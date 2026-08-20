from fastapi import APIRouter, Request
from time import time
from typing import Any

router = APIRouter(prefix="/api/system", tags=["System Health"])


@router.get("/apis")
def apis_status(request: Request) -> dict[str, Any]:
    """Return the current status of tracked API components.

    Reads the status store populated by the API activity middleware and
    background monitor. If tracking is not enabled, an explanatory message
    is returned.
    """
    statuses = getattr(request.app.state, "api_statuses", None)
    if statuses is None:
        return {"message": "API activity tracking not enabled", "components": []}

    components = []
    now = time()
    for name, entry in statuses.items():
        components.append(
            {
                "name": entry.get("name"),
                "prefix": entry.get("prefix"),
                "status": entry.get("status"),
                "last_seen": entry.get("last_seen"),
                "last_checked": entry.get("last_checked"),
                "request_count": entry.get("request_count", 0),
                "age_seconds": None if entry.get("last_seen") is None else round(now - entry.get("last_seen"), 2),
            }
        )

    return {"components": components}
