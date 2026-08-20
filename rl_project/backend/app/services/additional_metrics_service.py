from __future__ import annotations

import json
import math
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database.database import db
from app.services.training_history import list_runs, load_run

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "models"
OUTPUT_PATH = MODELS_DIR / "additional_metrics.json"

alerts_collection = db["live_alerts"]
activity_collection = db["live_alert_activity"]
analysts_collection = db["analysts"]


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(_json_safe(payload), indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _timestamp(value: Any) -> float | None:
    number = _number(value)
    if number is not None:
        return number
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _iqm(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    trim = int(math.floor(len(ordered) * 0.25))
    kept = ordered[trim: len(ordered) - trim] if len(ordered) >= 4 else ordered
    return statistics.mean(kept)


def _bootstrap_mean_ci(values: list[float], reps: int = 10_000, seed: int = 20260818) -> dict[str, Any]:
    if len(values) < 2:
        return {"status": "N/A", "reason": "At least two independent seed results are required."}
    rng = random.Random(seed)
    samples = [statistics.mean([values[rng.randrange(len(values))] for _ in values]) for _ in range(reps)]
    samples.sort()
    return {
        "status": "available",
        "method": "percentile bootstrap",
        "confidence": 0.95,
        "lower": samples[int(0.025 * (len(samples) - 1))],
        "upper": samples[int(0.975 * (len(samples) - 1))],
        "samples": len(values),
        "replications": reps,
    }


def _training_metrics() -> dict[str, Any]:
    return _load_json(MODELS_DIR / "training_metrics.json")


def _current_training() -> dict[str, Any]:
    metrics = _training_metrics()
    config = metrics.get("config") if isinstance(metrics.get("config"), dict) else {}
    history = [x for x in metrics.get("metrics", []) if isinstance(x, dict)]
    returns = [_number(x.get("average_reward", x.get("policy_reward"))) for x in history]
    returns = [x for x in returns if x is not None]
    last_10 = returns[-10:]
    threshold = _number(config.get("target_reward_threshold"))
    reached = None
    if threshold is not None:
        for point in history:
            reward = _number(point.get("average_reward", point.get("policy_reward")))
            if reward is not None and reward >= threshold:
                reached = point
                break
    return {
        "run_id": metrics.get("run_id") or config.get("run_id"),
        "algorithm": config.get("algorithm") or metrics.get("algorithm"),
        "seed": config.get("seed"),
        "evaluation_points": len(returns),
        "last_10_evaluation_returns": last_10,
        "mean_final_return_last_10": statistics.mean(last_10) if last_10 else None,
        "iqm_last_10": _iqm(last_10),
        "final_return": last_10[-1] if last_10 else None,
        "steps_to_threshold": ({
            "status": "available",
            "epoch": reached.get("epoch"),
            "updates": reached.get("total_updates", reached.get("updates")),
        } if reached else {
            "status": "N/A",
            "reason": "No target_reward_threshold was configured or the threshold was not reached."
        }),
        "best_epoch": metrics.get("best_epoch"),
        "actual_epochs": metrics.get("actual_epochs"),
        "total_updates_used": metrics.get("total_updates_used"),
    }


def _seed_results() -> list[dict[str, Any]]:
    results = []
    for run in list_runs():
        run_id = str(run.get("run_id") or "")
        if not run_id:
            continue
        loaded = load_run(run_id)
        if not loaded:
            continue
        training = ((loaded.get("results") or {}).get("training") or {})
        history = training.get("history") if isinstance(training.get("history"), list) else []
        values = [_number(x.get("avg_reward", x.get("policy_reward"))) for x in history if isinstance(x, dict)]
        values = [x for x in values if x is not None]
        if values and training.get("seed") is not None:
            results.append({
                "run_id": run_id,
                "algorithm": training.get("algorithm") or run.get("algorithm"),
                "seed": training.get("seed"),
                "final_return": values[-1],
                "mean_last_10": statistics.mean(values[-10:]),
            })
    return results


def _academic_metrics() -> dict[str, Any]:
    current = _current_training()
    seeds = _seed_results()
    unique_seeds = {str(x["seed"]) for x in seeds}
    final_values = [float(x["final_return"]) for x in seeds]
    return {
        "mean_final_return_last_10": current["mean_final_return_last_10"],
        "iqm_last_10": current["iqm_last_10"],
        "per_seed_final_return": seeds,
        "stratified_bootstrap_ci_95": _bootstrap_mean_ci(final_values),
        "steps_to_threshold": current["steps_to_threshold"],
        "performance_profile": ({
            "status": "available",
            "seed_count": len(unique_seeds),
            "values": final_values,
            "definition": "fraction of seed runs reaching each return threshold",
        } if len(unique_seeds) >= 2 else {
            "status": "N/A",
            "reason": "Requires multiple independent seeds/configurations."
        }),
        "ablation_effect": {
            "status": "N/A",
            "reason": "No matched full-vs-ablated experiment identifier is persisted."
        },
        "note": "No synthetic seed values are created. IQM over the last ten evaluations is reported as a within-run diagnostic; seed-level CI requires independent seeds."
    }


def _events(alert_id: str) -> list[dict[str, Any]]:
    return list(activity_collection.find({"alert_id": alert_id}, {"_id": 0}).sort("timestamp", 1))


def _ground_truth(alert: dict[str, Any]) -> str | None:
    for obj in (alert.get("source") or {}, alert.get("lineage") or {}, alert):
        for key in ("IncidentGrade", "incident_grade", "ground_truth", "GroundTruth"):
            value = obj.get(key)
            if value not in (None, "", "nan", "NaN"):
                return str(value)
    return None


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _latency_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"status": "N/A", "count": 0}
    return {
        "status": "available",
        "count": len(values),
        "mean_seconds": statistics.mean(values),
        "median_seconds": statistics.median(values),
        "p95_seconds": _percentile(values, 0.95),
        "max_seconds": max(values),
        "min_seconds": min(values),
    }


def _analyst_workload() -> dict[str, Any]:
    analysts = list(analysts_collection.find({"active": True}, {"_id": 0}))
    items = []
    loads = []
    for analyst in analysts:
        analyst_id = str(analyst.get("analyst_id"))
        capacity = int(analyst.get("capacity", 0) or 0)
        load = alerts_collection.count_documents({
            "assigned_analyst": analyst_id,
            "status": {"$in": ["HUMAN_REVIEW_PENDING", "ESCALATED", "OPEN"]},
        })
        utilization = load / capacity if capacity else None
        items.append({"analyst_id": analyst_id, "load": load, "capacity": capacity, "utilization": utilization})
        loads.append(load)
    return {
        "status": "available" if analysts else "N/A",
        "analysts": items,
        "average_load": statistics.mean(loads) if loads else None,
        "load_variance": statistics.pvariance(loads) if len(loads) > 1 else (0.0 if loads else None),
        "maximum_utilization": max((x["utilization"] for x in items if x["utilization"] is not None), default=None),
    }


def _operational_metrics() -> dict[str, Any]:
    alerts = list(alerts_collection.find({}, {"_id": 0}))
    latencies: list[float] = []
    processing: list[float] = []
    responses: list[float] = []
    action_counts: dict[str, int] = {}
    confusion = {"tp": 0, "tn": 0, "fp": 0, "fn": 0, "abstain_true_positive": 0, "abstain_negative": 0}
    complete = 0

    for alert in alerts:
        alert_id = str(alert.get("alert_id"))
        events = _events(alert_id)
        imported = next((x for x in events if x.get("action") == "ALERT_IMPORTED"), None)
        inferred = next((x for x in events if x.get("action") == "AGENT_INFERENCE"), None)
        if not imported or not inferred:
            continue
        received = _timestamp(imported.get("timestamp"))
        decision = _timestamp(inferred.get("timestamp"))
        if received is None or decision is None:
            continue
        latencies.append(max(0.0, decision - received))
        details = inferred.get("details") or {}
        action = str(details.get("action") or alert.get("agent", {}).get("action") or "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1

        human = next((x for x in events if str(x.get("action", "")).startswith("HUMAN_")), None)
        terminal = _timestamp(human.get("timestamp")) if human else decision
        if terminal is not None:
            elapsed = max(0.0, terminal - received)
            processing.append(elapsed)
            responses.append(elapsed)
        complete += 1

        truth = _ground_truth(alert)
        positive = truth == "TruePositive"
        if action == "human_review":
            confusion["abstain_true_positive" if positive else "abstain_negative"] += 1
        elif action == "block":
            confusion["tp" if positive else "fp"] += 1
        elif action == "allow":
            confusion["fn" if positive else "tn"] += 1

    tp, tn, fp, fn = confusion["tp"], confusion["tn"], confusion["fp"], confusion["fn"]
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else None
    total = len(alerts)
    review_count = action_counts.get("human_review", 0)
    automated = action_counts.get("allow", 0) + action_counts.get("block", 0)
    live_meta = _load_json(MODELS_DIR / "live_inference.json")
    duration = _number(live_meta.get("duration_seconds"))
    throughput = total / duration if duration and duration > 0 else None
    p95 = _percentile(latencies, 0.95)

    return {
        "alerts_total": total,
        "alerts_with_complete_timing": complete,
        "decision_latency_seconds": _latency_summary(latencies),
        "mean_alert_processing_time_seconds": statistics.mean(processing) if processing else None,
        "mttr_seconds": statistics.mean(responses) if responses else None,
        "mttr_scope": "Automatic decisions use decision timestamp; human-reviewed alerts use the first HUMAN_* event.",
        "throughput_alerts_per_second": throughput,
        "throughput_alerts_per_day_equivalent": throughput * 86400 if throughput is not None else None,
        "target_latency_500ms": {"status": "available" if p95 is not None else "N/A", "observed_p95_seconds": p95, "passes": p95 < 0.5 if p95 is not None else None},
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
        "false_negative_rate": fn / (fn + tp) if fn + tp else None,
        "precision": precision,
        "recall_detection_rate": recall,
        "f1_score": f1,
        "confusion_matrix": confusion,
        "human_review_rate": review_count / total if total else None,
        "automation_rate": automated / total if total else None,
        "action_distribution": action_counts,
        "analyst_workload": _analyst_workload(),
        "analyst_load_reduction": {"status": "N/A", "reason": "No matched manual/baseline workload run is persisted."},
        "playbook_automation_rate": {"status": "N/A", "reason": "No playbook execution event schema is persisted in the current live cycle."},
        "audit_completeness": _audit_completeness(alerts),
        "availability": {"status": "N/A", "reason": "No service-health observation window is persisted for this run."},
        "recovery_time": {"status": "N/A", "reason": "No failure/recovery event pair is persisted for this run."},
        "scalability": {
            "status": "observed_single_cycle",
            "observed_alerts": total,
            "observed_throughput_alerts_per_second": throughput,
            "observed_capacity_10k_per_day": throughput >= (10000 / 86400) if throughput is not None else None,
            "load_test": "N/A — no controlled multi-load stress test was persisted."
        },
    }


def _audit_completeness(alerts: list[dict[str, Any]]) -> dict[str, Any]:
    if not alerts:
        return {"status": "N/A", "total": 0, "complete": 0, "rate": None}
    required = ("alert_id", "incident_id", "agent", "created_at", "updated_at")
    complete = sum(1 for alert in alerts if all(alert.get(key) not in (None, "") for key in required))
    return {"status": "available", "total": len(alerts), "complete": complete, "rate": complete / len(alerts)}


def calculate_additional_metrics(*, persist: bool = True) -> dict[str, Any]:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": _training_metrics().get("run_id"),
        "academic_rl": _academic_metrics(),
        "operational_soc": _operational_metrics(),
        "data_integrity": {"synthetic_values_created": False, "unavailable_metrics_policy": "N/A with reason; never fabricate a value."},
    }
    if persist:
        _write_json(OUTPUT_PATH, payload)
    return payload
