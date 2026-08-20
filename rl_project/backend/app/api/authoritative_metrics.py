from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from app.services.training_history import list_runs, load_run

router = APIRouter(prefix="/api/authoritative-metrics", tags=["Authoritative Metrics"])

SUPPORTED_ALGORITHMS = {"double_dqn", "cql"}
PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "models"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _evaluation_is_populated(evaluation: dict[str, Any]) -> bool:
    return any(
        isinstance(evaluation.get(key), (int, float))
        for key in (
            "average_reward",
            "policy_optimality",
            "reward_efficiency",
            "reward_regret",
            "throughput_rows_per_second",
        )
    ) or bool(evaluation.get("action_distribution")) or bool(evaluation.get("per_class"))


def _loaded_evaluation(run: dict[str, Any]) -> dict[str, Any]:
    results = run.get("results") if isinstance(run.get("results"), dict) else {}
    evaluation = results.get("evaluation") if isinstance(results.get("evaluation"), dict) else {}
    return evaluation


def _latest_supported_run() -> dict[str, Any] | None:
    for run in list_runs():
        algorithm = str(run.get("algorithm") or "").lower()
        if algorithm not in SUPPORTED_ALGORITHMS:
            continue

        run_id = str(run.get("run_id") or "")
        if not run_id:
            continue

        loaded = load_run(run_id)
        if not loaded:
            continue

        status = str(loaded.get("status") or "")
        if status in {"completed", "stopped", "failed", "current"}:
            return loaded
    return None


def _latest_persisted_evaluation() -> dict[str, Any]:
    candidates: list[tuple[float, dict[str, Any]]] = []

    # Current final evaluation artifact.
    current = _load_json(MODELS_DIR / "real_test_metrics.json")
    if _evaluation_is_populated(current):
        try:
            ts = (MODELS_DIR / "real_test_metrics.json").stat().st_mtime
        except OSError:
            ts = 0.0
        candidates.append((ts, current))

    # Archived run evaluations. Use the training-history ordering timestamp
    # where available, falling back to the artifact mtime.
    for run in list_runs():
        algorithm = str(run.get("algorithm") or "").lower()
        if algorithm not in SUPPORTED_ALGORITHMS:
            continue
        run_id = str(run.get("run_id") or "")
        if not run_id:
            continue
        loaded = load_run(run_id)
        if not loaded:
            continue
        evaluation = _loaded_evaluation(loaded)
        if not _evaluation_is_populated(evaluation):
            continue
        sort_ts = float(run.get("sort_timestamp") or 0.0)
        candidates.append((sort_ts, evaluation))

    if not candidates:
        return {}
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


@router.get("")
def authoritative_metrics():
    latest_training = _latest_supported_run()
    if not latest_training:
        return {
            "status": "unavailable",
            "training": {
                "epochs": None,
                "history": [],
                "latest_loss": None,
                "latest_reward": None,
                "algorithm": None,
                "run_id": None,
            },
            "evaluation": {},
        }

    results = latest_training.get("results") if isinstance(latest_training.get("results"), dict) else {}
    training = results.get("training") if isinstance(results.get("training"), dict) else {}
    history = training.get("history") if isinstance(training.get("history"), list) else []
    last = history[-1] if history else {}

    # Training history and final unseen-test evaluation are resolved independently
    # but only from the supported Double DQN/CQL experiment family. This prevents
    # a newer telemetry-only run from blanking the latest available evaluation.
    evaluation = _latest_persisted_evaluation()

    return {
        "status": "available",
        "run_id": latest_training.get("run_id"),
        "training": {
            "run_id": latest_training.get("run_id"),
            "algorithm": training.get("algorithm") or latest_training.get("algorithm"),
            "display_name": training.get("display_name") or latest_training.get("display_name"),
            "epochs": training.get("actual_epochs") or len(history),
            "best_epoch": training.get("best_epoch"),
            "stopping_reason": training.get("stopping_reason"),
            "history": history,
            "latest_loss": last.get("loss"),
            "latest_reward": last.get("average_reward", last.get("policy_reward")),
        },
        "evaluation": {
            "samples": evaluation.get("samples", evaluation.get("test_rows")),
            "average_reward": evaluation.get("average_reward"),
            "throughput_rows_per_second": evaluation.get("throughput_rows_per_second"),
            "policy_optimality": evaluation.get("policy_optimality"),
            "reward_efficiency": evaluation.get("reward_efficiency"),
            "reward_regret": evaluation.get("reward_regret"),
            "action_distribution": evaluation.get("action_distribution"),
            "per_class": evaluation.get("per_class"),
            "accuracy": evaluation.get("accuracy"),
            "precision": evaluation.get("precision"),
            "recall": evaluation.get("recall"),
            "f1": evaluation.get("f1"),
            "mttr": evaluation.get("mttr"),
        },
    }
