"""Metrics API routes.

Expose runtime metrics collected by the in-memory metrics collector so
the frontend or healthchecks can query counters and gauges.
"""

from fastapi import APIRouter
from app.monitoring.metrics import metrics
from app.schemas.metrics_schema import MetricsSummary

router = APIRouter(prefix="/api/metrics", tags=["Metrics"])


@router.get("", response_model=MetricsSummary)
def get_metrics():
	return MetricsSummary(**metrics.get_metrics())


__all__ = ["router"]

