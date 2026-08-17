from __future__ import annotations

import csv
import json
import os
import shutil
from pathlib import Path
from typing import Any

from app.services.live_cycle_service import start_new_live_cycle
from app.services.live_inference_service import run_live_inference
from app.services.model_versioning import ensure_model_version

from .evaluator import evaluate
from .hard_data_pipeline import prepare_data_split
from .hard_data_trainer import evaluate_streaming, train_streaming
from .offline_algorithms import algorithm_metadata, get_algorithm
from .real_pipeline import (
    COMPARISON_PATH,
    EXPERIMENTS_DIR,
    MODEL_PATH,
    TEST_METRICS_PATH,
    TRAIN_METRICS_PATH,
    _experiment_configs,
)
from .triage_env import FEATURES


def _int_env(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _float_env(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _run_id() -> str:
    return os.getenv("REAL_RL_RUN_ID", "legacy-run")


def _json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _selection_score(validation: dict[str, Any]) -> float:
    return float(
        0.70 * float(validation.get("policy_optimality", 0.0))
        + 0.30 * float(validation.get("reward_efficiency", 0.0))
    )


def _live_expected_rows() -> int:
    path = Path(__file__).resolve().parents[3] / "data_alert" / "live_source.csv"
    if not path.exists():
        raise FileNotFoundError(f"Live source dataset not found: {path}")
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        return max(0, sum(1 for _ in handle) - 1)


def _run_full_live_cycle(*, run_id: str, champion: dict[str, Any], model_meta: dict[str, Any] | None) -> dict[str, Any]:
    expected = _live_expected_rows()
    if expected <= 0:
        raise RuntimeError("Live source dataset contains zero alerts.")

    cycle = start_new_live_cycle(
        reason="champion_model_full_live_holdout",
        metadata={
            "run_id": run_id,
            "winner": champion["name"],
            "algorithm": champion["algorithm"],
            "expected_live_alerts": expected,
        },
    )

    cycle_id = str(cycle.get("cycle_id") or "")
    if not cycle_id:
        raise RuntimeError("Live cycle was created without a cycle_id.")

    seeded = int(cycle.get("alerts", 0) or 0)
    if seeded != expected:
        raise RuntimeError(f"FATAL: live cycle seeded {seeded} alerts but expected {expected}.")

    result = run_live_inference(
        model_path=str(MODEL_PATH),
        model_name=champion["algorithm"],
        only_uninferred=True,
        cycle_id=cycle_id,
    )

    processed = int(result.get("alerts_processed", 0) or 0)
    considered = int(result.get("alerts_considered", 0) or 0)

    if considered != expected or processed != expected:
        raise RuntimeError(
            "FATAL: full live holdout was not processed: "
            f"expected={expected}, considered={considered}, processed={processed}, cycle={cycle_id}"
        )

    result["expected_live_alerts"] = expected
    result["full_live_holdout"] = True
    result["cycle"] = cycle
    result["model_version"] = (model_meta or {}).get("model_version")
    return result


def main() -> None:
    run_id = _run_id()
    print("=" * 78)
    print("HARD-DATA OFFLINE RL — ALERT-LEVEL STREAMING TRAINING")
    print("NO FULL-DATAFRAME LOAD / INCIDENT-DISJOINT VALIDATION / UNSEEN TEST")
    print(f"RUN ID: {run_id}")
    print("=" * 78)

    split = prepare_data_split()
    train_csv = str(split["train_path"])
    test_csv = str(split["test_path"])
    validation_ids = split["validation_ids"]

    # These defaults are part of the trainer itself, so behavior is identical
    # whether the process is launched through run_local.sh or directly by the API.
    max_epochs = _int_env("REAL_RL_MAX_EPOCHS", 4000)
    min_epochs = _int_env("REAL_RL_MIN_EPOCHS", 20)
    patience = _int_env("REAL_RL_PATIENCE", 10)
    validation_every = _int_env("REAL_RL_EVAL_EVERY", 1)
    min_delta = _float_env("REAL_RL_MIN_DELTA", 1e-3)
    batch_size_default = _int_env("REAL_RL_BATCH_SIZE", 512)
    chunk_size = _int_env("REAL_RL_CHUNK_SIZE", 50_000)
    max_updates_default = _int_env("REAL_RL_MAX_TOTAL_UPDATES", 5_000_000)
    learning_rate_default = _float_env("REAL_RL_LR", 1e-3)
    gamma_default = _float_env("REAL_RL_GAMMA", 0.95)
    seed = _int_env("REAL_RL_SEED", 42)
    target_update = _int_env("REAL_RL_TARGET_UPDATE", 1)

    print(f"Max epochs         : {max_epochs}")
    print(f"Minimum epochs     : {min_epochs}")
    print(f"Patience           : {patience}")
    print(f"Validation every   : {validation_every}")
    print(f"Min delta          : {min_delta}")
    print(f"Max updates        : {max_updates_default:,}")

    configs = _experiment_configs()
    selected_names = [str(c.get("name")) for c in configs]

    comparison_records: list[dict[str, Any]] = []
    _json_write(
        COMPARISON_PATH,
        {
            "status": "running",
            "run_id": run_id,
            "selected_models": selected_names,
            "data_mode": "hard_alert_streaming",
            "candidates": [],
            "best": None,
        },
    )

    for index, config in enumerate(configs, start=1):
        name = str(config.get("name") or f"candidate_{index}")
        algorithm = get_algorithm(str(config.get("algorithm", name))).name
        info = algorithm_metadata(algorithm)
        learning_rate = float(config.get("learning_rate", learning_rate_default))
        gamma = float(config.get("gamma", gamma_default))
        batch_size = int(config.get("batch_size", batch_size_default))
        max_updates = int(config.get("max_total_updates", max_updates_default))

        candidate_path = EXPERIMENTS_DIR / f"{run_id}__{name}.pt"
        training_json = EXPERIMENTS_DIR / f"{run_id}__{name}.training.json"

        print("\n" + "=" * 78)
        print(f"MODEL {index}/{len(configs)}: {info['display_name']}")
        print(f"Algorithm           : {algorithm}")
        print("Dataset mode        : hard_alert_streaming")
        print(f"Validation incidents: {len(validation_ids):,}")
        print(f"Batch size          : {batch_size}")
        print(f"Chunk size          : {chunk_size}")
        print(f"Max epochs          : {max_epochs}")
        print(f"Min epochs          : {min_epochs}")
        print(f"Patience            : {patience}")
        print(f"Max updates         : {max_updates:,}")
        print("=" * 78)

        model, result = train_streaming(
            train_csv=train_csv,
            validation_csv=train_csv,
            validation_ids=validation_ids,
            epochs=max_epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            gamma=gamma,
            target_update=target_update,
            seed=seed + index - 1,
            validation_every=validation_every,
            patience=patience,
            min_epochs=min_epochs,
            min_delta=min_delta,
            max_total_updates=max_updates,
            chunk_size=chunk_size,
            checkpoint_path=str(candidate_path),
            algorithm=algorithm,
        )

        best_validation = result.get("best_validation") or {}
        selection_score = _selection_score(best_validation)

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
            "chunk_size": chunk_size,
            "max_total_updates": max_updates,
            "actual_epochs": int(result.get("actual_epochs", 0)),
            "best_epoch": int(result.get("best_epoch", 0)),
            "best_validation": best_validation,
            "validation_score": selection_score,
            "model_path": str(candidate_path),
            "stopping_reason": result.get("stopping_reason"),
            "status": "trained",
            "data_mode": "hard_alert_streaming",
            "representative_incident_training": False,
            "test_used_for_selection": False,
        }

        comparison_records.append(candidate)
        comparison_records.sort(key=lambda x: float(x.get("validation_score", 0.0)), reverse=True)

        _json_write(training_json, result)
        _json_write(
            COMPARISON_PATH,
            {
                "status": "running",
                "run_id": run_id,
                "selected_models": selected_names,
                "data_mode": "hard_alert_streaming",
                "selection_rule": "0.70 * validation_policy_optimality + 0.30 * validation_reward_efficiency",
                "test_used_for_selection": False,
                "candidates": comparison_records,
                "best": comparison_records[0],
            },
        )

        _json_write(
            TRAIN_METRICS_PATH,
            {
                "run_id": run_id,
                "config": {
                    **result.get("config", {}),
                    "run_id": run_id,
                    "model_name": name,
                    "display_name": info["display_name"],
                    "algorithm": algorithm,
                    "candidate_index": index,
                    "candidate_count": len(configs),
                    "selected_models": selected_names,
                    "data_mode": "hard_alert_streaming",
                    "test_used_for_selection": False,
                    "max_epochs": max_epochs,
                    "min_epochs": min_epochs,
                    "patience": patience,
                    "validation_every": validation_every,
                    "min_delta": min_delta,
                },
                "metrics": result.get("metrics", []),
                "best_epoch": result.get("best_epoch"),
                "actual_epochs": result.get("actual_epochs"),
                "total_updates_used": result.get("total_updates_used"),
                "max_total_updates": result.get("max_total_updates"),
                "stopping_reason": result.get("stopping_reason"),
            },
        )
        del model

    if not comparison_records:
        raise RuntimeError("No model candidates completed.")

    champion = comparison_records[0]
    champion_path = Path(champion["model_path"])

    if not champion_path.exists():
        raise FileNotFoundError(champion_path)

    shutil.copy2(champion_path, MODEL_PATH)

    model_meta = ensure_model_version(
        model_path=MODEL_PATH,
        model_name=champion["display_name"],
        extra={
            "run_id": run_id,
            "algorithm": champion["algorithm"],
            "winner_name": champion["name"],
            "selection_score": champion["validation_score"],
            "best_epoch": champion["best_epoch"],
            "actual_epochs": champion["actual_epochs"],
            "behavior_action_mode": champion["behavior_action_mode"],
            "data_mode": "hard_alert_streaming",
        },
    )

    from .offline_algorithms import build_model

    champion_model = build_model(
        champion["algorithm"],
        input_dim=len(FEATURES),
        n_actions=3,
        learning_rate=champion["learning_rate"],
        gamma=champion["gamma"],
        hidden_dim=128,
    )
    champion_model.load(str(MODEL_PATH))

    final_test = evaluate_streaming(champion_model, test_csv, chunk_size=chunk_size)
    final_test.update(
        {
            "run_id": run_id,
            "algorithm": champion["algorithm"],
            "model_name": champion["display_name"],
            "model_version": (model_meta or {}).get("model_version"),
            "data_mode": "hard_alert_streaming",
            "test_used_for_selection": False,
            "test_is_unseen_incident_holdout": True,
        }
    )
    _json_write(TEST_METRICS_PATH, final_test)

    champion_history_path = EXPERIMENTS_DIR / f"{run_id}__{champion['name']}.training.json"
    champion_history = {}
    if champion_history_path.exists():
        champion_history = json.loads(champion_history_path.read_text(encoding="utf-8"))

    _json_write(
        TRAIN_METRICS_PATH,
        {
            "run_id": run_id,
            "config": {
                **champion_history.get("config", {}),
                "run_id": run_id,
                "model_name": champion["name"],
                "display_name": champion["display_name"],
                "algorithm": champion["algorithm"],
                "selected_models": selected_names,
                "selected": True,
                "selection_score": champion["validation_score"],
                "selection_rule": "validation only; final unseen TEST evaluation after champion selection",
                "data_mode": "hard_alert_streaming",
                "representative_incident_training": False,
                "test_used_for_selection": False,
                "model_version": (model_meta or {}).get("model_version"),
            },
            "metrics": champion_history.get("metrics", []),
            "best_epoch": champion["best_epoch"],
            "actual_epochs": champion["actual_epochs"],
            "best_validation": champion["best_validation"],
            "total_updates_used": champion_history.get("total_updates_used"),
            "max_total_updates": champion["max_total_updates"],
            "stopping_reason": champion["stopping_reason"],
        },
    )

    live_result = _run_full_live_cycle(run_id=run_id, champion=champion, model_meta=model_meta)

    champion_record = {
        **champion,
        "status": "CHAMPION",
        "model_version": (model_meta or {}).get("model_version"),
        "test_metrics": final_test,
        "live_holdout": live_result,
    }

    _json_write(
        COMPARISON_PATH,
        {
            "status": "selected",
            "run_id": run_id,
            "selected_models": selected_names,
            "data_mode": "hard_alert_streaming",
            "selection_rule": "0.70 * validation_policy_optimality + 0.30 * validation_reward_efficiency",
            "test_used_for_selection": False,
            "candidates": comparison_records,
            "best": champion_record,
        },
    )

    print("\n" + "=" * 78)
    print("HARD-DATA TRAINING COMPLETE")
    print(f"CHAMPION            : {champion['display_name']}")
    print(f"VALIDATION SCORE    : {champion['validation_score']:.6f}")
    print(f"TEST ROWS           : {final_test['rows']:,}")
    print(f"TEST INCIDENTS      : {final_test['incidents']:,}")
    print(f"TEST REWARD EFF.    : {final_test['reward_efficiency']:.6f}")
    print(f"TEST OPTIMALITY     : {final_test['policy_optimality']:.6f}")
    print(f"LIVE EXPECTED       : {live_result['expected_live_alerts']}")
    print(f"LIVE PROCESSED      : {live_result['alerts_processed']}")
    print(f"LIVE HUMAN REVIEW   : {live_result['human_review_routed']}")
    print("TEST WAS NOT USED FOR MODEL SELECTION")
    print("LIVE HOLDOUT USED CHAMPION ONLY")
    print("=" * 78)


if __name__ == "__main__":
    main()
