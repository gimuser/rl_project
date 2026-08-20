from __future__ import annotations

from fastapi import APIRouter

from app.services.additional_metrics_service import calculate_additional_metrics

router = APIRouter(prefix="/api/additional-metrics", tags=["Additional Metrics"])


@router.get("")
def get_additional_metrics():
    return calculate_additional_metrics(persist=True)


@router.post("/recalculate")
def recalculate_additional_metrics():
    return calculate_additional_metrics(persist=True)
