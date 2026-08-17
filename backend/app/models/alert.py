"""Alert model definition.

Simple dataclass for alert objects used in simulations and tests.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Alert:
	id: int
	title: str
	severity: int
	source: str
	timestamp: datetime = field(default_factory=datetime.utcnow)
	metadata: Optional[dict] = None


__all__ = ["Alert"]

