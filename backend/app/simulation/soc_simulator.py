"""SOC simulator entrypoint.

Provides a tiny simulator that yields synthetic alerts for local testing and
end-to-end flows. The simulator is deterministic-enough for demos and keeps
dependencies minimal.
"""

import random
from typing import Dict, Generator


def alert_generator(count: int = 10) -> Generator[Dict, None, None]:
	"""Yield a stream of synthetic alerts."""
	categories = ["auth", "network", "malware"]
	sources = ["fw", "ids", "endpoint"]

	for i in range(1, count + 1):
		yield {
			"id": i,
			"title": f"Synthetic alert {i}",
			"severity": random.choice([1, 2, 3]),
			"category": random.choice(categories),
			"source": random.choice(sources),
			"incident_score": random.random() * 10,
		}


class SocSimulator:
	def __init__(self, total: int = 10):
		self.total = total

	def run(self):
		for alert in alert_generator(self.total):
			yield alert


__all__ = ["alert_generator", "SocSimulator"]

