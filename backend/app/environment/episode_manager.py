"""Episode lifecycle helpers.

Simple episode manager to track episode numbers and resets for training.
"""

from typing import Iterator


class EpisodeManager:
	def __init__(self, start: int = 0):
		self.current = start

	def next_episode(self) -> int:
		self.current += 1
		return self.current

	def reset(self):
		self.current = 0

	def __iter__(self) -> Iterator[int]:
		while True:
			yield self.next_episode()


__all__ = ["EpisodeManager"]

