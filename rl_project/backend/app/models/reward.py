"""Reward model definition.

Data container representing a persisted reward record. Note: not a DB ORM,
just a small runtime container used in tests and service code.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional


@dataclass
class RewardRecord:
	id: int
	decision_id: int
	reward_value: float
	metrics: Dict[str, Any] = field(default_factory=dict)
	timestamp: datetime = field(default_factory=datetime.utcnow)
	note: Optional[str] = None


__all__ = ["RewardRecord"]

