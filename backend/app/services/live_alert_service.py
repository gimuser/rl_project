from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.database.database import db
from app.config.settings import settings

alerts_collection = db["live_alerts"]
activity_collection = db["live_alert_activity"]
review_collection = db["live_alert_reviews"]
analysts_collection = db["analysts"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _records(path: Path) -> list[dict[str, Any]]:
    frame = pd.read_csv(path, low_memory=False)
    return [{k: _json_safe(v) for k, v in row.items()} for row in frame.to_dict(orient="records")]


def _seed_paths() -> tuple[Path, Path, Path]:
    base = settings.project_root / "data_alert"
    return base / "live_source.csv", base / "live_processed.csv", base / "live_mapping.csv"


def ensure_indexes() -> None:
    alerts_collection.create_index("alert_id", unique=True)
    alerts_collection.create_index([("timestamp", -1)])
    alerts_collection.create_index("status")
    alerts_collection.create_index("incident_id")
    alerts_collection.create_index("assigned_analyst")
    alerts_collection.create_index("agent.model_version")
    alerts_collection.create_index("agent.requires_human_review")
    activity_collection.create_index([("alert_id", 1), ("timestamp", -1)])
    review_collection.create_index([("alert_id", 1), ("created_at", -1)])
    review_collection.create_index([("analyst_id", 1), ("created_at", -1)])
    analysts_collection.create_index("analyst_id", unique=True)


def seed_live_alerts(force: bool = False) -> dict[str, Any]:
    ensure_indexes()
    source_path, processed_path, mapping_path = _seed_paths()
    if not source_path.exists() or not processed_path.exists() or not mapping_path.exists():
        return {"seeded": False, "reason": "data_alert files are missing"}
    if alerts_collection.count_documents({}) > 0 and not force:
        return {"seeded": False, "reason": "live alerts already exist"}
    if force:
        alerts_collection.delete_many({})
        activity_collection.delete_many({})
        review_collection.delete_many({})

    source = _records(source_path)
    processed = _records(processed_path)
    mapping = _records(mapping_path)
    processed_by_id = {str(item.get("alert_id")): item for item in processed}
    mapping_by_id = {str(item.get("alert_id")): item for item in mapping}
    now = utc_now()
    docs: list[dict[str, Any]] = []

    for item in source:
        alert_id = str(item.get("alert_id"))
        source_payload = dict(item)
        source_payload.pop("alert_id", None)
        raw_suspicion = source_payload.get("SuspicionLevel")
        severity = str(raw_suspicion) if raw_suspicion not in (None, "", "Unknown") else "medium"
        docs.append(
            {
                "alert_id": alert_id,
                "incident_id": source_payload.get("IncidentId"),
                "timestamp": source_payload.get("Timestamp"),
                "status": "WAITING_INFERENCE",
                "severity": severity,
                "title": f"{source_payload.get('Category', 'Security alert')} / {source_payload.get('LastVerdict', 'Unknown')}",
                "source": source_payload,
                "processed": processed_by_id.get(alert_id, {}),
                "lineage": mapping_by_id.get(alert_id, {}),
                "agent": {
                    "status": "WAITING_INFERENCE",
                    "action": None,
                    "model_action": None,
                    "confidence": None,
                    "q_values": None,
                    "action_probabilities": None,
                    "action_margin": None,
                    "uncertainty_reason": None,
                    "model_version": None,
                    "requires_human_review": False,
                },
                "assigned_analyst": None,
                "created_at": now,
                "updated_at": now,
            }
        )

    if docs:
        alerts_collection.insert_many(docs)

    analysts = [
        {"analyst_id": "SA", "name": "SOC Analyst", "role": "Supervision", "capacity": 10, "active": True},
        {"analyst_id": "analyst-01", "name": "Analyst 01", "role": "Tier 1", "capacity": 10, "active": True},
        {"analyst_id": "analyst-02", "name": "Analyst 02", "role": "Tier 1", "capacity": 10, "active": True},
        {"analyst_id": "analyst-03", "name": "Analyst 03", "role": "Tier 2", "capacity": 8, "active": True},
    ]
    for analyst in analysts:
        analysts_collection.update_one({"analyst_id": analyst["analyst_id"]}, {"$set": analyst}, upsert=True)

    activity_docs = []
    for doc in docs:
        activity_docs.append({
            "alert_id": doc["alert_id"], "actor": "system", "action": "ALERT_IMPORTED",
            "details": {"source": "data_alert/live_source.csv", "processed": "data_alert/live_processed.csv"},
            "timestamp": now,
        })
    if activity_docs:
        activity_collection.insert_many(activity_docs)
    return {"seeded": True, "alerts": len(docs), "timestamp": now.isoformat()}


def list_alerts(limit: int = 100, skip: int = 0, search: str | None = None, severity: str | None = None) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if severity and severity.lower() != "all":
        query["severity"] = {"$regex": f"^{severity}$", "$options": "i"}
    if search:
        regex = {"$regex": search, "$options": "i"}
        query["$or"] = [
            {"alert_id": regex}, {"incident_id": regex}, {"title": regex},
            {"source.Category": regex}, {"source.MitreTechniques": regex}, {"source.LastVerdict": regex},
        ]
    total = alerts_collection.count_documents(query)
    items = list(alerts_collection.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(limit))
    return {"items": items, "total": total, "count": len(items)}


def get_alert(alert_id: str) -> dict[str, Any] | None:
    return alerts_collection.find_one({"alert_id": alert_id}, {"_id": 0})


def get_history(alert_id: str) -> list[dict[str, Any]]:
    return list(activity_collection.find({"alert_id": alert_id}, {"_id": 0}).sort("timestamp", -1).limit(200))


def review_alert(alert_id: str, analyst_id: str, decision: str, comment: str = "", action: str | None = None) -> dict[str, Any]:
    allowed = {
        "approve": "APPROVED", "approved": "APPROVED",
        "allow": "FINAL_ALLOWED", "allowed": "FINAL_ALLOWED",
        "reject": "REJECTED", "rejected": "REJECTED",
        "block": "FINAL_BLOCKED", "blocked": "FINAL_BLOCKED",
        "delete": "DELETED", "deleted": "DELETED",
        "escalate": "ESCALATED", "escalated": "ESCALATED",
        "close": "CLOSED", "closed": "CLOSED",
    }
    normalized = decision.strip().lower()
    if normalized not in allowed:
        raise ValueError(f"Unsupported decision: {decision}")
    current = get_alert(alert_id)
    if current is None:
        raise KeyError(alert_id)
    status = allowed[normalized]
    now = utc_now()
    review_collection.insert_one({
        "alert_id": alert_id,
        "analyst_id": analyst_id,
        "decision": status,
        "comment": comment,
        "action": action or normalized,
        "created_at": now,
    })
    alerts_collection.update_one(
        {"alert_id": alert_id},
        {"$set": {
            "status": status,
            "agent.requires_human_review": False,
            "assigned_analyst": analyst_id,
            "updated_at": now,
            "last_human_decision": {
                "analyst_id": analyst_id, "decision": status, "comment": comment,
                "action": action or normalized, "timestamp": now,
            },
        }},
    )
    activity_collection.insert_one({
        "alert_id": alert_id,
        "actor": analyst_id,
        "action": f"HUMAN_{status}",
        "details": {"comment": comment, "action": action or normalized},
        "timestamp": now,
    })
    return get_alert(alert_id) or {}


def assign_alert(alert_id: str, analyst_id: str) -> dict[str, Any]:
    current = get_alert(alert_id)
    if current is None:
        raise KeyError(alert_id)
    now = utc_now()
    alerts_collection.update_one({"alert_id": alert_id}, {"$set": {"assigned_analyst": analyst_id, "updated_at": now}})
    activity_collection.insert_one({"alert_id": alert_id, "actor": "SA", "action": "ASSIGNED", "details": {"analyst_id": analyst_id}, "timestamp": now})
    return get_alert(alert_id) or {}


def agent_status() -> dict[str, Any]:
    from app.services.model_versioning import get_current_model_version
    from app.services.live_inference_service import get_inference_status
    model_meta = get_current_model_version()
    inference = get_inference_status()
    total = alerts_collection.count_documents({})
    pending = alerts_collection.count_documents({"agent.requires_human_review": True})
    decisions = alerts_collection.count_documents({"agent.status": "INFERRED"})
    return {
        "status": "ONLINE",
        "mode": "LIVE_ALERT_HOLDOUT",
        "training": False,
        "training_status": "NOT_RUNNING",
        "model_status": "READY" if model_meta else "NOT_AVAILABLE",
        "algorithm": (model_meta or {}).get("model_name", "DoubleDQN"),
        "model_version": (model_meta or {}).get("model_version"),
        "policy_metrics": inference.get("summary"),
        "total_alerts": total,
        "agent_decisions": decisions,
        "human_review_pending": pending,
        "confidence": None,
        "environment_health": "HEALTHY",
        "inference_status": inference.get("status"),
        "note": "Live alerts preserve source/processed lineage; the champion model writes decisions to MongoDB.",
    }


def analysts_workload() -> dict[str, Any]:
    analysts = list(analysts_collection.find({"active": True}, {"_id": 0}))
    items: list[dict[str, Any]] = []
    loads: list[int] = []
    for analyst in analysts:
        analyst_id = analyst["analyst_id"]
        load = alerts_collection.count_documents({
            "assigned_analyst": analyst_id,
            "status": {"$in": ["HUMAN_REVIEW_PENDING", "ESCALATED", "OPEN"]},
        })
        capacity = int(analyst.get("capacity", 0))
        item = {**analyst, "load": load, "available": max(capacity - load, 0), "utilization": (load / capacity) if capacity else 0.0}
        items.append(item)
        loads.append(load)
    average = sum(loads) / len(loads) if loads else 0.0
    variance = sum((load - average) ** 2 for load in loads) / len(loads) if loads else 0.0
    return {
        "items": items,
        "average_analyst_load": average,
        "load_variance": variance,
        "most_loaded_analyst": max(items, key=lambda item: item["load"]) if items else None,
        "least_loaded_analyst": min(items, key=lambda item: item["load"]) if items else None,
    }


def get_system_status() -> dict[str, Any]:
    try:
        from app.database.database import client
        client.admin.command("ping")
        database = "Healthy"
    except Exception:
        database = "Offline"
    return {
        "api": "Online",
        "database": database,
        "live_alerts": alerts_collection.count_documents({}),
        "pending_human_review": alerts_collection.count_documents({"agent.requires_human_review": True}),
    }


def bootstrap() -> None:
    ensure_indexes()
    seed_live_alerts()

bootstrap()
