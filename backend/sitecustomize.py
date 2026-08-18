"""Runtime compatibility guard for the local RL control plane.

The training-control service uses ``time.time()`` for live progress telemetry.
Keep the symbol available during interpreter startup so older deployments of
that module cannot crash the training-start endpoint before the service is
fully refreshed.
"""

import builtins
import time as _time

if not hasattr(builtins, "time"):
    builtins.time = _time
