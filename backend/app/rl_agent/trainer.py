from __future__ import annotations

import gc
import json
import math
import os
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd
import torch

from .offline_algorithms import algorithm_metadata, build_model, train_step
from .triage_env import ACTIONS, FEATURES, INCIDENT_ID, LABELS, REWARD_TABLE, TARGET, sort_incidents


class TrainingStopped(Exception):
    """Raised when a managed training process receives a stop request."""


def prepare_transitions(df: pd.DataFrame):
    """Build transitions without Python lists per row.

    The previous implementation created several million Python-list entries.
    That produced a large RAM spike on the real SOC dataset. The dataset is
    sorted once, then transitions are constructed with NumPy arrays.
    """
    df, timestamp_col = sort_incidents(df)

    states = df[FEATURES].astype(np.float32).to_numpy(copy=True)
    labels = df[TARGET].astype(np.int64).to_numpy(copy=True)
    incident_ids = df[INCIDENT_ID].astype(str).to_numpy(copy=True)

    next_states = states.copy()
    if len(states) > 1:
        same_incident = incident_ids[:-1] == incident_ids[1:]
        next_states[:-1][same_incident] = states[1:][same_incident]

    dones = np.ones(len(states), dtype=np.float32)
    steps = np.zeros(len(states), dtype=np.int64)
    if len(states) > 1:
        same_incident = incident_ids[1:] == incident_ids[:-1]
        dones[:-1][same_incident] = 0.0
        steps[1:] = np.where(same_incident, steps[:-1] + 1, 0)

    return states, next_states, labels, dones, incident_ids, steps, timestamp_col


def _counterfactual_rewards(labels: np.ndarray) -> np.ndarray:
    matrix = np.zeros((len(labels), len(ACTIONS)), dtype=np.float32)
    for label, row in REWARD_TABLE.items():
        mask = labels == int(label)
        if np.any(mask):
            for action in ACTIONS:
                matrix[mask, action] = float(row[action])
    unknown = ~np.isin(labels, list(REWARD_TABLE.keys()))
    if np.any(unknown):
        row = REWARD_TABLE[max(REWARD_TABLE)]
        for action in ACTIONS:
            matrix[unknown, action] = float(row[action])
    return matrix


def evaluate_policy(model, csv_path: str, chunksize: int = 100_000) -> dict:
    """Evaluate in bounded chunks so validation/test never loads the whole CSV."""
    total_reward = 0.0
    optimal_reward = 0.0
    optimal_actions = 0
    rows = 0
    incidents: set[str] = set()
    action_counts = {name: 0 for name in ACTIONS.values()}
    class_stats: dict[int, dict[str, float]] = {}
    start = time.perf_counter()

    for chunk in pd.read_csv(csv_path, usecols=list(FEATURES) + [INCIDENT_ID, TARGET], chunksize=chunksize, low_memory=False):
        states = chunk[FEATURES].astype(np.float32).to_numpy(copy=False)
        labels = chunk[TARGET].astype(np.int64).to_numpy(copy=False)
        ids = chunk[INCIDENT_ID].astype(str).to_numpy(copy=False)
        incidents.update(ids.tolist())

        actions = np.asarray(model.act(states), dtype=np.int64)
        rewards = _counterfactual_rewards(labels)
        chosen = rewards[np.arange(len(actions)), actions]
        best = rewards.max(axis=1)

        total_reward += float(chosen.sum())
        optimal_reward += float(best.sum())
        optimal_actions += int(np.count_nonzero(chosen == best))
        rows += len(labels)

        for action in actions:
            action_counts[ACTIONS[int(action)]] += 1

        for label in np.unique(labels):
            mask = labels == label
            stats = class_stats.setdefault(int(label), {"rows": 0.0, "reward": 0.0, "optimal": 0.0})
            stats["rows"] += float(mask.sum())
            stats["reward"] += float(chosen[mask].sum())
            stats["optimal"] += float(best[mask].sum())

        del chunk, states, labels, ids, actions, rewards, chosen, best

    elapsed = time.perf_counter() - start
    per_class = {}
    for label, stats in class_stats.items():
        n = int(stats["rows"])
        per_class[LABELS.get(label, "Unknown")] = {
            "rows": n,
            "average_reward": stats["reward"] / n if n else 0.0,
            "optimality": stats["reward"] / stats["optimal"] if stats["optimal"] else 0.0,
        }

    gc.collect()
    return {
        "rows": rows,
        "incidents": len(incidents),
        "total_reward": total_reward,
        "average_reward": total_reward / rows if rows else 0.0,
        "oracle_average_reward": optimal_reward / rows if rows else 0.0,
        "reward_efficiency": total_reward / optimal_reward if optimal_reward else 0.0,
        "policy_optimality": optimal_actions / rows if rows else 0.0,
        "action_distribution": action_counts,
        "evaluation_time_seconds": elapsed,
        "throughput_rows_per_second": rows / elapsed if elapsed else 0.0,
        "per_class": per_class,
    }


