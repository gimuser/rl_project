from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from .offline_algorithms import build_model, algorithm_metadata
from .triage_env import ACTIONS, FEATURES, INCIDENT_ID, TARGET, LABELS, REWARD_TABLE, sort_incidents


def evaluate(test_csv: str, model_path: str = "models/real_dqn_agent.pt"):
    df = pd.read_csv(test_csv, low_memory=False)
    df, timestamp_col = sort_incidents(df)
    checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
    algorithm = str(checkpoint.get("algorithm", "double_dqn")).lower()
    model = build_model(algorithm, input_dim=len(FEATURES), n_actions=len(ACTIONS), learning_rate=1e-3, gamma=float(checkpoint.get("gamma", 0.95)), hidden_dim=128)
    model.load(model_path)

    total_reward = 0.0
    optimal_reward = 0.0
    optimal_actions = 0
    action_counts = {name: 0 for name in ACTIONS.values()}
    class_stats = {int(label): {"rows": 0, "reward": 0.0, "optimal_reward": 0.0} for label in LABELS}
    predictions = []
    start = time.perf_counter()

    for incident_id, group in df.groupby(INCIDENT_ID, sort=False):
        rows = group.reset_index(drop=True)
        states = rows[FEATURES].astype(np.float32).to_numpy(copy=True)
        labels = rows[TARGET].astype(int).to_numpy(copy=True)
        q_values = model.q_values(states)
        actions = model.act(states) if algorithm in {"iql", "bcq"} else np.argmax(q_values, axis=1)
        for i, (label, action) in enumerate(zip(labels, actions)):
            label = int(label); action = int(action)
            rewards = REWARD_TABLE.get(label, REWARD_TABLE[max(REWARD_TABLE)])
            reward = float(rewards[action]); optimal = float(max(rewards.values()))
            total_reward += reward; optimal_reward += optimal; optimal_actions += int(reward == optimal); action_name = ACTIONS[action]; action_counts[action_name] += 1
            stats = class_stats[label]; stats["rows"] += 1; stats["reward"] += reward; stats["optimal_reward"] += optimal
            predictions.append({"IncidentId": str(incident_id), "step": i, "label": label, "label_name": LABELS.get(label, "Unknown"), "action": action, "action_name": action_name, "reward": reward, "optimal_reward": optimal, "q_allow": float(q_values[i][0]), "q_block": float(q_values[i][1]), "q_human_review": float(q_values[i][2]), "done": i == len(rows) - 1})

    elapsed = time.perf_counter() - start
    n = len(predictions)
    avg_reward = total_reward / n if n else 0.0
    regret = optimal_reward - total_reward
    efficiency = total_reward / optimal_reward if optimal_reward else 0.0
    optimality = optimal_actions / n if n else 0.0
    per_class = {}
    for label, stats in class_stats.items():
        count = int(stats["rows"])
        if count:
            per_class[LABELS.get(label, "Unknown")] = {"rows": count, "average_reward": stats["reward"] / count, "optimality": stats["reward"] / stats["optimal_reward"] if stats["optimal_reward"] else 0.0}
    return {
        "rows": n,
        "test_rows": n,
        "incidents": int(df[INCIDENT_ID].astype(str).nunique()),
        "algorithm": algorithm,
        "algorithm_metadata": algorithm_metadata(algorithm),
        "timestamp_column": timestamp_col,
        "total_reward": total_reward,
        "average_reward": avg_reward,
        "oracle_average_reward": optimal_reward / n if n else 0.0,
        "reward_efficiency": efficiency,
        "policy_optimality": optimality,
        "reward_regret": regret,
        "action_distribution": action_counts,
        "throughput_rows_per_second": n / elapsed if elapsed else 0.0,
        "evaluation_time_seconds": elapsed,
        "per_class": per_class,
        "predictions": predictions,
        "unseen_incidents": True,
    }
