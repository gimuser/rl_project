"""TensorBoard helpers.

Provide a tiny wrapper that attempts to use `torch.utils.tensorboard.SummaryWriter`.
If the dependency is missing, a no-op writer is returned so code can call
`add_scalar()` without importing TensorBoard in tests.
"""

from types import SimpleNamespace


def get_writer(log_dir: str = "runs"):
	try:
		from torch.utils.tensorboard import SummaryWriter

		return SummaryWriter(log_dir=log_dir)
	except Exception:
		# no-op fallback
		class Noop:
			def add_scalar(self, *a, **k):
				return None

			def close(self):
				return None

		return Noop()


__all__ = ["get_writer"]

