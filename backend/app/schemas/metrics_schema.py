"""Schemas for monitoring and metrics endpoints."""

from pydantic import BaseModel
from typing import Dict


class MetricsSummary(BaseModel):
	counters: Dict[str, int]
	gauges: Dict[str, float]


__all__ = ["MetricsSummary"]

