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
BACKEND_LOG="/tmp/rl_agent_backend.log"
FRONTEND_LOG="/tmp/rl_agent_frontend.log"

<<<<<<< Updated upstream
die() { echo "ERROR: $1" >&2; exit 1; }
=======
BACKEND_LOG="/tmp/rl_agent_backend.log"
FRONTEND_LOG="/tmp/rl_agent_frontend.log"

log() {
    printf '\n==> %s\n' "$1"
}

die() {
    printf '\nERROR: %s\n' "$1" >&2
    exit 1
}

>>>>>>> Stashed changes
cleanup() {
    [[ -n "${FRONTEND_PID:-}" ]] && kill "$FRONTEND_PID" >/dev/null 2>&1 || true
    [[ -n "${BACKEND_PID:-}" ]] && kill "$BACKEND_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

[[ -n "$PYTHON" ]] || die "python3 not found."
[[ -n "$NPM" ]] || die "npm not found."
[[ -f "$ROOT_DIR/backend/main.py" ]] || die "backend/main.py not found."
[[ -f "$ROOT_DIR/frontend/package.json" ]] || die "frontend/package.json not found."

<<<<<<< Updated upstream
if ss -ltn 2>/dev/null | grep -q ":${BACKEND_PORT} "; then
    die "Backend port $BACKEND_PORT is already in use."
fi
if ss -ltn 2>/dev/null | grep -q ":${FRONTEND_PORT} "; then
    die "Frontend port $FRONTEND_PORT is already in use."
fi

if [[ ! -x "$ROOT_DIR/frontend/node_modules/.bin/vite" ]]; then
    (
        cd "$ROOT_DIR/frontend"
        if [[ -f package-lock.json ]]; then "$NPM" ci; else "$NPM" install; fi
    ) || die "Frontend dependency installation failed."
fi

=======
# ------------------------------------------------------------
# BASIC CHECKS
# ------------------------------------------------------------

if [[ -z "$PYTHON" ]]; then
    die "python3 was not found."
fi

if [[ -z "$NPM" ]]; then
    die "npm was not found."
fi

if [[ ! -f "$ROOT_DIR/frontend/package.json" ]]; then
    die "frontend/package.json was not found."
fi

if [[ ! -f "$ROOT_DIR/backend/main.py" ]]; then
    die "backend/main.py was not found."
fi

# ------------------------------------------------------------
# CHECK PORTS BEFORE STARTING
# ------------------------------------------------------------

echo
echo "==> Checking backend port $BACKEND_PORT"

if ss -ltn 2>/dev/null | grep -q ":${BACKEND_PORT} "; then
    echo "WARNING: port $BACKEND_PORT is already in use."
    echo
    ss -ltnp 2>/dev/null | grep ":${BACKEND_PORT} " || true
    die "Backend port $BACKEND_PORT is already occupied."
fi

echo "OK: backend port $BACKEND_PORT is free."

echo
echo "==> Checking frontend port $FRONTEND_PORT"

if ss -ltn 2>/dev/null | grep -q ":${FRONTEND_PORT} "; then
    echo "WARNING: port $FRONTEND_PORT is already in use."
    echo
    ss -ltnp 2>/dev/null | grep ":${FRONTEND_PORT} " || true
    die "Frontend port $FRONTEND_PORT is already occupied."
fi

echo "OK: frontend port $FRONTEND_PORT is free."

# ------------------------------------------------------------
# FRONTEND DEPENDENCIES
# ------------------------------------------------------------

if [[ ! -x "$ROOT_DIR/frontend/node_modules/.bin/vite" ]]; then

    log "Frontend dependencies not found."

    if [[ -f "$ROOT_DIR/frontend/package-lock.json" ]]; then

        log "Running npm ci"

        (
            cd "$ROOT_DIR/frontend"
            "$NPM" ci
        ) || die "npm ci failed."

    else

        log "package-lock.json not found; running npm install"

        (
            cd "$ROOT_DIR/frontend"
            "$NPM" install
        ) || die "npm install failed."

    fi

else

    log "Frontend dependencies already installed."

fi

if [[ ! -x "$ROOT_DIR/frontend/node_modules/.bin/vite" ]]; then
    die "Vite is still unavailable."
fi

# ------------------------------------------------------------
# ENVIRONMENT
# ------------------------------------------------------------

>>>>>>> Stashed changes
export MONGO_URI
export DATABASE_NAME="soar_rl_agent"
export PYTHONPATH="$ROOT_DIR/backend:$ROOT_DIR"

<<<<<<< Updated upstream
rm -f "$BACKEND_LOG" "$FRONTEND_LOG"
=======
log "Python: $PYTHON"
log "npm: $NPM"
log "Backend: http://127.0.0.1:$BACKEND_PORT"
log "Frontend: http://127.0.0.1:$FRONTEND_PORT"
log "MongoDB: $MONGO_URI"

# ------------------------------------------------------------
# BACKEND
# ------------------------------------------------------------

rm -f "$BACKEND_LOG"

echo
echo "==> Starting FastAPI backend..."
>>>>>>> Stashed changes

"$PYTHON" -m uvicorn backend.main:app \
    --host 127.0.0.1 \
    --port "$BACKEND_PORT" \
    >"$BACKEND_LOG" 2>&1 &
<<<<<<< Updated upstream
BACKEND_PID=$!

BACKEND_READY=0
for _ in {1..120}; do
    if curl -fsS --connect-timeout 1 --max-time 2 \
        "http://127.0.0.1:$BACKEND_PORT/" >/dev/null 2>&1; then
        BACKEND_READY=1
        break
    fi
    if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
        cat "$BACKEND_LOG" >&2 || true
        die "Backend exited before becoming ready."
    fi
    sleep 0.5
=======

BACKEND_PID=$!

echo "==> Backend process started (PID=$BACKEND_PID)"
echo "==> Backend log: $BACKEND_LOG"

# ------------------------------------------------------------
# BACKEND READINESS
#
# Give imports / startup considerably more time.
# Maximum: 60 seconds.
# ------------------------------------------------------------

BACKEND_READY=0

echo
echo "==> Waiting for backend..."

for i in {1..120}; do

    # First check whether the process died.
    if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then

        echo
        echo "============================================================"
        echo " BACKEND PROCESS EXITED"
        echo "============================================================"

        echo
        echo "PID: $BACKEND_PID"
        echo "Exit detected after approximately $((i / 2)) seconds."

        echo
        echo "---------------- BACKEND LOG ----------------"
        cat "$BACKEND_LOG" 2>/dev/null || true
        echo "------------------------------------------------"

        die "Backend process exited before becoming ready."

    fi

    # Root endpoint is the simplest FastAPI health check.
    if curl -fsS \
        --connect-timeout 1 \
        --max-time 2 \
        "http://127.0.0.1:$BACKEND_PORT/" \
        >/dev/null 2>&1
    then

        BACKEND_READY=1
        echo
        echo "OK: backend root endpoint is responding."
        break

    fi

    # Also try the training endpoint.
    if curl -fsS \
        --connect-timeout 1 \
        --max-time 2 \
        "http://127.0.0.1:$BACKEND_PORT/api/training-control" \
        >/dev/null 2>&1
    then

        BACKEND_READY=1
        echo
        echo "OK: training-control endpoint is responding."
        break

    fi

    # Show progress every 5 seconds.
    if (( i % 10 == 0 )); then
        echo "   backend still starting... ${i}/120"
    fi

    sleep 0.5

>>>>>>> Stashed changes
done
[[ "$BACKEND_READY" -eq 1 ]] || { tail -n 100 "$BACKEND_LOG" >&2 || true; die "Backend did not become ready within 60 seconds."; }

<<<<<<< Updated upstream
(
    cd "$ROOT_DIR/frontend"
    "$NPM" run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT"
) >"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

FRONTEND_READY=0
for _ in {1..60}; do
    if curl -fsS --connect-timeout 1 --max-time 2 \
        "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null 2>&1; then
        FRONTEND_READY=1
        break
    fi
    if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
        cat "$FRONTEND_LOG" >&2 || true
        die "Frontend exited before becoming ready."
    fi
    sleep 0.5
=======
# ------------------------------------------------------------
# BACKEND FAILED READINESS
# ------------------------------------------------------------

if [[ "$BACKEND_READY" -ne 1 ]]; then

    echo
    echo "============================================================"
    echo " BACKEND DID NOT BECOME READY"
    echo "============================================================"

    echo
    echo "Backend PID : $BACKEND_PID"
    echo "Backend port: $BACKEND_PORT"
    echo "Backend log : $BACKEND_LOG"

    echo
    echo "---------------- LAST BACKEND LOG ----------------"
    tail -n 150 "$BACKEND_LOG" 2>/dev/null || true
    echo "---------------------------------------------------"

    echo
    echo "Port status:"
    ss -ltnp 2>/dev/null | grep ":${BACKEND_PORT} " || true

    die "Backend did not become ready within 60 seconds."

fi

log "Backend is READY."

# ------------------------------------------------------------
# FRONTEND
# ------------------------------------------------------------

cd "$ROOT_DIR/frontend"

rm -f "$FRONTEND_LOG"

echo
echo "==> Starting Vite frontend..."

"$NPM" run dev -- \
    --host 0.0.0.0 \
    --port "$FRONTEND_PORT" \
    >"$FRONTEND_LOG" 2>&1 &

FRONTEND_PID=$!

echo "==> Frontend process started (PID=$FRONTEND_PID)"
echo "==> Frontend log: $FRONTEND_LOG"

# ------------------------------------------------------------
# FRONTEND READINESS
# ------------------------------------------------------------

FRONTEND_READY=0

echo
echo "==> Waiting for frontend..."

for i in {1..60}; do

    if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then

        echo
        echo "============================================================"
        echo " FRONTEND PROCESS EXITED"
        echo "============================================================"

        cat "$FRONTEND_LOG" 2>/dev/null || true

        die "Frontend exited before becoming ready."

    fi

    if curl -fsS \
        --connect-timeout 1 \
        --max-time 2 \
        "http://127.0.0.1:$FRONTEND_PORT/" \
        >/dev/null 2>&1
    then

        FRONTEND_READY=1
        echo
        echo "OK: frontend is responding."
        break

    fi

    if (( i % 10 == 0 )); then
        echo "   frontend still starting... ${i}/60"
    fi

    sleep 0.5

>>>>>>> Stashed changes
done
[[ "$FRONTEND_READY" -eq 1 ]] || { tail -n 100 "$FRONTEND_LOG" >&2 || true; die "Frontend did not become ready within 30 seconds."; }

<<<<<<< Updated upstream
=======
if [[ "$FRONTEND_READY" -ne 1 ]]; then

    echo
    echo "============================================================"
    echo " FRONTEND DID NOT BECOME READY"
    echo "============================================================"

    echo
    echo "---------------- LAST FRONTEND LOG ----------------"
    tail -n 100 "$FRONTEND_LOG" 2>/dev/null || true
    echo "-----------------------------------------------------"

    die "Frontend did not become ready within 30 seconds."

fi

# ------------------------------------------------------------
# SUCCESS
# ------------------------------------------------------------

echo
>>>>>>> Stashed changes
echo "============================================================"
echo "RL_Agent READY"
echo "============================================================"
<<<<<<< Updated upstream
echo "Frontend: http://127.0.0.1:$FRONTEND_PORT"
echo "Backend : http://127.0.0.1:$BACKEND_PORT"
=======
echo
echo "Backend : http://127.0.0.1:$BACKEND_PORT"
echo "Frontend: http://127.0.0.1:$FRONTEND_PORT"
echo "MongoDB : $MONGO_URI"
echo
echo "Backend log : $BACKEND_LOG"
echo "Frontend log: $FRONTEND_LOG"
echo
echo "Dataset files were NOT modified by run_local.sh."
echo
echo "Press CTRL+C to stop both services."
>>>>>>> Stashed changes
echo "============================================================"
echo "Press CTRL+C to stop."

wait