def _checkpoint(model, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(path))


def _finite(value: float) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else 0.0
    except Exception:
        return 0.0


def train(
    train_csv: str,
    epochs: int = 4000,
    batch_size: int = 512,
    learning_rate: float = 1e-3,
    gamma: float = 0.95,
    target_update: int = 1,
    seed: int = 42,
    stop_event: Optional[object] = None,
    validation_csv: str | None = None,
    min_epochs: int = 20,
    patience: int = 10,
    min_delta: float = 1e-3,
    stability_window: int = 6,
    stability_tolerance: float = 0.002,
    checkpoint_path: str | None = None,
    progress_callback: Optional[Callable[[dict], None]] = None,
    max_total_updates: int | None = None,
    algorithm: str = "double_dqn",
    hidden_dim: int = 128,
):
    np.random.seed(seed)
    torch.manual_seed(seed)

    # Explicit CPU limits protect the 12 GB-class local machine from thread
    # explosions in NumPy/PyTorch/BLAS.
    threads = max(1, min(int(os.getenv("RL_TORCH_THREADS", "2")), os.cpu_count() or 2))
    try:
        torch.set_num_threads(threads)
    except RuntimeError:
        pass

    algorithm_info = algorithm_metadata(algorithm)

    # Read the authoritative training split once. Transition construction is
    # vectorised; the original dataframe is released immediately afterwards.
    df = pd.read_csv(train_csv, usecols=list(FEATURES) + [INCIDENT_ID, TARGET], low_memory=False)
    states, next_states, labels, dones, incident_ids, _, timestamp_col = prepare_transitions(df)
    n_rows = len(states)
    incident_count = int(np.unique(incident_ids).size)
    del df
    gc.collect()

    updates_per_epoch = math.ceil(n_rows / batch_size) if n_rows else 0
    update_budget = int(max_total_updates) if max_total_updates else max(1, updates_per_epoch * max(1, epochs))
    model = build_model(
        algorithm,
        input_dim=len(FEATURES),
        n_actions=len(ACTIONS),
        learning_rate=learning_rate,
        gamma=gamma,
        hidden_dim=hidden_dim,
    )

    metrics_path = Path(__file__).resolve().parents[3] / "models" / "training_metrics.json"
    best_path = Path(checkpoint_path) if checkpoint_path else metrics_path.with_name("best_candidate.pt")
    metrics: list[dict] = []
    best_score = -float("inf")
    best_epoch = 0
    best_validation = None
    epochs_without_improvement = 0
    total_updates_used = 0
    stopping_reason = "max_epochs_reached"

    config = {
        **algorithm_info,
        "model_name": algorithm_info["display_name"],
        "algorithm": algorithm_info["algorithm"],
        "epochs": epochs,
        "max_epochs": epochs,
        "min_epochs": min_epochs,
        "patience": patience,
        "min_delta": min_delta,
        "stability_window": stability_window,
        "stability_tolerance": stability_tolerance,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "gamma": gamma,
        "hidden_dim": hidden_dim,
        "features": FEATURES,
        "actions": ACTIONS,
        "incident_id": INCIDENT_ID,
        "target": TARGET,
        "synthetic_data": False,
        "real_data": True,
        "incident_level_episodes": True,
        "early_stopping": validation_csv is not None,
        "timestamp_column": timestamp_col,
        "updates_per_epoch": updates_per_epoch,
        "max_total_updates": update_budget,
        "threads": threads,
        "ram_safe_chunk_evaluation": True,
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps({"config": config, "metrics": []}, indent=2), encoding="utf-8")

    for epoch in range(1, epochs + 1):
        if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
            raise TrainingStopped("Training stopped by user.")
        if total_updates_used >= update_budget:
            stopping_reason = "update_budget_reached"
            break

        epoch_start = time.perf_counter()
        indices = np.random.permutation(n_rows)
        total_loss = 0.0
        updates = 0
        policy_reward_sum = 0.0
        oracle_reward_sum = 0.0
        action_counts = {name: 0 for name in ACTIONS.values()}

        for start_idx in range(0, n_rows, batch_size):
            if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
                raise TrainingStopped("Training stopped by user.")
            if total_updates_used >= update_budget:
                break

            batch_idx = indices[start_idx:start_idx + batch_size]
            batch_states = states[batch_idx]
            batch_next = next_states[batch_idx]
            batch_labels = labels[batch_idx]
            batch_dones = dones[batch_idx]
            reward_matrix = _counterfactual_rewards(batch_labels)

            total_loss += _finite(
                train_step(model, algorithm, batch_states, reward_matrix, batch_next, batch_dones)
            )
            updates += 1
            total_updates_used += 1

            policy_actions = np.asarray(model.act(batch_states), dtype=np.int64)
            chosen_rewards = reward_matrix[np.arange(len(policy_actions)), policy_actions]
            policy_reward_sum += float(chosen_rewards.sum())
            oracle_reward_sum += float(reward_matrix.max(axis=1).sum())
            for action in policy_actions:
                action_counts[ACTIONS[int(action)]] += 1

        del indices
        if target_update > 0 and epoch % target_update == 0:
            model.update_target()

        elapsed = time.perf_counter() - epoch_start
        loss_value = total_loss / max(updates, 1)
        policy_reward = policy_reward_sum / n_rows if n_rows else 0.0
        oracle_reward = oracle_reward_sum / n_rows if n_rows else 0.0
        efficiency = policy_reward / oracle_reward if oracle_reward else 0.0

        # Validation is streamed in bounded chunks. This is intentionally done
        # without loading or grouping the complete validation CSV in RAM.
        validation = evaluate_policy(model, validation_csv) if validation_csv else None
        validation_score = None
        improved = False

        if validation:
            validation_score = 0.70 * validation["policy_optimality"] + 0.30 * validation["reward_efficiency"]
            improved = validation_score > best_score + min_delta
            if improved:
                best_score = validation_score
                best_epoch = epoch
                best_validation = validation
                epochs_without_improvement = 0
                _checkpoint(model, best_path)
            else:
                epochs_without_improvement += 1

        row = {
            "epoch": epoch,
            "rows": n_rows,
            "incidents": incident_count,
            "updates": updates,
            "total_updates": total_updates_used,
            "updates_per_epoch": updates_per_epoch,
            "loss": loss_value,
            "average_reward": policy_reward,
            "policy_reward": policy_reward,
            "oracle_average_reward": oracle_reward,
            "reward_efficiency": efficiency,
            "action_counts": action_counts,
            "action_distribution": action_counts,
            "time_seconds": elapsed,
            "validation": validation,
            "validation_score": validation_score,
            "best_epoch": best_epoch,
            "patience_used": epochs_without_improvement,
            "improved": improved,
            "algorithm": algorithm_info["algorithm"],
            "behavior_action_mode": algorithm_info["behavior_action_mode"],
            "stopping_reason": None,
        }
        metrics.append(row)

        convergence = False
        persistent_decline = False
        if validation and epoch >= min_epochs:
            recent = [r.get("validation_score") for r in metrics[-stability_window:] if isinstance(r.get("validation_score"), (int, float))]
            recent_rewards = [r.get("policy_reward") for r in metrics[-stability_window:] if isinstance(r.get("policy_reward"), (int, float))]
            if len(recent) == stability_window and len(recent_rewards) == stability_window:
                score_flat = max(recent) - min(recent) <= stability_tolerance
                reward_ref = max(abs(float(np.mean(recent_rewards))), 1.0)
                reward_flat = max(recent_rewards) - min(recent_rewards) <= max(stability_tolerance, reward_ref * 0.0025)
                no_new_best = all(float(v) <= best_score + min_delta for v in recent)
                convergence = score_flat and reward_flat and no_new_best
                persistent_decline = recent[-1] < best_score - min_delta and all(
                    recent[i] <= recent[i - 1] + min_delta * 0.25 for i in range(1, len(recent))
                )
            if persistent_decline:
                stopping_reason = "persistent_validation_decline"
            elif convergence:
                stopping_reason = "validation_and_policy_converged"
            elif epochs_without_improvement >= patience:
                stopping_reason = "validation_patience_exhausted"
            if stopping_reason != "max_epochs_reached":
                row["stopping_reason"] = stopping_reason

        metrics_path.write_text(
            json.dumps(
                {
                    "config": config,
                    "metrics": metrics,
                    "best_epoch": best_epoch,
                    "actual_epochs": epoch,
                    "best_validation": best_validation,
                    "total_updates_used": total_updates_used,
                    "updates_per_epoch": updates_per_epoch,
                    "max_total_updates": update_budget,
                    "stopping_reason": row["stopping_reason"],
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        if progress_callback:
            progress_callback(row)
        if row["stopping_reason"]:
            break
        if total_updates_used >= update_budget:
            stopping_reason = "update_budget_reached"
            break

        gc.collect()

    if best_path.exists() and best_epoch:
        try:
            model.load(str(best_path))
        except Exception:
            pass

    final_epoch = metrics[-1]["epoch"] if metrics else 0
    result = {
        "config": config,
        "metrics": metrics,
        "best_epoch": best_epoch,
        "best_validation": best_validation,
        "actual_epochs": final_epoch,
        "total_updates_used": total_updates_used,
        "updates_per_epoch": updates_per_epoch,
        "max_total_updates": update_budget,
        "stopping_reason": stopping_reason,
    }
    metrics_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    del states, next_states, labels, dones, incident_ids
    gc.collect()
    return model, result
