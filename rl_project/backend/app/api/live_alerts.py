from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.live_alert_service import (
    activity_collection,
    agent_status,
    analysts_workload,
    assign_alert,
    get_alert,
    get_history,
    get_system_status,
    list_alerts,
    review_alert,
    seed_live_alerts,
)
from app.services.live_inference_service import get_inference_status, run_live_inference
from app.services.model_versioning import get_current_model_version

router = APIRouter(prefix="/api", tags=["Live Alert Operations"])


class ReviewPayload(BaseModel):
    analyst_id: str = Field(default="SA", min_length=1)
    decision: str = Field(min_length=1)
    comment: str = ""
    action: str | None = None


class AssignPayload(BaseModel):
    analyst_id: str = Field(min_length=1)


class InferencePayload(BaseModel):
    confidence_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    margin_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    only_uninferred: bool = True


@router.get("/system/live-status")
def live_system_status():
    return get_system_status()


@router.get("/live-alerts")
def live_alerts(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    search: str | None = None,
    severity: str | None = None,
):
    return list_alerts(skip=skip, limit=limit, search=search, severity=severity)


@router.get("/live-alerts/{alert_id}")
def live_alert(alert_id: str):
    document = get_alert(alert_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    document["history"] = get_history(alert_id)
    return document


@router.get("/live-alerts/{alert_id}/history")
def live_alert_history(alert_id: str):
    if get_alert(alert_id) is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    items = get_history(alert_id)
    return {"items": items, "history": items, "total": len(items)}


@router.get("/live-activity")
def live_activity(limit: int = Query(default=200, ge=1, le=500)):
    items = list(activity_collection.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit))
    return {"items": items, "activity": items, "total": len(items)}


@router.get("/live-decisions")
def live_decisions(
    limit: int = Query(default=100, ge=1, le=500),
    cycle_id: str | None = None,
):
    """Return the agent's decisions from the latest live inference cycle.

    This is intentionally separate from the legacy /api/decisions collection:
    live inference persists its authoritative decisions in live_alert_activity
    together with model, confidence, uncertainty, and cycle lineage.
    """
    if cycle_id is None:
        latest = activity_collection.find_one(
            {"action": "AGENT_INFERENCE"},
            {"_id": 0, "cycle_id": 1, "decision_cycle_id": 1, "timestamp": 1},
            sort=[("timestamp", -1)],
        )
        cycle_id = (latest or {}).get("cycle_id") or (latest or {}).get("decision_cycle_id")

    if not cycle_id:
        return {"items": [], "total": 0, "cycle_id": None, "summary": {}}

    events = list(
        activity_collection.find(
            {"action": "AGENT_INFERENCE", "$or": [{"cycle_id": cycle_id}, {"decision_cycle_id": cycle_id}]},
            {"_id": 0},
        ).sort("timestamp", -1).limit(limit)
    )

    items = []
    counts = {"allow": 0, "block": 0, "human_review": 0}
    for event in events:
        details = event.get("details") or {}
        action = str(details.get("action") or "unknown")
        counts[action] = counts.get(action, 0) + 1
        alert = get_alert(str(event.get("alert_id"))) or {}
        agent = alert.get("agent") or {}
        items.append(
            {
                "decision_id": f"{cycle_id}:{event.get('alert_id')}",
                "alert_id": event.get("alert_id"),
                "incident_id": alert.get("incident_id"),
                "action": action,
                "model_action": details.get("model_action") or agent.get("model_action"),
                "confidence": details.get("confidence", agent.get("confidence")),
                "action_margin": details.get("action_margin", agent.get("action_margin")),
                "uncertainty_reason": details.get("uncertainty_reason") or agent.get("uncertainty_reason"),
                "algorithm": details.get("algorithm") or agent.get("algorithm"),
                "model_version": details.get("model_version") or agent.get("model_version"),
                "status": alert.get("status"),
                "assigned_analyst": alert.get("assigned_analyst"),
                "source_category": (alert.get("source") or {}).get("Category"),
                "verdict": (alert.get("source") or {}).get("LastVerdict"),
                "timestamp": event.get("timestamp"),
            }
        )

    return {
        "items": items,
        "total": len(items),
        "cycle_id": cycle_id,
        "summary": {
            "considered": len(items),
            "processed": len(items),
            "action_distribution": counts,
            "human_review": counts.get("human_review", 0),
        },
    }


@router.get("/human-review")
def human_review(limit: int = Query(default=100, ge=1, le=500)):
    result = list_alerts(limit=limit, skip=0)
    items = [item for item in result["items"] if item.get("agent", {}).get("requires_human_review")]
    return {"items": items, "alerts": items, "total": len(items)}


@router.post("/live-alerts/{alert_id}/review")
def human_review_alert(alert_id: str, payload: ReviewPayload):
    try:
        return review_alert(alert_id, payload.analyst_id, payload.decision, payload.comment, payload.action)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Alert not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/live-alerts/{alert_id}/assign")
def assign_live_alert(alert_id: str, payload: AssignPayload):
    try:
        return assign_alert(alert_id, payload.analyst_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Alert not found") from exc


@router.get("/agent/live-status")
def live_agent_status():
    return agent_status()


@router.get("/agent/live-alerts")
def live_agent_alerts(limit: int = Query(default=100, ge=1, le=500)):
    return list_alerts(limit=limit, skip=0)


@router.get("/agent/model")
def live_model():
    return {"model": get_current_model_version(), "inference": get_inference_status()}


@router.get("/agent/inference/status")
def inference_status():
    return get_inference_status()


@router.post("/agent/inference/run")
def inference_run(payload: InferencePayload = InferencePayload()):
    try:
        return run_live_inference(
            confidence_threshold=payload.confidence_threshold,
            margin_threshold=payload.margin_threshold,
            only_uninferred=payload.only_uninferred,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Live inference failed: {exc}") from exc


@router.get("/analysts/live-workload")
def live_analyst_workload():
    return analysts_workload()


@router.get("/analysts")
def live_analysts():
    return analysts_workload()


@router.get("/analysts/pending-alerts")
def analyst_pending_alerts(
    analyst_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
):
    result = list_alerts(limit=limit, skip=0)
    items = [
        item for item in result["items"]
        if item.get("agent", {}).get("requires_human_review")
        and item.get("status") in {"HUMAN_REVIEW_PENDING", "ESCALATED", "OPEN"}
        and (analyst_id is None or item.get("assigned_analyst") == analyst_id)
    ]
    return {"items": items, "alerts": items, "total": len(items)}


@router.get("/analysts/recent-actions")
def analyst_recent_actions(
    limit: int = Query(default=100, ge=1, le=300),
    analyst_id: str | None = None,
):
    query = {"actor": {"$ne": "system"}}
    if analyst_id:
        query["actor"] = analyst_id
    activity_items = list(activity_collection.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit))
    items = [item for item in activity_items if str(item.get("action", "")).startswith(("HUMAN_", "ASSIGNED"))]
    return {"items": items, "actions": items, "total": len(items)}


@router.post("/live-alerts/bootstrap")
def bootstrap_live_alerts():
    return seed_live_alerts(force=True)
