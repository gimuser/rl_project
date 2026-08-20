#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
MONGO_PORT="${MONGO_PORT:-27017}"
MONGO_URI="${MONGO_URI:-mongodb://127.0.0.1:${MONGO_PORT}}"
MONGO_CONTAINER="${MONGO_CONTAINER:-rl_project_mongo}"
MONGO_VOLUME="${MONGO_VOLUME:-rl_project_mongo_data}"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON_BIN="${PYTHON:-}"
NPM="${NPM:-$(command -v npm || true)}"
BACKEND_PID=""
FRONTEND_PID=""
BACKEND_LOG="/tmp/rl_project_backend.log"
FRONTEND_LOG="/tmp/rl_project_frontend.log"
NPM_LOG="/tmp/rl_project_npm_install.log"

log() { printf '[RL] %s\n' "$1"; }
die() { printf '\n[RL] ERROR: %s\n' "$1" >&2; exit 1; }

cleanup() {
  [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

[[ -f "$ROOT_DIR/backend/main.py" ]] || die "backend/main.py not found."
[[ -f "$ROOT_DIR/frontend/package.json" ]] || die "frontend/package.json not found."
[[ -f "$ROOT_DIR/requirements.txt" ]] || die "requirements.txt not found."

if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done
fi
[[ -n "$PYTHON_BIN" ]] || die "Python 3.10+ is required. Install Python 3 and run ./run_all.sh again."

PYTHON_VERSION="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PYTHON_MAJOR="${PYTHON_VERSION%%.*}"
PYTHON_MINOR="${PYTHON_VERSION##*.}"
if (( PYTHON_MAJOR < 3 || (PYTHON_MAJOR == 3 && PYTHON_MINOR < 10) )); then
  die "Python 3.10+ is required; found Python $PYTHON_VERSION."
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  log "Creating Python virtual environment..."
  "$PYTHON_BIN" -m venv "$VENV_DIR" || die "Could not create Python virtual environment."
fi

PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

log "Installing/verifying Python dependencies..."
"$PIP" install --disable-pip-version-check -q -r "$ROOT_DIR/requirements.txt" || die "Python dependency installation failed."

command -v curl >/dev/null 2>&1 || die "curl is required."
[[ -n "$NPM" ]] || die "npm is required. Install Node.js/npm and run ./run_all.sh again."
"$NPM" --version >/dev/null 2>&1 || die "npm is not usable."

port_pids() {
  local port="$1"
  if command -v fuser >/dev/null 2>&1; then
    fuser -n tcp "$port" 2>/dev/null | tr ' ' '\n' | sed '/^$/d' | sort -u
  else
    ss -ltnp 2>/dev/null | awk -v p=":$port" '$4 == p {match($0,/pid=[0-9]+/); if (RSTART) print substr($0,RSTART+4,RLENGTH-4)}' | sort -u
  fi
}

ensure_port_free_or_project_owned() {
  local port="$1"
  local pids pid args foreign=""
  pids="$(port_pids "$port" || true)"
  [[ -z "$pids" ]] && return 0
  while read -r pid; do
    [[ "$pid" =~ ^[0-9]+$ ]] || continue
    args="$(ps -p "$pid" -o args= 2>/dev/null || true)"
    if [[ "$args" == *"$ROOT_DIR"* ]] || [[ "$args" == *"uvicorn backend.main:app"* ]] || [[ "$args" == *"vite"* && "$args" == *"$ROOT_DIR/frontend"* ]]; then
      kill -TERM "$pid" >/dev/null 2>&1 || true
    else
      foreign+=" PID $pid ($args)"
    fi
  done <<< "$pids"
  sleep 1
  pids="$(port_pids "$port" || true)"
  if [[ -n "$foreign" ]]; then
    die "Port $port is already used by another application:$foreign. Stop it or set a different project port."
  fi
  if [[ -n "$pids" ]]; then
    while read -r pid; do [[ "$pid" =~ ^[0-9]+$ ]] && kill -KILL "$pid" >/dev/null 2>&1 || true; done <<< "$pids"
  fi
}

ensure_mongodb() {
  if "$PYTHON" - "$MONGO_PORT" <<'PY' >/dev/null 2>&1
import socket, sys
port = int(sys.argv[1])
s = socket.socket()
s.settimeout(0.5)
try:
    s.connect(("127.0.0.1", port))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
  then
    log "MongoDB is already reachable on 127.0.0.1:${MONGO_PORT}."
    return 0
  fi

  if ! command -v docker >/dev/null 2>&1; then
    die "MongoDB is not reachable on 127.0.0.1:${MONGO_PORT}, and Docker is not installed. Install MongoDB or Docker, then rerun."
  fi
  if ! docker info >/dev/null 2>&1; then
    die "MongoDB is not reachable and the Docker daemon is not running. Start Docker, then rerun."
  fi

  if docker ps -a --format '{{.Names}}' | grep -qx "$MONGO_CONTAINER"; then
    log "Starting existing project MongoDB container..."
    docker start "$MONGO_CONTAINER" >/dev/null 2>&1 || die "Could not start MongoDB container '$MONGO_CONTAINER'."
  else
    log "Starting project MongoDB container..."
    docker volume inspect "$MONGO_VOLUME" >/dev/null 2>&1 || docker volume create "$MONGO_VOLUME" >/dev/null
    docker run -d --name "$MONGO_CONTAINER" \
      -p "127.0.0.1:${MONGO_PORT}:27017" \
      -v "${MONGO_VOLUME}:/data/db" \
      --restart unless-stopped mongo:6.0 >/dev/null || die "Could not start MongoDB container."
  fi

  for _ in {1..60}; do
    if "$PYTHON" - "$MONGO_PORT" <<'PY' >/dev/null 2>&1
import socket, sys
port = int(sys.argv[1])
s = socket.socket(); s.settimeout(0.5)
try:
    s.connect(("127.0.0.1", port))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
    then return 0; fi
    sleep 0.5
  done
  die "MongoDB container started but port ${MONGO_PORT} did not become reachable within 30 seconds."
}

ensure_port_free_or_project_owned "$BACKEND_PORT"
ensure_port_free_or_project_owned "$FRONTEND_PORT"
ensure_mongodb

# Remove only stale project training workers, preventing false 409/conflict states.
STALE_TRAINING_PIDS="$(ps -eo pid=,args= 2>/dev/null | awk '/app\.rl_agent\.sequential_experiment/ && !/awk/ {print $1}')"
if [[ -n "$STALE_TRAINING_PIDS" ]]; then
  while read -r pid; do [[ "$pid" =~ ^[0-9]+$ ]] && kill -TERM "$pid" >/dev/null 2>&1 || true; done <<< "$STALE_TRAINING_PIDS"
  sleep 1
fi

# Frontend dependencies: prefer reproducible npm ci, then recover with npm install.
if [[ ! -x "$ROOT_DIR/frontend/node_modules/.bin/vite" ]]; then
  : > "$NPM_LOG"
  (
    cd "$ROOT_DIR/frontend"
    if [[ -f package-lock.json ]]; then
      "$NPM" ci >"$NPM_LOG" 2>&1 || "$NPM" install >"$NPM_LOG" 2>&1
    else
      "$NPM" install >"$NPM_LOG" 2>&1
    fi
  ) || { tail -n 80 "$NPM_LOG" >&2 || true; die "Frontend dependency installation failed."; }
fi

export MONGO_URI
export DATABASE_NAME="soar_rl_agent"
export PYTHONPATH="$ROOT_DIR/backend:$ROOT_DIR"
export REAL_RL_MAX_EPOCHS="${REAL_RL_MAX_EPOCHS:-4000}"
export REAL_RL_MIN_EPOCHS="${REAL_RL_MIN_EPOCHS:-20}"
export REAL_RL_PATIENCE="${REAL_RL_PATIENCE:-10}"
export REAL_RL_EVAL_EVERY="${REAL_RL_EVAL_EVERY:-2}"
export REAL_RL_MIN_DELTA="${REAL_RL_MIN_DELTA:-0.001}"
export REAL_RL_MAX_TOTAL_UPDATES="${REAL_RL_MAX_TOTAL_UPDATES:-5000000}"
export REAL_RL_CHUNK_SIZE="${REAL_RL_CHUNK_SIZE:-100000}"
export REAL_RL_BATCH_SIZE="${REAL_RL_BATCH_SIZE:-2048}"
export RL_TORCH_THREADS="${RL_TORCH_THREADS:-4}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-4}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-4}"
export VITE_POLL_INTERVAL_MS="${VITE_POLL_INTERVAL_MS:-2000}"

rm -f "$BACKEND_LOG" "$FRONTEND_LOG"

log "Starting backend..."
"$PYTHON" -m uvicorn backend.main:app --host 127.0.0.1 --port "$BACKEND_PORT" >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

BACKEND_READY=0
for _ in {1..120}; do
  if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    tail -n 100 "$BACKEND_LOG" >&2 || true
    die "Backend exited before becoming ready."
  fi
  if curl -fsS --connect-timeout 1 --max-time 2 "http://127.0.0.1:$BACKEND_PORT/" >/dev/null 2>&1; then
    BACKEND_READY=1
    break
  fi
  sleep 0.5
done
[[ "$BACKEND_READY" -eq 1 ]] || { tail -n 100 "$BACKEND_LOG" >&2 || true; die "Backend did not become ready within 60 seconds."; }

log "Starting frontend..."
(
  cd "$ROOT_DIR/frontend"
  "$NPM" run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT"
) >"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

FRONTEND_READY=0
for _ in {1..60}; do
  if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    tail -n 100 "$FRONTEND_LOG" >&2 || true
    die "Frontend exited before becoming ready."
  fi
  if curl -fsS --connect-timeout 1 --max-time 2 "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null 2>&1; then
    FRONTEND_READY=1
    break
  fi
  sleep 0.5
done
[[ "$FRONTEND_READY" -eq 1 ]] || { tail -n 100 "$FRONTEND_LOG" >&2 || true; die "Frontend did not become ready within 30 seconds."; }

# Open the application with the user's default desktop browser when supported.
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://127.0.0.1:${FRONTEND_PORT}" >/dev/null 2>&1 &
  log "Opened the frontend with the default browser."
else
  log "Default browser launcher (xdg-open) is unavailable."
fi

printf '\n==============================================\n'
printf ' SOAR-RL-Agent is ready\n'
printf ' Backend : http://127.0.0.1:%s\n' "$BACKEND_PORT"
printf ' Frontend: http://127.0.0.1:%s\n' "$FRONTEND_PORT"
printf '==============================================\n\n'

wait
