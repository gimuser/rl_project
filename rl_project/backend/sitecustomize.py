"""Runtime compatibility guards for the local RL control plane."""

import builtins
import json
import time as _time
from functools import wraps
from pathlib import Path

if not hasattr(builtins, "time"):
    builtins.time = _time


def _install_training_status_telemetry_bridge() -> None:
    """Expose epoch telemetry while a candidate is still running.

    The trainer persists ``run_id`` at the top level of training_metrics.json,
    while the control-plane status reader historically validated
    ``config.run_id``. During a live run that mismatch caused the API to return
    an empty history even though completed epoch metrics were already present.
    """
    try:
        from app.services import authoritative_training_control as control
    except Exception:
        return

    original_status = control.status

    if getattr(original_status, "_telemetry_bridge", False):
        return

    @wraps(original_status)
    def status_with_live_history():
        result = original_status()
        try:
            if result.get("status") != "running":
                return result

            run_id = result.get("run_id")
            training_metrics = control._load_json(control.TRAIN_METRICS) or {}
            persisted_run_id = training_metrics.get("run_id")

            if not run_id or persisted_run_id != run_id:
                return result

            history = control._history()
            if not history:
                return result

            # The trainer stores the real per-epoch action counts as
            # sample_action_distribution. The API history normalizer
            # historically looked only for action_distribution/action_counts,
            # so the frontend received zeros even though actions were real.
            raw_records = training_metrics.get("metrics")
            if isinstance(raw_records, list):
                by_epoch = {
                    item.get("epoch"): item
                    for item in raw_records
                    if isinstance(item, dict) and item.get("epoch") is not None
                }
                for epoch_item in history:
                    raw = by_epoch.get(epoch_item.get("epoch"))
                    if not isinstance(raw, dict):
                        continue
                    distribution = (
                        raw.get("sample_action_distribution")
                        or raw.get("action_distribution")
                        or raw.get("action_counts")
                    )
                    if isinstance(distribution, dict):
                        epoch_item["action_distribution"] = distribution

            results = result.setdefault("results", {})
            training = results.setdefault("training", {})
            training["history"] = history

            config = training_metrics.get("config")
            if isinstance(config, dict):
                for key in (
                    "model_name", "algorithm", "display_name", "candidate_index",
                    "candidate_count", "learning_rate", "epochs", "max_epochs",
                    "min_epochs", "patience", "min_delta", "batch_size",
                    "max_total_updates", "updates_per_epoch", "chunk_size",
                ):
                    if key in config:
                        target_key = "epochs" if key == "max_epochs" else key
                        training[target_key] = config[key]

            for key in (
                "actual_epochs", "best_epoch", "total_updates_used",
                "max_total_updates", "stopping_reason",
            ):
                if key in training_metrics:
                    training[key] = training_metrics[key]

            return result
        except Exception:
            return result

    status_with_live_history._telemetry_bridge = True
    control.status = status_with_live_history


_install_training_status_telemetry_bridge()
