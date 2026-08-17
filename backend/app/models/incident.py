"""Incident model definition.

Small container representing an incident derived from an alert.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Incident:
	id: int
	alert_id: int
	status: str = "open"
	created_at: datetime = field(default_factory=datetime.utcnow)
	resolved_at: Optional[datetime] = None
	details: Optional[dict] = None


__all__ = ["Incident"]

