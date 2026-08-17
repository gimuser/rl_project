import asyncio
import time
from typing import Dict
from datetime import datetime
from fastapi import FastAPI, Request
from app.config.settings import settings


def init_api_status_store(app: FastAPI) -> None:
    # Initialize a dict in app.state to hold status for each component
    app.state.api_statuses = {}
    now = time.time()
    for comp in settings.api_components:
        app.state.api_statuses[comp["name"]] = {
            "name": comp["name"],
            "prefix": comp["prefix"],
            "status": "unknown",
            "last_seen": None,
            "last_checked": now,
            "request_count": 0,
        }


async def api_activity_middleware(request: Request, call_next):
    # Update last_seen for the matching component (by prefix)
    path = request.url.path
    for comp in settings.api_components:
        if path.startswith(comp["prefix"]):
            statuses: Dict | None = getattr(request.app.state, "api_statuses", None)
            entry = statuses.get(comp["name"]) if statuses is not None else None
            if entry is not None:
                entry["last_seen"] = time.time()
                entry["status"] = "up"
                entry["request_count"] = entry.get("request_count", 0) + 1
            break

    response = await call_next(request)
    return response


async def api_status_monitor_task(app: FastAPI):
    # Background task that marks components 'down' if not seen recently
    interval = max(1, settings.api_status_poll_interval)
    timeout = max(1, settings.api_status_timeout_seconds)
    from app.database.database import api_statuses_collection  # local import to avoid startup cycles

    while True:
        now = time.time()
        statuses: Dict = getattr(app.state, "api_statuses", {})
        for name, entry in statuses.items():
            last = entry.get("last_seen")

            # Active checks for some components
            try:
                from app.database.database import client, training_collection

                if entry.get("name") == "database":
                    # Active DB ping
                    try:
                        await asyncio.to_thread(client.admin.command, "ping")
                        entry["status"] = "up"
                        entry["last_seen"] = now
                    except Exception:
                        entry["status"] = "down"
                elif entry.get("name") == "training":
                    # Consider training 'up' if the training collection reports running
                    try:
                        status_doc = await asyncio.to_thread(
                            training_collection.find_one,
                            {"type": "status"},
                            sort=[("updated_at", -1)],
                        )
                        if status_doc and status_doc.get("status") == "running":
                            entry["status"] = "up"
                            entry["last_seen"] = now
                        else:
                            # fall back to passive last_seen evaluation below
                            pass
                    except Exception:
                        pass
            except Exception:
                # ignore active-check failures
                pass

            if last is None:
                # Still unknown — mark down only if app has been running for
                # longer than timeout so short-lived startups don't show red.
                if (now - entry.get("last_checked", now)) > timeout:
                    entry["status"] = "down"
            else:
                if (now - last) > timeout:
                    entry["status"] = "down"
                else:
                    entry["status"] = "up"

            entry["last_checked"] = now

            # Persist to DB if enabled
            if getattr(settings, "persist_api_statuses", False):
                try:
                    # Upsert a document per component by name
                    api_statuses_collection.update_one(
                        {"name": entry["name"]},
                        {
                            "$set": {
                                "name": entry["name"],
                                "prefix": entry["prefix"],
                                "status": entry["status"],
                                "last_seen": entry["last_seen"],
                                "last_checked": entry["last_checked"],
                                "request_count": entry.get("request_count", 0),
                                "updated_at": datetime.utcfromtimestamp(entry.get("last_checked", now)),
                            }
                        },
                        upsert=True,
                    )
                except Exception:
                    # Don't fail the monitor on DB errors
                    pass
        await asyncio.sleep(interval)


def start_status_monitor(app: FastAPI):
    if not settings.enable_api_activity_tracking:
        return
    # Start background task after middleware is already attached.
    loop = asyncio.get_event_loop()
    task = loop.create_task(api_status_monitor_task(app))
    app.state.api_status_monitor_task = task


async def stop_status_monitor(app: FastAPI):
    task = getattr(app.state, "api_status_monitor_task", None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
