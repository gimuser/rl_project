from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter


router = APIRouter(prefix="/api/authoritative-metrics", tags=["Authoritative Metrics"])


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load(name: str) -> dict[str, Any]:
    path = _root() / "models" / name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


@router.get("")
def authoritative_metrics():
    training = _load("training_metrics.json")
    testing = _load("real_test_metrics.json")

    history = training.get("metrics") if isinstance(training.get("metrics"), list) else []
    last = history[-1] if history else {}

    # The evaluation pipeline does not currently persist classification
    # accuracy/F1 as a single scalar. Do not fabricate them.
    return {
        "status": "available" if testing else "unavailable",
        "training": {
            "epochs": training.get("config", {}).get("epochs"),
            "history": history,
            "latest_loss": last.get("loss"),
            "latest_reward": last.get("average_reward"),
        },
        "evaluation": {
            "samples": testing.get("test_rows"),
            "average_reward": testing.get("average_reward"),
            "throughput_rows_per_second": testing.get("throughput_rows_per_second"),
            "policy_optimality": testing.get("policy_optimality"),
            "reward_efficiency": testing.get("reward_efficiency"),
            "reward_regret": testing.get("reward_regret"),
            "action_distribution": testing.get("action_distribution"),
            "per_class": testing.get("per_class"),
            "accuracy": testing.get("accuracy"),
            "precision": testing.get("precision"),
            "recall": testing.get("recall"),
            "f1": testing.get("f1"),
            "mttr": testing.get("mttr"),
        },
    }
