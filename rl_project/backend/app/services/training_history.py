from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "models"
RUNS_DIR = MODELS_DIR / "training_runs"
TRAIN_METRICS = MODELS_DIR / "training_metrics.json"
TEST_METRICS = MODELS_DIR / "real_test_metrics.json"
COMPARISON = MODELS_DIR / "model_comparison.json"
INFERENCE = MODELS_DIR / "live_inference.json"
RUN_STATE = MODELS_DIR / "training_run.json"
PROGRESS = MODELS_DIR / "training_progress.json"
CURRENT_MODEL = MODELS_DIR / "current_model.json"


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _history_from_metrics(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    raw = metrics.get("metrics")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict) and isinstance(item.get("epoch"), (int, float))]


def _run_id_from_current() -> str | None:
    run = _load(RUN_STATE)
    if run.get("run_id"):
        return str(run["run_id"])
    metrics = _load(TRAIN_METRICS)
    config = metrics.get("config") if isinstance(metrics.get("config"), dict) else {}
    return str(config["run_id"]) if config.get("run_id") else None


def _timestamp_value(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _embedded_run_timestamp(metrics: dict[str, Any], run_state: dict[str, Any] | None = None) -> float:
    run_state = run_state or {}
    config = metrics.get("config") if isinstance(metrics.get("config"), dict) else {}
    history = _history_from_metrics(metrics)

    # Prefer the run's own persisted timestamps over filesystem mtimes.
    for source in (metrics, config, run_state):
        for key in ("completed_at", "finished_at", "updated_at", "last_updated_at", "created_at", "started_at"):
            ts = _timestamp_value(source.get(key)) if isinstance(source, dict) else 0.0
            if ts:
                return ts

    # Legacy metric points sometimes contain their own timestamp.
    for point in reversed(history):
        for key in ("completed_at", "finished_at", "updated_at", "timestamp", "created_at"):
            ts = _timestamp_value(point.get(key))
            if ts:
                return ts

    return 0.0


def _path_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _run_sort_timestamp(metrics: dict[str, Any], run_state: dict[str, Any] | None = None, manifest: dict[str, Any] | None = None, fallback: Path | None = None) -> float:
    ts = _embedded_run_timestamp(metrics, run_state)
    if ts:
        return ts
    manifest = manifest or {}
    for key in ("sort_timestamp", "last_updated_at", "archived_at"):
        ts = _timestamp_value(manifest.get(key))
        if ts:
            return ts
    return _path_mtime(fallback) if fallback else 0.0


def archive_current_run(reason: str = "superseded_by_new_run") -> str | None:
    run_id = _run_id_from_current()
    if not run_id:
        return None
    metrics = _load(TRAIN_METRICS)
    history = _history_from_metrics(metrics)
    if not history:
        return None

    destination = RUNS_DIR / run_id
    destination.mkdir(parents=True, exist_ok=True)
    files = {
        "training_metrics.json": TRAIN_METRICS,
        "real_test_metrics.json": TEST_METRICS,
        "model_comparison.json": COMPARISON,
        "live_inference.json": INFERENCE,
        "training_run.json": RUN_STATE,
        "training_progress.json": PROGRESS,
        "current_model.json": CURRENT_MODEL,
    }
    for name, source in files.items():
        if source.exists():
            shutil.copy2(source, destination / name)

    config = metrics.get("config") if isinstance(metrics.get("config"), dict) else {}
    run_state = _load(RUN_STATE)
    sort_timestamp = _run_sort_timestamp(metrics, run_state)
    archive_time = datetime.now(timezone.utc).isoformat()
    manifest = {
        "run_id": run_id,
        "archived_at": archive_time,
        "last_updated_at": datetime.fromtimestamp(sort_timestamp, timezone.utc).isoformat() if sort_timestamp else archive_time,
        "sort_timestamp": sort_timestamp,
        "reason": reason,
        "status": (run_state.get("status") or metrics.get("status") or "completed"),
        "algorithm": config.get("algorithm") or metrics.get("algorithm"),
        "display_name": config.get("display_name") or metrics.get("display_name"),
        "actual_epochs": metrics.get("actual_epochs") or len(history),
        "best_epoch": metrics.get("best_epoch"),
        "metric_count": len(history),
        "test_metrics_saved": TEST_METRICS.exists(),
        "comparison_saved": COMPARISON.exists(),
    }
    _write(destination / "manifest.json", manifest)
    return run_id


def _candidate_from_json(path: Path, metrics: dict[str, Any]) -> dict[str, Any] | None:
    history = _history_from_metrics(metrics)
    if not history:
        return None
    config = metrics.get("config") if isinstance(metrics.get("config"), dict) else {}
    run_id = str(config.get("run_id") or metrics.get("run_id") or path.stem)
    run_state = _load(path.parent / "training_run.json")
    updated_ts = _run_sort_timestamp(metrics, run_state, fallback=path)
    return {
        "run_id": run_id,
        "status": metrics.get("status") or config.get("status") or "completed",
        "algorithm": config.get("algorithm") or metrics.get("algorithm") or history[-1].get("algorithm"),
        "display_name": config.get("display_name") or metrics.get("display_name"),
        "actual_epochs": metrics.get("actual_epochs") or len(history),
        "best_epoch": metrics.get("best_epoch"),
        "metric_count": len(history),
        "current": False,
        "legacy": True,
        "source_path": str(path),
        "sort_timestamp": updated_ts,
        "last_updated_at": datetime.fromtimestamp(updated_ts, timezone.utc).isoformat() if updated_ts else None,
    }


def _legacy_candidates() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if not MODELS_DIR.exists():
        return results
    for path in MODELS_DIR.rglob("*.json"):
        if "training_runs" in path.parts or "__pycache__" in path.parts:
            continue
        if not ("training" in path.name.lower() or "experiment" in path.name.lower()):
            continue
        candidate = _candidate_from_json(path, _load(path))
        if candidate:
            results.append(candidate)
    return results


def list_runs() -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    current_id = _run_id_from_current()
    if current_id:
        metrics = _load(TRAIN_METRICS)
        run = _load(RUN_STATE)
        config = metrics.get("config") if isinstance(metrics.get("config"), dict) else {}
        history = _history_from_metrics(metrics)
        if history:
            updated_ts = _run_sort_timestamp(metrics, run, fallback=TRAIN_METRICS)
            runs.append({
                "run_id": current_id,
                "status": run.get("status") or "current",
                "algorithm": config.get("algorithm") or metrics.get("algorithm"),
                "display_name": config.get("display_name") or metrics.get("display_name"),
                "actual_epochs": metrics.get("actual_epochs") or len(history),
                "best_epoch": metrics.get("best_epoch"),
                "metric_count": len(history),
                "current": True,
                "source_path": str(TRAIN_METRICS),
                "sort_timestamp": updated_ts,
                "last_updated_at": datetime.fromtimestamp(updated_ts, timezone.utc).isoformat() if updated_ts else None,
            })

    if RUNS_DIR.exists():
        for directory in RUNS_DIR.iterdir():
            if not directory.is_dir():
                continue
            manifest = _load(directory / "manifest.json")
            training = _load(directory / "training_metrics.json")
            run_state = _load(directory / "training_run.json")
            if not manifest.get("run_id"):
                manifest["run_id"] = directory.name
            if int(manifest.get("metric_count") or 0) <= 0:
                history = _history_from_metrics(training)
                if not history:
                    continue
                manifest["metric_count"] = len(history)
                manifest["actual_epochs"] = training.get("actual_epochs") or len(history)
                manifest["best_epoch"] = training.get("best_epoch")
            if not manifest.get("sort_timestamp"):
                manifest["sort_timestamp"] = _run_sort_timestamp(training, run_state, manifest, directory / "training_metrics.json")
            if not manifest.get("last_updated_at") and manifest.get("sort_timestamp"):
                manifest["last_updated_at"] = datetime.fromtimestamp(float(manifest["sort_timestamp"]), timezone.utc).isoformat()
            manifest["current"] = False
            manifest["source_path"] = str(directory / "training_metrics.json")
            runs.append(manifest)

    seen = {str(item.get("source_path")) for item in runs if item.get("source_path")}
    for candidate in _legacy_candidates():
        if candidate.get("source_path") not in seen:
            runs.append(candidate)

    return sorted(runs, key=lambda item: (float(item.get("sort_timestamp") or 0.0), str(item.get("run_id") or "")), reverse=True)


def _status_shape(run_id: str, source: str, training: dict[str, Any], evaluation: dict[str, Any], comparison: dict[str, Any], inference: dict[str, Any], run_state: dict[str, Any], progress: dict[str, Any], manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    config = training.get("config") if isinstance(training.get("config"), dict) else {}
    history = _history_from_metrics(training)
    last = history[-1] if history else {}
    status = str(run_state.get("status") or training.get("status") or ("completed" if history else "idle"))
    return {
        "status": status,
        "message": f"Training run {run_id} loaded from {source} persisted telemetry.",
        "started_at": run_state.get("started_at"),
        "pid": run_state.get("pid"),
        "run_id": run_id,
        "results": {
            "source": source,
            "run_id": run_id,
            "training": {
                "run_id": run_id,
                "model_name": config.get("model_name"),
                "algorithm": config.get("algorithm") or training.get("algorithm"),
                "display_name": config.get("display_name") or training.get("display_name"),
                "selected_models": config.get("selected_models", []),
                "learning_rate": config.get("learning_rate"),
                "gamma": config.get("gamma"),
                "epochs": config.get("epochs", config.get("max_epochs")),
                "actual_epochs": training.get("actual_epochs", last.get("epoch")),
                "min_epochs": config.get("min_epochs"),
                "patience": config.get("patience"),
                "min_delta": config.get("min_delta"),
                "validation_every": config.get("validation_every"),
                "batch_size": config.get("batch_size"),
                "chunk_size": config.get("chunk_size"),
                "hidden_dim": config.get("hidden_dim"),
                "target_update": config.get("target_update"),
                "updates_per_epoch": training.get("updates_per_full_pass") or last.get("updates_per_epoch_full_pass"),
                "max_total_updates": training.get("max_total_updates"),
                "total_updates_used": training.get("total_updates_used"),
                "policy_reward": last.get("policy_reward", last.get("average_reward")),
                "oracle_average_reward": last.get("oracle_average_reward"),
                "reward_efficiency": last.get("reward_efficiency"),
                "validation": last.get("validation"),
                "validation_score": last.get("validation_score"),
                "best_epoch": training.get("best_epoch", last.get("best_epoch")),
                "stopping_reason": training.get("stopping_reason") or last.get("stopping_reason"),
                "history": history,
                "progress": progress,
            },
            "comparison": comparison,
            "evaluation": {
                "samples": evaluation.get("rows", evaluation.get("test_rows")),
                "throughput_rows_per_second": evaluation.get("throughput_rows_per_second"),
                "average_reward": evaluation.get("average_reward"),
                "oracle_average_reward": evaluation.get("oracle_average_reward"),
                "policy_optimality": evaluation.get("policy_optimality"),
                "reward_efficiency": evaluation.get("reward_efficiency"),
                "reward_regret": evaluation.get("reward_regret"),
                "action_distribution": evaluation.get("action_distribution"),
                "per_class": evaluation.get("per_class"),
            },
            "live_inference": inference,
            "manifest": manifest,
        },
    }


def load_run(run_id: str) -> dict[str, Any] | None:
    current_id = _run_id_from_current()
    if current_id == run_id:
        return _status_shape(run_id, "current", _load(TRAIN_METRICS), _load(TEST_METRICS), _load(COMPARISON), _load(INFERENCE), _load(RUN_STATE), _load(PROGRESS))

    directory = RUNS_DIR / run_id
    if directory.exists():
        return _status_shape(run_id, "historical", _load(directory / "training_metrics.json"), _load(directory / "real_test_metrics.json"), _load(directory / "model_comparison.json"), _load(directory / "live_inference.json"), _load(directory / "training_run.json"), _load(directory / "training_progress.json"), _load(directory / "manifest.json"))

    for candidate in _legacy_candidates():
        if str(candidate.get("run_id")) != run_id:
            continue
        source = Path(str(candidate["source_path"]))
        return _status_shape(run_id, "legacy", _load(source), {}, {}, {}, _load(source.parent / "training_run.json"), {}, {"legacy": True, "source_path": str(source), "metric_count": candidate.get("metric_count"), "sort_timestamp": candidate.get("sort_timestamp"), "last_updated_at": candidate.get("last_updated_at")})

    return None
