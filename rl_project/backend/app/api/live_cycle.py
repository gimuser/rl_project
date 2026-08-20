from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services.live_cycle_service import archived_cycles, current_cycle, start_new_live_cycle
from app.services.live_inference_service import get_inference_status

router = APIRouter(prefix="/api/live-cycle", tags=["Live Evaluation Cycle"])


class NewCyclePayload(BaseModel):
    reason: str = "manual_refresh"
    metadata: dict = {}


@router.get("")
def get_cycle():
    return {"cycle": current_cycle()}


@router.post("/new")
def new_cycle(payload: NewCyclePayload):
    return start_new_live_cycle(reason=payload.reason, metadata=payload.metadata)


@router.get("/history")
def cycle_history(limit: int = Query(default=20, ge=1, le=100)):
    items = archived_cycles(limit=limit)
    return {"items": items, "cycles": items, "total": len(items)}


@router.get("/inference")
def inference_status():
    return get_inference_status()
