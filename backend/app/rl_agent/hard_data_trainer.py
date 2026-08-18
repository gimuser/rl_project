from __future__ import annotations

import gc
import json
import math
import os
import subprocess
import time
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import torch

from .offline_algorithms import algorithm_metadata, build_model, train_step
from .triage_env import ACTIONS, FEATURES, INCIDENT_ID, LABELS, REWARD_TABLE, TARGET


MODEL_FEATURES = list(FEATURES)
USECOLS = MODEL_FEATURES + [INCIDENT_ID, TARGET]


def _counterfactual_rewards(labels: np.ndarray) -> np.ndarray:
    matrix = np.zeros((len(labels), len(ACTIONS)), dtype=np.float32)
    for label, rewards in REWARD_TABLE.items():
        mask = labels == int(label)
        if np.any(mask):
            for action in ACTIONS:
                matrix[mask, action] = float(rewards[action])
    unknown = ~np.isin(labels, list(REWARD_TABLE.keys()))
    if np.any(unknown):
        fallback = REWARD_TABLE[max(REWARD_TABLE)]
        for action in ACTIONS:
            matrix[unknown, action] = float(fallback[action])
    return matrix


def _model_dtypes() -> dict[str, str]:
    # All engineered state columns in the processed files are numeric.
    dtypes = {name: "float32" for name in MODEL_FEATURES}
    dtypes[TARGET] = "int64"
    dtypes[INCIDENT_ID] = "string"
    return dtypes


