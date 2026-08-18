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


def _run_id_from_current() -> str | None:
    run = _load(RUN_STATE)
    if run.get("run_id"):
        return str(run["run_id"])
    metrics = _load(TRAIN_METRICS)
    config = metrics.get("config") if isinstance(metrics.get("config"), dict) else {}
    return str(config["run_id"]) if config.get("run_id") else None


def archive_current_run(reason: str = "superseded_by_new_run") -> str | None:
    run_id = _run_id_from_current()
    if not run_id:
        return None

    metrics = _load(TRAIN_METRICS)
    if not metrics.get("metrics"):
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

    manifest = {
        "run_id": run_id,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "status": (_load(RUN_STATE).get("status") or metrics.get("status") or "completed"),
        "algorithm": (metrics.get("config") or {}).get("algorithm"),
        "display_name": (metrics.get("config") or {}).get("display_name"),
        "actual_epochs": metrics.get("actual_epochs"),
        "best_epoch": metrics.get("best_epoch"),
        "metric_count": len(metrics.get("metrics", [])) if isinstance(metrics.get("metrics"), list) else 0,
        "test_metrics_saved": TEST_METRICS.exists(),
        "comparison_saved": COMPARISON.exists(),
    }
    _write(destination / "manifest.json", manifest)
    return run_id


def _history_from_metrics(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    raw = metrics.get("metrics")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict) and isinstance(item.get("epoch"), (int, float))]


def list_runs() -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    current_id = _run_id_from_current()
    if current_id:
        metrics = _load(TRAIN_METRICS)
        run = _load(RUN_STATE)
        config = metrics.get("config") if isinstance(metrics.get("config"), dict) else {}
        history = _history_from_metrics(metrics)
        runs.append({
            "run_id": current_id,
            "status": run.get("status") or "current",
            "algorithm": config.get("algorithm"),
            "display_name": config.get("display_name"),
            "actual_epochs": metrics.get("actual_epochs") or len(history),
            "best_epoch": metrics.get("best_epoch"),
            "metric_count": len(history),
            "current": True,
        })

    if RUNS_DIR.exists():
        for directory in RUNS_DIR.iterdir():
            if not directory.is_dir():
                continue
            manifest = _load(directory / "manifest.json")
            if not manifest.get("run_id"):
                manifest["run_id"] = directory.name
            manifest["current"] = False
            runs.append(manifest)

    return sorted(runs, key=lambda item: str(item.get("archived_at") or item.get("run_id") or ""), reverse=True)


def load_run(run_id: str) -> dict[str, Any] | None:
    current_id = _run_id_from_current()
    if current_id == run_id:
        return {
            "run_id": run_id,
            "source": "current",
            "training": _load(TRAIN_METRICS),
            "evaluation": _load(TEST_METRICS),
            "comparison": _load(COMPARISON),
            "live_inference": _load(INFERENCE),
            "run_state": _load(RUN_STATE),
            "progress": _load(PROGRESS),
        }

    directory = RUNS_DIR / run_id
    if not directory.exists():
        return None
    return {
        "run_id": run_id,
        "source": "historical",
        "training": _load(directory / "training_metrics.json"),
        "evaluation": _load(directory / "real_test_metrics.json"),
        "comparison": _load(directory / "model_comparison.json"),
        "live_inference": _load(directory / "live_inference.json"),
        "run_state": _load(directory / "training_run.json"),
        "progress": _load(directory / "training_progress.json"),
        "manifest": _load(directory / "manifest.json"),
    }
