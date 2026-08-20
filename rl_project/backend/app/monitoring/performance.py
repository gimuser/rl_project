"""Performance monitoring helpers.

Provides a simple timer context manager and helper to record timings.
"""

import time
from contextlib import contextmanager
from typing import Dict
from .metrics import metrics


@contextmanager
def timer(name: str):
	start = time.perf_counter()
	try:
		yield
	finally:
		elapsed = time.perf_counter() - start
		# store as a gauge
		metrics.set_gauge(f"timing.{name}", elapsed)


def measure_callable(name: str, func, *args, **kwargs):
	with timer(name):
		return func(*args, **kwargs)


__all__ = ["timer", "measure_callable"]

