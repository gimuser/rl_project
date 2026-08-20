"""State model definition.

Container for environment states used by agents and trainers.
"""

from dataclasses import dataclass, field
from typing import List, Any, Dict


@dataclass
class State:
	vector: List[float]
	metadata: Dict[str, Any] = field(default_factory=dict)


__all__ = ["State"]

