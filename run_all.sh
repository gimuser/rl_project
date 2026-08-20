#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.yml}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}"
BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}"

log() { printf '[RL] %s\n' "$1"; }
die() { printf '\n[RL] ERROR: %s\n' "$1" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "Docker is required. Install Docker and run ./run_all.sh again."
[[ -f "$COMPOSE_FILE" ]] || die "docker-compose.yml not found."
docker info >/dev/null 2>&1 || die "Docker daemon is not running. Start Docker and run ./run_all.sh again."

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose -f "$COMPOSE_FILE")
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose -f "$COMPOSE_FILE")
else
  die "Docker Compose is required."
fi

log "Using Docker Compose for the project validation stack."
log "Building and starting MongoDB, backend and frontend..."
"${COMPOSE[@]}" up -d --build || die "Docker Compose failed to build/start the project."

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempts="$3"

  command -v curl >/dev/null 2>&1 || die "curl is required for service readiness checks."

  for ((i=1; i<=attempts; i++)); do
    if curl -fsS --connect-timeout 1 --max-time 3 "$url" >/dev/null 2>&1; then
      log "$label is ready: $url"
      return 0
    fi
    sleep 1
done

  log "$label did not become ready. Container status:"
  "${COMPOSE[@]}" ps >&2 || true
  "${COMPOSE[@]}" logs --tail=80 >&2 || true
  return 1
}

wait_for_url "$BACKEND_URL/" "Backend" 90 || die "Backend did not become ready."
wait_for_url "$FRONTEND_URL/" "Frontend" 90 || die "Frontend did not become ready."

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$FRONTEND_URL" >/dev/null 2>&1 &
  log "Opened the frontend with the system default browser."
else
  log "xdg-open is unavailable; open $FRONTEND_URL manually."
fi

printf '\n==============================================\n'
printf ' SOAR-RL-Agent Docker stack is ready\n'
printf ' Backend : %s\n' "$BACKEND_URL"
printf ' Frontend: %s\n' "$FRONTEND_URL"
printf '==============================================\n\n'

"${COMPOSE[@]}" ps
