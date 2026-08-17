#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
MONGO_URI="${MONGO_URI:-mongodb://127.0.0.1:27017}"
PYTHON="${PYTHON:-$(command -v python3 || true)}"
NPM="${NPM:-$(command -v npm || true)}"
BACKEND_PID=""
FRONTEND_PID=""
BACKEND_LOG="/tmp/rl_project_backend.log"
FRONTEND_LOG="/tmp/rl_project_frontend.log"

log() { printf '\n==> %s\n' "$1"; }
die() { printf '\nERROR: %s\n' "$1" >&2; exit 1; }
cleanup() {
  [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

[[ -n "$PYTHON" ]] || die "python3 not found."
[[ -n "$NPM" ]] || die "npm not found."
[[ -f "$ROOT_DIR/backend/main.py" ]] || die "backend/main.py not found."
[[ -f "$ROOT_DIR/frontend/package.json" ]] || die "frontend/package.json not found."

if ss -ltn 2>/dev/null | grep -q ":${BACKEND_PORT} "; then die "Backend port $BACKEND_PORT is already in use."; fi
if ss -ltn 2>/dev/null | grep -q ":${FRONTEND_PORT} "; then die "Frontend port $FRONTEND_PORT is already in use."; fi

if ! "$PYTHON" -c 'import uvicorn' >/dev/null 2>&1; then die "uvicorn is not installed in the selected Python environment."; fi
if ! "$NPM" --version >/dev/null 2>&1; then die "npm is not usable."; fi

if [[ ! -x "$ROOT_DIR/frontend/node_modules/.bin/vite" ]]; then
  log "Installing frontend dependencies"
  (
    cd "$ROOT_DIR/frontend"
    if [[ -f package-lock.json ]]; then "$NPM" ci; else "$NPM" install; fi
  ) || die "Frontend dependency installation failed."
fi

export MONGO_URI
export DATABASE_NAME="soar_rl_agent"
export PYTHONPATH="$ROOT_DIR/backend:$ROOT_DIR"

# ---------------------------------------------------------------------------
# HARD-DATA TRAINING DEFAULTS
# Match the original RL_Agent early-stopping policy while keeping the new
# alert-level streaming implementation RAM-safe.
#
# 4000 = hard upper bound, not a target. The trainer saves the best validation
# checkpoint and stops after the configured patience window, then restores the
# best epoch.
# ---------------------------------------------------------------------------
export REAL_RL_MAX_EPOCHS="${REAL_RL_MAX_EPOCHS:-4000}"
export REAL_RL_MIN_EPOCHS="${REAL_RL_MIN_EPOCHS:-20}"
export REAL_RL_PATIENCE="${REAL_RL_PATIENCE:-10}"
export REAL_RL_EVAL_EVERY="${REAL_RL_EVAL_EVERY:-1}"
export REAL_RL_MIN_DELTA="${REAL_RL_MIN_DELTA:-0.001}"
export REAL_RL_MAX_TOTAL_UPDATES="${REAL_RL_MAX_TOTAL_UPDATES:-5000000}"
export REAL_RL_CHUNK_SIZE="${REAL_RL_CHUNK_SIZE:-50000}"
export REAL_RL_BATCH_SIZE="${REAL_RL_BATCH_SIZE:-512}"
export RL_TORCH_THREADS="${RL_TORCH_THREADS:-2}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-2}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-2}"

# Frontend live-data polling. The Alerts page uses this shared interval.
export VITE_POLL_INTERVAL_MS="${VITE_POLL_INTERVAL_MS:-2000}"

rm -f "$BACKEND_LOG" "$FRONTEND_LOG"

log "Starting FastAPI backend"
"$PYTHON" -m uvicorn backend.main:app \
  --host 127.0.0.1 \
  --port "$BACKEND_PORT" \
  >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

BACKEND_READY=0
for _ in {1..120}; do
  if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    cat "$BACKEND_LOG" >&2 || true
    die "Backend exited before becoming ready."
  fi
  if curl -fsS --connect-timeout 1 --max-time 2 \
    "http://127.0.0.1:$BACKEND_PORT/" >/dev/null 2>&1 || \
     curl -fsS --connect-timeout 1 --max-time 2 \
    "http://127.0.0.1:$BACKEND_PORT/api/training-control" >/dev/null 2>&1; then
    BACKEND_READY=1
    break
  fi
  sleep 0.5
done

[[ "$BACKEND_READY" -eq 1 ]] || {
  tail -n 100 "$BACKEND_LOG" >&2 || true
  die "Backend did not become ready within 60 seconds."
}

log "Backend READY at http://127.0.0.1:$BACKEND_PORT"

log "Starting Vite frontend"
(
  cd "$ROOT_DIR/frontend"
  "$NPM" run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT"
) >"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

FRONTEND_READY=0
for _ in {1..60}; do
  if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    cat "$FRONTEND_LOG" >&2 || true
    die "Frontend exited before becoming ready."
  fi
  if curl -fsS --connect-timeout 1 --max-time 2 \
    "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null 2>&1; then
    FRONTEND_READY=1
    break
  fi
  sleep 0.5
done

[[ "$FRONTEND_READY" -eq 1 ]] || {
  tail -n 100 "$FRONTEND_LOG" >&2 || true
  die "Frontend did not become ready within 30 seconds."
}

cat <<EOF

============================================================
RL_PROJECT READY
============================================================
Backend : http://127.0.0.1:$BACKEND_PORT
Frontend: http://127.0.0.1:$FRONTEND_PORT
MongoDB : $MONGO_URI

Training page:
  http://127.0.0.1:$FRONTEND_PORT/training

Alerts page:
  http://127.0.0.1:$FRONTEND_PORT/alerts

Hard-data training defaults:
  Max epochs       : $REAL_RL_MAX_EPOCHS
  Minimum epochs   : $REAL_RL_MIN_EPOCHS
  Patience         : $REAL_RL_PATIENCE
  Validation every : $REAL_RL_EVAL_EVERY epoch
  Max update cap   : $REAL_RL_MAX_TOTAL_UPDATES
  Chunk size       : $REAL_RL_CHUNK_SIZE
  Batch size       : $REAL_RL_BATCH_SIZE

Frontend polling:
  $VITE_POLL_INTERVAL_MS ms

Backend log : $BACKEND_LOG
Frontend log: $FRONTEND_LOG

Press CTRL+C to stop both services.
============================================================
EOF

wait
