"""Monitoring metrics helpers.

Small in-memory metrics collector useful during development and tests. It
provides counters and gauges and is intentionally thread-unsafe for simplicity.
"""

from typing import Dict


class MetricsCollector:
	def __init__(self):
		self.counters: Dict[str, int] = {}
		self.gauges: Dict[str, float] = {}

	def inc(self, name: str, value: int = 1) -> None:
		self.counters[name] = self.counters.get(name, 0) + int(value)

	def set_gauge(self, name: str, value: float) -> None:
		self.gauges[name] = float(value)

	def get_metrics(self) -> Dict[str, Dict]:
		return {"counters": dict(self.counters), "gauges": dict(self.gauges)}


metrics = MetricsCollector()


__all__ = ["metrics", "MetricsCollector"]

