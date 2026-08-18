from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.services.training_history import list_runs, load_run

router = APIRouter(prefix="/api/authoritative-metrics", tags=["Authoritative Metrics"])

SUPPORTED_ALGORITHMS = {"double_dqn", "cql"}


def _evaluation_is_populated(run: dict[str, Any]) -> bool:
    results = run.get("results") if isinstance(run.get("results"), dict) else {}
    evaluation = results.get("evaluation") if isinstance(results.get("evaluation"), dict) else {}
    return any(
        isinstance(evaluation.get(key), (int, float))
        for key in ("average_reward", "policy_optimality", "reward_efficiency", "reward_regret", "throughput_rows_per_second")
    ) or bool(evaluation.get("action_distribution")) or bool(evaluation.get("per_class"))


def _latest_supported_run() -> dict[str, Any] | None:
    fallback: dict[str, Any] | None = None

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
        if status not in {"completed", "stopped", "failed", "current"}:
            continue

        if fallback is None:
            fallback = loaded

        # Metrics should represent the latest run that actually has a persisted
        # unseen-test evaluation, not a newer telemetry-only/legacy artifact.
        if _evaluation_is_populated(loaded):
            return loaded

    return fallback


@router.get("")
def authoritative_metrics():
    run = _latest_supported_run()
    if not run:
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

    results = run.get("results") if isinstance(run.get("results"), dict) else {}
    training = results.get("training") if isinstance(results.get("training"), dict) else {}
    evaluation = results.get("evaluation") if isinstance(results.get("evaluation"), dict) else {}
    history = training.get("history") if isinstance(training.get("history"), list) else []
    last = history[-1] if history else {}

    return {
        "status": "available",
        "run_id": run.get("run_id"),
        "training": {
            "run_id": run.get("run_id"),
            "algorithm": training.get("algorithm") or run.get("algorithm"),
            "display_name": training.get("display_name") or run.get("display_name"),
            "epochs": training.get("actual_epochs") or len(history),
            "best_epoch": training.get("best_epoch"),
            "stopping_reason": training.get("stopping_reason"),
            "history": history,
            "latest_loss": last.get("loss"),
            "latest_reward": last.get("average_reward", last.get("policy_reward")),
        },
        "evaluation": {
            "samples": evaluation.get("samples"),
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
