#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = os.environ.get("PYTHON", "python3")
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8000"))
BACKEND_LOG = "/tmp/rl_project_backend.log"
_backend_process: subprocess.Popen[str] | None = None
_lock = threading.Lock()


def _kill_backend_processes() -> None:
    try:
        output = subprocess.check_output(["ps", "-eo", "pid=,args="], text=True)
    except Exception:
        return
    for line in output.splitlines():
        line = line.strip()
        if "uvicorn backend.main:app" not in line or "local_service_launcher" in line:
            continue
        try:
            pid = int(line.split(None, 1)[0])
            os.kill(pid, signal.SIGTERM)
        except (ValueError, ProcessLookupError, PermissionError):
            pass


def _start_backend() -> tuple[bool, str]:
    global _backend_process
    with _lock:
        _kill_backend_processes()
        time.sleep(0.5)
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{ROOT / 'backend'}:{ROOT}"
        env.setdefault("MONGO_URI", "mongodb://127.0.0.1:27017")
        env.setdefault("DATABASE_NAME", "soar_rl_agent")
        try:
            log = open(BACKEND_LOG, "a", encoding="utf-8")
            _backend_process = subprocess.Popen(
                [PYTHON, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
                cwd=str(ROOT),
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
            return True, f"Backend restart requested (PID {_backend_process.pid})."
        except Exception as exc:
            return False, f"Backend start failed: {exc}"


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._json(204, "")

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/status":
            alive = _backend_process is not None and _backend_process.poll() is None
            self._json(200, '{"launcher":"online","backend":"%s"}' % ("running" if alive else "stopped"))
            return
        self._json(404, '{"error":"not found"}')

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/restart-backend":
            ok, message = _start_backend()
            self._json(200 if ok else 500, '{"ok":%s,"message":%r}' % (str(ok).lower(), message))
            return
        self._json(404, '{"error":"not found"}')

    def log_message(self, *_args) -> None:
        return


if __name__ == "__main__":
    port = int(os.environ.get("RL_LAUNCHER_PORT", "8765"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.serve_forever()
