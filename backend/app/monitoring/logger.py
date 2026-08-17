"""Monitoring logger helpers.

Provides a module-level logger instance used by monitoring modules. Keeps
configuration lightweight and consistent with the rest of the application.
"""

import logging


logger = logging.getLogger("SOAR-RL-Agent.monitoring")
if not logger.handlers:
	# If the application hasn't configured logging yet, provide a basic
	# console handler so modules using this logger produce useful output.
	handler = logging.StreamHandler()
	formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
	handler.setFormatter(formatter)
	logger.addHandler(handler)
	logger.setLevel(logging.INFO)


__all__ = ["logger"]

