#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PROJECT_NAME="rl_agent"

BACKEND_CONTAINER_PORT=8000
FRONTEND_CONTAINER_PORT=80

DEFAULT_BACKEND_PORT="${BACKEND_PORT:-8000}"
DEFAULT_FRONTEND_PORT="${FRONTEND_PORT:-8081}"

# ============================================================
# COLORS / LOGGING
# ============================================================

log() {
    printf '\n==> %s\n' "$1"
}

info() {
    printf '    %s\n' "$1"
}

die() {
    printf '\nERROR: %s\n' "$1" >&2
    exit 1
}

# ============================================================
# DOCKER CLEANUP
# Ctrl+C automatically reaches this function
# ============================================================

CLEANUP_DONE=0

cleanup() {
    if [[ "$CLEANUP_DONE" -eq 1 ]]; then
        return
    fi

    CLEANUP_DONE=1

    echo
    echo
    echo "============================================================"
    echo " Stopping RL_AGENT..."
    echo "============================================================"

    if [[ -n "${COMPOSE_FILE:-}" ]] && [[ -n "${COMPOSE[*]:-}" ]]; then
        "${COMPOSE[@]}" \
            -f "$COMPOSE_FILE" \
            --project-name "$PROJECT_NAME" \
            down --remove-orphans >/dev/null 2>&1 || true
    fi

    echo
    echo "RL_AGENT containers stopped."
    echo "Docker network removed."
    echo "Ports released."
    echo
    echo "RL_AGENT stopped cleanly."
    echo
}

# IMPORTANT:
# Ctrl+C / SIGINT
# SIGTERM
# normal script exit
trap 'cleanup' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# ============================================================
# DOCKER CHECK
# ============================================================

command -v docker >/dev/null 2>&1 || die "Docker is not installed."

unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH || true

# Prefer the system Docker socket when available, even if a user-level
# Docker host or Podman socket is configured in the environment.
if ! docker info >/dev/null 2>&1; then
    if [[ -S /var/run/docker.sock ]]; then
        export DOCKER_HOST="unix:///var/run/docker.sock"
        info "Falling back to system Docker socket: $DOCKER_HOST"
    else
        die "Docker daemon is not running or current user cannot access Docker."
    fi
fi

if docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
else
    die "Docker Compose is not installed."
fi

# ============================================================
# FIND COMPOSE FILE
# ============================================================

if [[ -f "$ROOT_DIR/docker-compose.yml" ]]; then
    COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
elif [[ -f "$ROOT_DIR/compose.yml" ]]; then
    COMPOSE_FILE="$ROOT_DIR/compose.yml"
elif [[ -f "$ROOT_DIR/compose.yaml" ]]; then
    COMPOSE_FILE="$ROOT_DIR/compose.yaml"
else
    die "No Docker Compose file found."
fi

# ============================================================
# PORT CHECK
# ============================================================

port_busy() {
    local port="$1"

    if command -v ss >/dev/null 2>&1; then
        if ss -H -ltn 2>/dev/null | awk -v p=":$port" '{ addr=$4; if (addr ~ p "$" ) found=1 } END { exit(found ? 0 : 1) }'; then
            return 0
        fi
    fi

    if command -v lsof >/dev/null 2>&1; then
        if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
            return 0
        fi
    fi

    return 1
}

find_free_port() {
    local port="$1"
    local max="$2"

    while [[ "$port" -le "$max" ]]; do

        if ! port_busy "$port"; then
            printf '%s\n' "$port"
            return 0
        fi

        port=$((port + 1))
    done

    return 1
}

# ============================================================
# STARTUP INFORMATION
# ============================================================

log "RL_AGENT Docker startup"

info "Project root: $ROOT_DIR"
info "Compose command: ${COMPOSE[*]}"
info "Compose file: $COMPOSE_FILE"

# ============================================================
# STOP OLD RL_AGENT CONTAINERS
# ============================================================

log "Stopping existing RL_AGENT containers..."

