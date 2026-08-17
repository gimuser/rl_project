from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from app.services.live_cycle_service import start_new_live_cycle
from app.services.live_inference_service import run_live_inference
from app.services.model_versioning import ensure_model_version

from .evaluator import evaluate
from .offline_algorithms import algorithm_metadata, get_algorithm
from .real_pipeline import (
    COMPARISON_PATH,
    EXPERIMENTS_DIR,
    MODEL_PATH,
    TEST_METRICS_PATH,
    TRAIN_METRICS_PATH,
    _experiment_configs,
    _score,
    _write_comparison,
    build_incident_split,
)
from .trainer import train
from .triage_env import FEATURES


def _int_env(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _float_env(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _run_id() -> str:
    return os.getenv("REAL_RL_RUN_ID", "legacy-run")


def _write_live_candidate_metrics(
    config: dict[str, Any],
    metrics: list[dict[str, Any]],
    result: dict[str, Any],
    index: int,
    count: int,
) -> None:
    """Persist the complete in-memory epoch history for one candidate/run.

    The trainer also writes training_metrics.json. This callback intentionally
    does not read that shared file: doing so caused the live API to see only
    the latest epoch while training was still running. The sequential runner
    is now the sole writer for the live candidate telemetry snapshot.
    """
    run_id = _run_id()
    normalized: list[dict[str, Any]] = []
    for item in metrics:
        if not isinstance(item, dict) or item.get("epoch") is None:
            continue
        normalized.append(
            {
                **item,
                "run_id": run_id,
                "algorithm": config.get("algorithm"),
                "model_name": config.get("model_name"),
                "display_name": config.get("display_name"),
            }
        )

    normalized.sort(key=lambda item: int(item["epoch"]))

    payload = {
        "run_id": run_id,
        "config": {
            **config,
            "run_id": run_id,
            "candidate_index": index,
            "candidate_count": count,
            "features": FEATURES,
            "synthetic_data": False,
            "real_data": True,
            "early_stopping": True,
            "experiment_mode": "sequential_algorithm_then_live_cycle",
        },
        "metrics": normalized,
        "best_epoch": result.get("best_epoch"),
        "actual_epochs": result.get("actual_epochs"),
        "total_updates_used": result.get("total_updates_used"),
        "updates_per_epoch": result.get("updates_per_epoch"),
        "max_total_updates": result.get("max_total_updates"),
        "stopping_reason": result.get("stopping_reason"),
    }
    TRAIN_METRICS_PATH.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )


def main() -> None:
    run_id = _run_id()
    print("=" * 78)
    print("SEQUENTIAL OFFLINE-RL ALGORITHM -> FRESH 40-ALERT EVALUATION")
    print("ADAPTIVE EARLY STOPPING + SINGLE-FLIGHT RESOURCE CONTROL")
    print(f"RUN ID: {run_id}")
    print("=" * 78)

    train_csv, validation_csv, test_csv = build_incident_split()
    max_epochs = _int_env("REAL_RL_MAX_EPOCHS", 4000)
    min_epochs = _int_env("REAL_RL_MIN_EPOCHS", 20)
    patience = _int_env("REAL_RL_PATIENCE", 10)
    min_delta = _float_env("REAL_RL_MIN_DELTA", 1e-3)
    stability_window = _int_env("REAL_RL_STABILITY_WINDOW", 6)
    stability_tolerance = _float_env("REAL_RL_STABILITY_TOLERANCE", 0.002)
    seed = _int_env("REAL_RL_SEED", 42)
    target_update = _int_env("REAL_RL_TARGET_UPDATE", 1)

    configs = _experiment_configs()
    comparison_records: list[dict[str, Any]] = []
    _write_comparison([], None, "running")
    COMPARISON_PATH.write_text(
        json.dumps(
            {
                "status": "running",
                "run_id": run_id,
                "selected_models": [str(c.get("name")) for c in configs],
                "candidates": [],
                "best": None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    for index, config in enumerate(configs, start=1):
        name = str(config.get("name") or f"candidate_{index}")
        algorithm = get_algorithm(str(config.get("algorithm", name))).name
        info = algorithm_metadata(algorithm)
        learning_rate = float(config.get("learning_rate", 1e-3))
        gamma = float(config.get("gamma", 0.95))
        batch_size = int(config.get("batch_size", 512))
        candidate_path = EXPERIMENTS_DIR / f"{run_id}__{name}.pt"
        candidate_history: list[dict[str, Any]] = []

        print("\n" + "=" * 78)
        print(f"MODEL {index}/{len(configs)}: {info['display_name']}")
        print(f"Algorithm: {algorithm}")
        print(f"Run: {run_id}")
        print("=" * 78)

        # Reset the live telemetry snapshot for every new candidate.
        TRAIN_METRICS_PATH.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "config": {
                        "run_id": run_id,
                        "candidate_index": index,
                        "candidate_count": len(configs),
                        "model_name": name,
                        "algorithm": algorithm,
                        "display_name": info["display_name"],
                        "selected_models": [str(c.get("name")) for c in configs],
                    },
                    "metrics": [],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        def on_progress(row: dict[str, Any]) -> None:
            candidate_history.append(dict(row))
            _write_live_candidate_metrics(
                {
                    "run_id": run_id,
                    "model_name": name,
                    "algorithm": algorithm,
                    "display_name": info["display_name"],
                    "behavior_action_mode": info["behavior_action_mode"],
                    "research_warning": info.get("research_warning"),
                    "learning_rate": learning_rate,
                    "gamma": gamma,
                    "batch_size": batch_size,
                    "max_epochs": max_epochs,
                    "min_epochs": min_epochs,
                    "patience": patience,
                    "min_delta": min_delta,
                    "stability_window": stability_window,
                    "stability_tolerance": stability_tolerance,
                },
                candidate_history,
                {
                    "actual_epochs": row.get("epoch"),
                    "best_epoch": row.get("best_epoch"),
                    "total_updates_used": row.get("total_updates"),
                    "updates_per_epoch": row.get("updates_per_epoch"),
                    "max_total_updates": max_epochs * max(1, int(row.get("updates_per_epoch") or 0)),
                    "stopping_reason": row.get("stopping_reason"),
                },
                index,
                len(configs),
            )

        model, result = train(
            train_csv=train_csv,
            validation_csv=validation_csv,
            epochs=max_epochs,
            min_epochs=min_epochs,
            patience=patience,
            min_delta=min_delta,
            stability_window=stability_window,
            stability_tolerance=stability_tolerance,
            batch_size=batch_size,
            learning_rate=learning_rate,
            gamma=gamma,
            target_update=target_update,
            seed=seed + index - 1,
            checkpoint_path=str(candidate_path),
            progress_callback=on_progress,
            algorithm=algorithm,
        )

        # Ensure the final candidate state is persisted even if the last
        # callback was not emitted after an externally requested stop.
        if result.get("metrics"):
            candidate_history = [dict(item) for item in result["metrics"]]
            _write_live_candidate_metrics(
                {
                    "run_id": run_id,
                    "model_name": name,
                    "algorithm": algorithm,
                    "display_name": info["display_name"],
                    "behavior_action_mode": info["behavior_action_mode"],
                    "research_warning": info.get("research_warning"),
                    "learning_rate": learning_rate,
                    "gamma": gamma,
                    "batch_size": batch_size,
                    "max_epochs": max_epochs,
                    "min_epochs": min_epochs,
                    "patience": patience,
                    "min_delta": min_delta,
                    "stability_window": stability_window,
                    "stability_tolerance": stability_tolerance,
                },
                candidate_history,
                result,
                index,
                len(configs),
            )

        candidate = {
            "run_id": run_id,
            "name": name,
            "algorithm": algorithm,
            "display_name": info["display_name"],
            "behavior_action_mode": info["behavior_action_mode"],
            "research_warning": info.get("research_warning"),
            "learning_rate": learning_rate,
            "gamma": gamma,
            "batch_size": batch_size,
            "actual_epochs": int(result.get("actual_epochs", 0)),
            "best_epoch": int(result.get("best_epoch", 0)),
            "best_validation": result.get("best_validation") or {},
            "validation_score": _score({"best_validation": result.get("best_validation") or {}}),
            "model_path": str(candidate_path),
            "stopping_reason": result.get("stopping_reason"),
            "status": "trained",
        }

        cycle = start_new_live_cycle(
            reason=f"model_candidate_{index}",
            metadata={
                "run_id": run_id,
                "model_name": name,
                "algorithm": algorithm,
                "candidate_index": index,
                "candidate_count": len(configs),
            },
        )
        shutil.copy2(candidate_path, MODEL_PATH)
        candidate_meta = ensure_model_version(
            model_path=MODEL_PATH,
            model_name=info["display_name"],
            extra={
                "run_id": run_id,
                "algorithm": algorithm,
                "candidate_index": index,
                "candidate_count": len(configs),
                "best_epoch": candidate["best_epoch"],
                "actual_epochs": candidate["actual_epochs"],
                "learning_rate": learning_rate,
                "decision_cycle_id": cycle["cycle_id"],
                "behavior_action_mode": info["behavior_action_mode"],
            },
        )
        live = run_live_inference(
            model_path=str(candidate_path),
            model_name=algorithm,
            only_uninferred=True,
        )
        candidate["model_version"] = candidate_meta.get("model_version")
        candidate["live_cycle_id"] = cycle["cycle_id"]
        candidate["live_inference"] = live
        comparison_records.append(candidate)
        comparison_records.sort(
            key=lambda item: float(item.get("validation_score", 0.0)),
            reverse=True,
        )
        _write_comparison(comparison_records, comparison_records[0], "running")
        COMPARISON_PATH.write_text(
            json.dumps(
                {
                    "status": "running",
                    "run_id": run_id,
                    "selected_models": [str(c.get("name")) for c in configs],
                    "candidates": comparison_records,
                    "best": comparison_records[0],
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        (EXPERIMENTS_DIR / f"{run_id}__{name}.training.json").write_text(
            json.dumps(result, indent=2, default=str),
            encoding="utf-8",
        )
        (EXPERIMENTS_DIR / f"{run_id}__{name}.live.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "cycle": cycle,
                    "inference": live,
                    "model": candidate_meta,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        print(
            f"[LIVE] {name}: cycle={cycle.get('cycle_id')} "
            f"processed={live.get('alerts_processed', 0)} "
            f"human_review={live.get('human_review_routed', 0)}"
        )
        del model

    if not comparison_records:
        raise RuntimeError("No model candidates completed.")

    best = comparison_records[0]
    best_path = Path(best["model_path"])
    shutil.copy2(best_path, MODEL_PATH)
    final_cycle = start_new_live_cycle(
        reason="champion_model",
        metadata={
            "run_id": run_id,
            "winner": best["name"],
            "algorithm": best["algorithm"],
            "selection_score": best["validation_score"],
        },
    )
    champion_meta = ensure_model_version(
        model_path=MODEL_PATH,
        model_name=best["display_name"],
        extra={
            "run_id": run_id,
            "algorithm": best["algorithm"],
            "winner_name": best["name"],
            "selection_score": best["validation_score"],
            "best_epoch": best["best_epoch"],
            "actual_epochs": best["actual_epochs"],
            "decision_cycle_id": final_cycle["cycle_id"],
            "behavior_action_mode": best["behavior_action_mode"],
        },
    )
    champion_live = run_live_inference(
        model_path=str(MODEL_PATH),
        model_name=best["algorithm"],
        only_uninferred=True,
    )
    champion = {
        **best,
        "status": "CHAMPION",
        "model_version": champion_meta.get("model_version"),
        "live_cycle_id": final_cycle["cycle_id"],
        "live_inference": champion_live,
    }
    _write_comparison(comparison_records, champion, "selected")
    COMPARISON_PATH.write_text(
        json.dumps(
            {
                "status": "selected",
                "run_id": run_id,
                "selected_models": [str(c.get("name")) for c in configs],
                "candidates": comparison_records,
                "best": champion,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    final_metrics = evaluate(test_csv=test_csv, model_path=str(MODEL_PATH))
    final_metrics["run_id"] = run_id
    final_metrics["algorithm"] = best["algorithm"]
    TEST_METRICS_PATH.write_text(
        json.dumps(final_metrics, indent=2, default=str),
        encoding="utf-8",
    )

    selected_history_path = EXPERIMENTS_DIR / f"{run_id}__{best['name']}.training.json"
    selected_history = json.loads(selected_history_path.read_text(encoding="utf-8"))
    selected_config = selected_history.get("config", {})
    selected_config.update(
        {
            "run_id": run_id,
            "model_name": best["name"],
            "display_name": best["display_name"],
            "algorithm": best["algorithm"],
            "candidate_count": len(comparison_records),
            "selected_models": [str(c.get("name")) for c in configs],
            "selected": True,
            "selection_score": best["validation_score"],
            "selection_rule": "validation only; final unseen test evaluation after champion selection",
            "experiment_mode": "sequential_algorithm_then_live_cycle",
        }
    )
    TRAIN_METRICS_PATH.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "config": selected_config,
                "metrics": selected_history.get("metrics", []),
                "best_epoch": best["best_epoch"],
                "actual_epochs": best["actual_epochs"],
                "best_validation": best["best_validation"],
                "total_updates_used": selected_history.get("total_updates_used"),
                "updates_per_epoch": selected_history.get("updates_per_epoch"),
                "max_total_updates": selected_history.get("max_total_updates"),
                "stopping_reason": best.get("stopping_reason"),
                "model_comparison": comparison_records,
                "champion_model_version": champion_meta.get("model_version"),
                "champion_live_cycle": final_cycle,
                "champion_live_inference": champion_live,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print("\n" + "=" * 78)
    print("SEQUENTIAL EXPERIMENT COMPLETE")
    print(f"Run: {run_id}")
    print(f"Winner: {best['display_name']} ({best['algorithm']})")
    print(f"Champion version: {champion_meta.get('model_version')}")
    print(
        f"Final live processed: {champion_live.get('alerts_processed', 0)} "
        f"/ {champion_live.get('alerts_considered', 0)}"
    )
    print(f"Human review routed: {champion_live.get('human_review_routed', 0)}")
    print("=" * 78)


if __name__ == "__main__":
    main()