def _write_progress(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _iter_batches(
    csv_path: str | Path,
    *,
    batch_size: int,
    chunk_size: int,
    include_incidents: set[str] | None = None,
    invert_filter: bool = False,
    shuffle_within_chunk: bool = True,
    seed: int = 42,
    epoch: int = 0,
    progress_callback: Callable[[dict], None] | None = None,
):
    """Stream alert rows and yield small one-step contextual RL batches.

    There is no historical agent-action column in this dataset. Therefore the
    training problem is explicitly treated as a one-step counterfactual alert
    decision: reward(action | historical IncidentGrade), with no fabricated
    next-alert transition.
    """
    rng = np.random.default_rng(seed + epoch)
    dtypes = _model_dtypes()
    source_rows_seen = 0
    chunk_index = 0

    for chunk in pd.read_csv(
        csv_path,
        usecols=USECOLS,
        dtype=dtypes,
        chunksize=chunk_size,
        low_memory=True,
    ):
        chunk_index += 1
        source_rows_seen += len(chunk)

        if progress_callback:
            progress_callback({
                "source_rows_processed": source_rows_seen,
                "chunk_index": chunk_index,
            })

        ids = chunk[INCIDENT_ID].astype(str)

        if include_incidents is not None:
            mask = ids.isin(include_incidents)
            if invert_filter:
                mask = ~mask
            chunk = chunk.loc[mask]

        if chunk.empty:
            del chunk, ids
            continue

        states = chunk[MODEL_FEATURES].to_numpy(dtype=np.float32, copy=True)
        labels = chunk[TARGET].to_numpy(dtype=np.int64, copy=True)

        if shuffle_within_chunk and len(states) > 1:
            order = rng.permutation(len(states))
            states = states[order]
            labels = labels[order]

        for start in range(0, len(states), batch_size):
            end = min(start + batch_size, len(states))
            batch_states = states[start:end]
            batch_labels = labels[start:end]

            # One-step contextual decision: no fabricated temporal transition.
            next_states = batch_states
            dones = np.ones(len(batch_states), dtype=np.float32)
            rewards = _counterfactual_rewards(batch_labels)

            yield batch_states, rewards, next_states, dones, batch_labels

        del chunk, ids, states, labels


def evaluate_streaming(
    model,
    csv_path: str | Path,
    *,
    chunk_size: int = 100_000,
    include_incidents: set[str] | None = None,
    invert_filter: bool = False,
) -> dict:
    total_reward = 0.0
    oracle_reward = 0.0
    optimal_actions = 0
    rows = 0
    incidents: set[str] = set()
    action_counts = {name: 0 for name in ACTIONS.values()}
    class_stats: dict[int, dict[str, float]] = {}
    start = time.perf_counter()

    dtypes = _model_dtypes()

    for chunk in pd.read_csv(
        csv_path,
        usecols=USECOLS,
        dtype=dtypes,
        chunksize=chunk_size,
        low_memory=True,
    ):
        ids = chunk[INCIDENT_ID].astype(str)
        if include_incidents is not None:
            mask = ids.isin(include_incidents)
            if invert_filter:
                mask = ~mask
            chunk = chunk.loc[mask]
            ids = ids.loc[mask]

        if chunk.empty:
            del chunk, ids
            continue

        states = chunk[MODEL_FEATURES].to_numpy(dtype=np.float32, copy=False)
        labels = chunk[TARGET].to_numpy(dtype=np.int64, copy=False)
        incidents.update(ids.tolist())

        actions = np.asarray(model.act(states), dtype=np.int64)
        rewards = _counterfactual_rewards(labels)
        chosen = rewards[np.arange(len(actions)), actions]
        best = rewards.max(axis=1)

        total_reward += float(chosen.sum())
        oracle_reward += float(best.sum())
        optimal_actions += int(np.count_nonzero(chosen == best))
        rows += len(labels)

        for action in actions:
            action_counts[ACTIONS[int(action)]] += 1

        for label in np.unique(labels):
            mask_label = labels == label
            stats = class_stats.setdefault(
                int(label),
                {"rows": 0.0, "reward": 0.0, "optimal": 0.0},
            )
            stats["rows"] += float(mask_label.sum())
            stats["reward"] += float(chosen[mask_label].sum())
            stats["optimal"] += float(best[mask_label].sum())

        del chunk, ids, states, labels, actions, rewards, chosen, best

    elapsed = time.perf_counter() - start
    per_class = {}

    for label, stats in class_stats.items():
        n = int(stats["rows"])
        per_class[LABELS.get(label, "Unknown")] = {
            "rows": n,
            "average_reward": stats["reward"] / n if n else 0.0,
            "optimality": stats["reward"] / stats["optimal"] if stats["optimal"] else 0.0,
        }

    return {
        "rows": rows,
        "incidents": len(incidents),
        "total_reward": total_reward,
        "average_reward": total_reward / rows if rows else 0.0,
        "oracle_average_reward": oracle_reward / rows if rows else 0.0,
        "reward_efficiency": total_reward / oracle_reward if oracle_reward else 0.0,
        "policy_optimality": optimal_actions / rows if rows else 0.0,
        "action_distribution": action_counts,
        "evaluation_time_seconds": elapsed,
        "throughput_rows_per_second": rows / elapsed if elapsed else 0.0,
        "per_class": per_class,
        "data_mode": "hard_alert_streaming",
        "one_step_contextual": True,
    }


def _count_rows(path: str | Path) -> int:
    """Fast OS-level row count; never iterate over CSV rows in Python."""
    result = subprocess.run(
        ["wc", "-l", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return max(0, int(result.stdout.strip().split()[0]) - 1)


def train_streaming(
    *,
    train_csv: str | Path,
    validation_csv: str | Path,
    validation_ids: set[str],
    epochs: int = 10,
    batch_size: int = 512,
    learning_rate: float = 1e-3,
    gamma: float = 0.95,
    target_update: int = 1,
    seed: int = 42,
    validation_every: int = 2,
    patience: int = 3,
    min_epochs: int = 2,
    min_delta: float = 1e-3,
    max_total_updates: int | None = None,
    chunk_size: int = 50_000,
    metric_sample_rows: int = 10_000,
    checkpoint_path: str | None = None,
    algorithm: str = "double_dqn",
    hidden_dim: int = 128,
    progress_callback: Callable[[dict], None] | None = None,
    stop_event: object | None = None,
):
    np.random.seed(seed)
    torch.manual_seed(seed)

    threads = max(
        1,
        min(
            int(os.getenv("RL_TORCH_THREADS", "2")),
            os.cpu_count() or 2,
        ),
    )
    try:
        torch.set_num_threads(threads)
    except RuntimeError:
        pass

    algorithm_info = algorithm_metadata(algorithm)
    train_rows = _count_rows(train_csv)
    updates_per_full_pass = math.ceil(train_rows / batch_size)
    update_budget = int(
        max_total_updates
        if max_total_updates is not None
        else min(25_000, max(1, updates_per_full_pass * epochs))
    )
    progress_path = Path(
        os.getenv(
            "REAL_RL_PROGRESS_PATH",
            str(Path(train_csv).resolve().parents[2] / "models" / "training_progress.json"),
        )
    )
    chunks_total = math.ceil(train_rows / chunk_size)

    model = build_model(
        algorithm,
        input_dim=len(MODEL_FEATURES),
        n_actions=len(ACTIONS),
        learning_rate=learning_rate,
        gamma=gamma,
        hidden_dim=hidden_dim,
    )

    metrics: list[dict] = []
    best_score = -float("inf")
    best_epoch = 0
    best_validation = None
    epochs_without_improvement = 0
    total_updates = 0
    stopping_reason = "max_epochs_reached"
    sample_states = None
    sample_labels = None

    for epoch in range(1, epochs + 1):
        if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
            raise RuntimeError("Training stopped by user.")
        if total_updates >= update_budget:
            stopping_reason = "update_budget_reached"
            break

        epoch_start = time.perf_counter()
        updates = 0
        seen_rows = 0
        loss_sum = 0.0
        streamed_rows = 0
        streamed_chunks = 0

        _write_progress(progress_path, {
            "status": "running",
            "stage": "epoch_in_progress",
            "algorithm": algorithm_info["algorithm"],
            "display_name": algorithm_info["display_name"],
            "epoch": epoch,
            "epochs": epochs,
            "completed_epochs": epoch - 1,
            "source_rows_processed": 0,
            "source_rows_total": train_rows,
            "progress_percent": 0.0,
            "chunks_processed": 0,
            "chunks_total": chunks_total,
            "filtered_train_rows_processed": 0,
            "updates": 0,
            "total_updates": total_updates,
            "updated_at": time.time(),
        })

        def stream_progress(info: dict) -> None:
            nonlocal streamed_rows, streamed_chunks
            streamed_rows = int(info.get("source_rows_processed", streamed_rows))
            streamed_chunks = int(info.get("chunk_index", streamed_chunks))
            percent = min(100.0, (streamed_rows / train_rows) * 100.0) if train_rows else 0.0
            payload = {
                "status": "running",
                "stage": "epoch_in_progress",
                "algorithm": algorithm_info["algorithm"],
                "display_name": algorithm_info["display_name"],
                "epoch": epoch,
                "epochs": epochs,
                "completed_epochs": epoch - 1,
                "source_rows_processed": streamed_rows,
                "source_rows_total": train_rows,
                "progress_percent": round(percent, 2),
                "chunks_processed": streamed_chunks,
                "chunks_total": chunks_total,
                "filtered_train_rows_processed": seen_rows,
                "updates": updates,
                "total_updates": total_updates,
                "updated_at": time.time(),
            }
            _write_progress(progress_path, payload)
            if progress_callback:
                progress_callback(payload)

        for states, rewards, next_states, dones, labels in _iter_batches(
            train_csv,
            batch_size=batch_size,
            chunk_size=chunk_size,
            include_incidents=validation_ids,
            invert_filter=True,
            shuffle_within_chunk=True,
            seed=seed,
            epoch=epoch,
            progress_callback=stream_progress,
        ):
            if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
                raise RuntimeError("Training stopped by user.")
            if total_updates >= update_budget:
                break

            if sample_states is None and metric_sample_rows > 0:
                take = min(metric_sample_rows, len(states))
                sample_states = states[:take].copy()
                sample_labels = labels[:take].copy()

            loss = train_step(
                model,
                algorithm,
                states,
                rewards,
                next_states,
                dones,
            )

            loss_sum += float(loss)
            updates += 1
            total_updates += 1
            seen_rows += len(states)

            del states, rewards, next_states, dones, labels

        if target_update > 0 and epoch % target_update == 0:
            model.update_target()

        elapsed = time.perf_counter() - epoch_start
        training_loss = loss_sum / max(1, updates)

        if sample_states is not None and sample_labels is not None:
            sample_actions = np.asarray(model.act(sample_states), dtype=np.int64)
            sample_rewards = _counterfactual_rewards(sample_labels)
            sample_chosen = sample_rewards[
                np.arange(len(sample_actions)),
                sample_actions,
            ]
            sample_best = sample_rewards.max(axis=1)
            train_metric_reward = float(sample_chosen.mean())
            train_metric_efficiency = (
                float(sample_chosen.sum())
                / float(sample_best.sum())
                if float(sample_best.sum()) != 0.0
                else 0.0
            )
            sample_action_distribution = {
                name: int(np.count_nonzero(sample_actions == action))
                for action, name in ACTIONS.items()
            }
        else:
            train_metric_reward = 0.0
            train_metric_efficiency = 0.0
            sample_action_distribution = {name: 0 for name in ACTIONS.values()}

        validation = None
        validation_score = None
        improved = False

        if validation_every > 0 and (epoch % validation_every == 0 or epoch == epochs or total_updates >= update_budget):
            validation = evaluate_streaming(
                model,
                validation_csv,
                chunk_size=chunk_size,
                include_incidents=validation_ids,
                invert_filter=False,
            )
            validation_score = (
                0.70 * validation["policy_optimality"]
                + 0.30 * validation["reward_efficiency"]
            )

            if validation_score > best_score + min_delta:
                best_score = validation_score
                best_epoch = epoch
                best_validation = validation
                epochs_without_improvement = 0
                if checkpoint_path:
                    Path(checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
                    model.save(str(checkpoint_path))
                improved = True
            else:
                epochs_without_improvement += 1

        row = {
            "epoch": epoch,
            "rows_seen": seen_rows,
            "dataset_rows": train_rows,
            "validation_incidents": len(validation_ids),
            "updates": updates,
            "total_updates": total_updates,
            "updates_per_epoch_full_pass": updates_per_full_pass,
            "loss": training_loss,
            "average_reward": train_metric_reward,
            "reward_efficiency": train_metric_efficiency,
            "sample_rows": int(len(sample_states)) if sample_states is not None else 0,
            "sample_action_distribution": sample_action_distribution,
            "time_seconds": elapsed,
            "throughput_rows_per_second": seen_rows / elapsed if elapsed else 0.0,
            "validation": validation,
            "validation_score": validation_score,
            "best_epoch": best_epoch,
            "patience_used": epochs_without_improvement,
            "improved": improved,
            "algorithm": algorithm_info["algorithm"],
            "behavior_action_mode": algorithm_info["behavior_action_mode"],
            "data_mode": "hard_alert_streaming",
            "one_step_contextual": True,
            "representative_incident_training": False,
            "stopping_reason": None,
        }
        metrics.append(row)

        if validation is not None and epoch >= min_epochs:
            if epochs_without_improvement >= patience:
                stopping_reason = "validation_patience_exhausted"
                row["stopping_reason"] = stopping_reason

        _write_progress(progress_path, {
            "status": "running",
            "stage": "epoch_completed",
            "algorithm": algorithm_info["algorithm"],
            "display_name": algorithm_info["display_name"],
            "epoch": epoch,
            "epochs": epochs,
            "completed_epochs": epoch,
            "source_rows_processed": train_rows,
            "source_rows_total": train_rows,
            "progress_percent": 100.0,
            "chunks_processed": chunks_total,
            "chunks_total": chunks_total,
            "filtered_train_rows_processed": seen_rows,
            "updates": updates,
            "total_updates": total_updates,
            "updated_at": time.time(),
        })

        if progress_callback:
            progress_callback({
                "status": "running",
                "stage": "epoch_completed",
                "algorithm": algorithm_info["algorithm"],
                "display_name": algorithm_info["display_name"],
                "epoch": epoch,
                "epochs": epochs,
                "completed_epochs": epoch,
                "source_rows_processed": train_rows,
                "source_rows_total": train_rows,
                "progress_percent": 100.0,
                "chunks_processed": chunks_total,
                "chunks_total": chunks_total,
                "filtered_train_rows_processed": seen_rows,
                "updates": updates,
                "total_updates": total_updates,
                "updated_at": time.time(),
            })

        if row["stopping_reason"]:
            break

        gc.collect()

    if checkpoint_path and Path(checkpoint_path).exists() and best_epoch:
        model.load(str(checkpoint_path))
    elif checkpoint_path:
        Path(checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
        model.save(str(checkpoint_path))

    final_epoch = metrics[-1]["epoch"] if metrics else 0
    _write_progress(progress_path, {
        "status": "completed",
        "stage": "training_completed",
        "algorithm": algorithm_info["algorithm"],
        "display_name": algorithm_info["display_name"],
        "epoch": final_epoch,
        "epochs": epochs,
        "completed_epochs": final_epoch,
        "source_rows_processed": train_rows,
        "source_rows_total": train_rows,
        "progress_percent": 100.0,
        "chunks_processed": chunks_total,
        "chunks_total": chunks_total,
        "filtered_train_rows_processed": metrics[-1]["rows_seen"] if metrics else 0,
        "updates": total_updates,
        "total_updates": total_updates,
        "updated_at": time.time(),
    })

    result = {
        "config": {
            **algorithm_info,
            "model_name": algorithm_info["display_name"],
            "algorithm": algorithm_info["algorithm"],
            "epochs": epochs,
            "actual_epochs": final_epoch,
            "batch_size": batch_size,
            "learning_rate": learning_rate,
            "gamma": gamma,
            "hidden_dim": hidden_dim,
            "validation_every": validation_every,
            "patience": patience,
            "min_epochs": min_epochs,
            "min_delta": min_delta,
            "chunk_size": chunk_size,
            "max_total_updates": update_budget,
            "updates_per_full_pass": updates_per_full_pass,
            "dataset_rows": train_rows,
            "features": MODEL_FEATURES,
            "incident_id": INCIDENT_ID,
            "target": TARGET,
            "real_data": True,
            "synthetic_data": False,
            "data_mode": "hard_alert_streaming",
            "one_step_contextual": True,
            "representative_incident_training": False,
            "test_used_for_selection": False,
            "threads": threads,
        },
        "metrics": metrics,
        "best_epoch": best_epoch,
        "best_validation": best_validation,
        "actual_epochs": final_epoch,
        "total_updates_used": total_updates,
        "updates_per_full_pass": updates_per_full_pass,
        "max_total_updates": update_budget,
        "stopping_reason": stopping_reason,
    }

    del sample_states, sample_labels
    gc.collect()
    return model, result