"""Database session helpers.

Provides a tiny session/context helper that returns the collections in use
by the application. This intentionally keeps behavior simple so tests and
local development (including the in-memory fallback) can use a common API.
"""

from contextlib import contextmanager
from types import SimpleNamespace

from app.database import database as db_module


@contextmanager
def get_db_session():
	"""Yield an object with collection attributes.

	Usage:
		with get_db_session() as session:
			session.alerts.find(...)
	"""
	session = SimpleNamespace(
		alerts=getattr(db_module, "alerts_collection"),
		decisions=getattr(db_module, "decisions_collection"),
		rewards=getattr(db_module, "rewards_collection"),
		evaluations=getattr(db_module, "evaluations_collection"),
		pipeline=getattr(db_module, "pipeline_collection"),
	)
	try:
		yield session
	finally:
		# No-op: underlying client/collections are managed elsewhere
		pass


def get_collections():
	"""Return the collections namespace for quick access outside a context."""
	return SimpleNamespace(
		alerts=getattr(db_module, "alerts_collection"),
		decisions=getattr(db_module, "decisions_collection"),
		rewards=getattr(db_module, "rewards_collection"),
		evaluations=getattr(db_module, "evaluations_collection"),
		pipeline=getattr(db_module, "pipeline_collection"),
	)