"${COMPOSE[@]}" \
    -f "$COMPOSE_FILE" \
    --project-name "$PROJECT_NAME" \
    down --remove-orphans >/dev/null 2>&1 || true

info "RL_AGENT containers stopped."

# ============================================================
# REMOVE STALE CONTAINERS
# ============================================================

log "Removing stale RL_AGENT containers..."

mapfile -t OLD_CONTAINERS < <(
    docker ps -aq \
        --filter "label=com.docker.compose.project=$PROJECT_NAME" \
        2>/dev/null || true
)

if [[ "${#OLD_CONTAINERS[@]}" -gt 0 ]]; then
    docker rm -f "${OLD_CONTAINERS[@]}" >/dev/null 2>&1 || true
fi

info "Stale RL_AGENT containers removed."

# ============================================================
# BACKEND PORT
# ============================================================

log "Selecting backend port..."

BACKEND_PORT="$(find_free_port "$DEFAULT_BACKEND_PORT" 8999)" || \
    die "No free backend port available."

export BACKEND_PORT

info "Selected backend host port: $BACKEND_PORT"

# ============================================================
# FRONTEND PORT
# ============================================================

log "Selecting frontend port..."

FRONTEND_PORT="$(find_free_port "$DEFAULT_FRONTEND_PORT" 8999)" || \
    die "No free frontend port available."

export FRONTEND_PORT

info "Selected frontend host port: $FRONTEND_PORT"

# ============================================================
# VALIDATE COMPOSE
# ============================================================

log "Validating Docker Compose configuration..."

CONFIG_FILE="$(mktemp)"

if ! "${COMPOSE[@]}" \
        -f "$COMPOSE_FILE" \
        --project-name "$PROJECT_NAME" \
        config > "$CONFIG_FILE"; then

    echo
    cat "$CONFIG_FILE" || true
    rm -f "$CONFIG_FILE"

    die "Docker Compose configuration is invalid."
fi

rm -f "$CONFIG_FILE"

info "Compose configuration is valid."

# ============================================================
# BUILD
# ============================================================

log "Building Docker images..."

"${COMPOSE[@]}" \
    -f "$COMPOSE_FILE" \
    --project-name "$PROJECT_NAME" \
    build

info "Docker images built successfully."

# ============================================================
# FINAL PORT CHECK
# ============================================================

log "Final port availability check..."

if port_busy "$BACKEND_PORT"; then
    die "Backend port $BACKEND_PORT became occupied before startup."
fi

if port_busy "$FRONTEND_PORT"; then
    die "Frontend port $FRONTEND_PORT became occupied before startup."
fi

info "Backend port $BACKEND_PORT is free."
info "Frontend port $FRONTEND_PORT is free."

# ============================================================
# START CONTAINERS
# ============================================================

log "Starting RL_AGENT..."

"${COMPOSE[@]}" \
    -f "$COMPOSE_FILE" \
    --project-name "$PROJECT_NAME" \
    up -d

info "RL_AGENT containers started."

# ============================================================
# WAIT
# ============================================================

log "Waiting for services..."

sleep 3

# ============================================================
# STATUS
# ============================================================

log "Container status"

"${COMPOSE[@]}" \
    -f "$COMPOSE_FILE" \
    --project-name "$PROJECT_NAME" \
    ps

# ============================================================
# URLS
# ============================================================

echo
echo "============================================================"
echo " RL_AGENT IS RUNNING"
echo "============================================================"

echo
echo "Frontend:"
echo "  http://127.0.0.1:${FRONTEND_PORT}"

echo
echo "Backend:"
echo "  http://127.0.0.1:${BACKEND_PORT}"

echo
echo "============================================================"
echo " Press CTRL+C to stop RL_AGENT cleanly"
echo "============================================================"
echo

# ============================================================
# KEEP SCRIPT RUNNING
#
# This is important:
# The script stays alive so Ctrl+C can trigger cleanup().
# ============================================================

while true; do
    sleep 1
done