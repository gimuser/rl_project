"""Action model definition.

Lightweight data container used by services and tests.
"""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class Action:
	id: int
	name: str
	params: Dict[str, Any] = field(default_factory=dict)


__all__ = ["Action"]

