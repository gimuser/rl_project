"""Terminal condition helpers.

Provide a small utility to decide episode termination based on step counts or
other simple criteria. Kept minimal for unit tests and small local runs.
"""

from typing import Dict, Any


def is_terminal(step_count: int, max_steps: int = 100, info: Dict[str, Any] | None = None) -> bool:
	"""Return True when the episode should terminate.

	Additional criteria can be passed in `info` but are optional.
	"""
	if step_count >= max_steps:
		return True

	if info and info.get("done", False):
		return True

	return False


__all__ = ["is_terminal"]

