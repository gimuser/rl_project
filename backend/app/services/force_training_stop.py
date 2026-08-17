from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RUN_STATE = PROJECT_ROOT / "models" / "training_run.json"


def _training_pids() -> list[int]:
    """Find every live sequential_experiment process, including orphans."""
    try:
        output = subprocess.check_output(
            ["ps", "-eo", "pid=,args="],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []

    pids: list[int] = []
    current_pid = os.getpid()
    for line in output.splitlines():
        line = line.strip()
        if not line or "app.rl_agent.sequential_experiment" not in line:
            continue
        try:
            pid = int(line.split(None, 1)[0])
        except (ValueError, IndexError):
            continue
        if pid != current_pid and pid > 1:
            pids.append(pid)
    return sorted(set(pids))


def _write_state(status: str, *, return_code: int | None = None, message: str = "") -> None:
    payload: dict[str, Any] = {}
    try:
        if RUN_STATE.exists():
            import json
            raw = json.loads(RUN_STATE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                payload.update(raw)
    except Exception:
        pass

    payload.update({
        "status": status,
        "stopped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    if return_code is not None:
        payload["return_code"] = return_code
    if message:
        payload["stop_message"] = message

    RUN_STATE.parent.mkdir(parents=True, exist_ok=True)
    import json
    RUN_STATE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def stop() -> dict[str, Any]:
    """Reliably terminate the actual training process and all managed children."""
    pids = _training_pids()
    terminated: list[int] = []

    for pid in pids:
        try:
            pgid = os.getpgid(pid)
        except ProcessLookupError:
            continue
        except Exception:
            pgid = pid

        try:
            os.killpg(pgid, signal.SIGTERM)
            terminated.append(pid)
        except ProcessLookupError:
            pass
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
                terminated.append(pid)
            except Exception:
                pass

    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline and _training_pids():
        time.sleep(0.15)

    remaining = _training_pids()
    for pid in remaining:
        try:
            pgid = os.getpgid(pid)
        except Exception:
            pgid = pid
        try:
            os.killpg(pgid, signal.SIGKILL)
            terminated.append(pid)
        except Exception:
            try:
                os.kill(pid, signal.SIGKILL)
                terminated.append(pid)
            except Exception:
                pass

    final_remaining = _training_pids()
    code = -signal.SIGTERM if terminated else None
    message = (
        f"Training stop completed; terminated {len(set(terminated))} process(es)."
        if terminated
        else "No active training process was found."
    )
    _write_state("stopped", return_code=code, message=message)

    return {
        "status": "stopped",
        "message": message,
        "terminated_pids": sorted(set(terminated)),
        "remaining_pids": final_remaining,
    }
