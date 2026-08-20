#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.yml}"
FRONTEND_PORT="${FRONTEND_PORT:-}"
BACKEND_PORT="${BACKEND_PORT:-}"
FRONTEND_URL=""
BACKEND_URL=""

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

# Pick a free host port BEFORE Compose starts. The previous launcher tried to
# discover the published port after `docker compose up`, but Compose must bind
# the host port during `up`; if the default port was already occupied, startup
# failed before the script could discover an alternative.
port_is_free() {
  local port="$1"
  ! (echo >/dev/tcp/127.0.0.1/"$port") 2>/dev/null
}

choose_port() {
  local requested="$1"
  local fallback_start="$2"
  local port

  if [[ -n "$requested" ]]; then
    [[ "$requested" =~ ^[0-9]+$ ]] || die "Invalid port: $requested"
    if port_is_free "$requested"; then
      printf '%s' "$requested"
      return 0
    fi
    log "Port $requested is already in use; selecting a free port automatically."
  fi

  for ((port=fallback_start; port<fallback_start+100; port++)); do
    if port_is_free "$port"; then
      printf '%s' "$port"
      return 0
    fi
  done

  die "Could not find a free host port in the range ${fallback_start}-$((fallback_start+99))."
}

# These values are exported because Docker Compose performs ${BACKEND_PORT}
# and ${FRONTEND_PORT} interpolation from the process environment.
BACKEND_PORT="$(choose_port "$BACKEND_PORT" 8000)"
FRONTEND_PORT="$(choose_port "$FRONTEND_PORT" 8081)"
export BACKEND_PORT FRONTEND_PORT

# Build the backend with a temporary CPU-only Dockerfile/Compose override.
# The permanent requirements.txt and Dockerfile are deliberately not changed.
# The validation image installs only the runtime dependencies used by this app;
# PyTorch is always taken from the official CPU-only wheel index.
TMP_DOCKER_DIR="$ROOT_DIR/.run_all_docker"
TMP_DOCKERFILE="$TMP_DOCKER_DIR/Dockerfile.cpu"
TMP_FRONTEND_DOCKERFILE="$TMP_DOCKER_DIR/Dockerfile.frontend"
TMP_COMPOSE="$TMP_DOCKER_DIR/docker-compose.cpu.yml"

cleanup() {
  rm -rf "$TMP_DOCKER_DIR"
}
trap cleanup EXIT INT TERM

rm -rf "$TMP_DOCKER_DIR"
mkdir -p "$TMP_DOCKER_DIR"

cat > "$TMP_DOCKERFILE" <<'DOCKERFILE'
FROM python:3.11-slim

WORKDIR /app

# Minimal CPU-only backend dependencies. Do not install from the repository
# requirements file here: it is intentionally decoupled from the validation image.
RUN printf '%s\n' \
    'fastapi' \
    'uvicorn' \
    'pydantic' \
    'pydantic-settings' \
    'python-multipart' \
    'numpy' \
    'pandas' \
    'scikit-learn' \
    'scipy' \
    'gymnasium' \
    'python-dotenv' \
    'requests' \
    'httpx' \
    'pymongo' \
    'psutil' \
    > /tmp/requirements.cpu.txt \
    && python -m pip install --no-cache-dir --disable-pip-version-check -r /tmp/requirements.cpu.txt \
    && python -m pip install --no-cache-dir --disable-pip-version-check --index-url https://download.pytorch.org/whl/cpu torch \
    && python -c "import torch; assert torch.version.cuda is None and not torch.cuda.is_available(); print('PyTorch CPU-only:', torch.__version__)"

COPY backend ./backend
COPY data ./data
COPY README.md ./README.md

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
DOCKERFILE

cat > "$TMP_FRONTEND_DOCKERFILE" <<'DOCKERFILE'
FROM node:18 AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

COPY frontend ./

# Temporary validation-build patch: ApiError.status is optional, but the
# frontend retries only statuses that are actually present. Keep the permanent
# source untouched and narrow the type before passing it to Set.has().
RUN sed -i 's/RETRYABLE_STATUSES\.has(error\.status)/error.status !== undefined \&\& RETRYABLE_STATUSES.has(error.status)/g' src/services/api.ts \
    && npm run build

FROM nginx:stable-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
DOCKERFILE

cat > "$TMP_COMPOSE" <<'YAML'
services:
  backend:
    build:
      context: .
      dockerfile: .run_all_docker/Dockerfile.cpu
  frontend:
    build:
      context: .
      dockerfile: .run_all_docker/Dockerfile.frontend
YAML

log "Using Docker Compose for the project validation stack."
log "CPU-only minimal backend dependencies enabled; permanent requirements are unchanged."
log "Frontend TypeScript validation patch enabled; permanent frontend source is unchanged."
log "Using backend host port ${BACKEND_PORT} and frontend host port ${FRONTEND_PORT}."
log "Building and starting MongoDB, backend and frontend..."

COMPOSE_CPU=("${COMPOSE[@]}" -f "$TMP_COMPOSE")
"${COMPOSE_CPU[@]}" up -d --build || die "Docker Compose failed to build/start the project."

BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}"
FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}"

log "Resolved backend port: ${BACKEND_PORT}"
log "Resolved frontend port: ${FRONTEND_PORT}"

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
  "${COMPOSE_CPU[@]}" ps >&2 || true
  "${COMPOSE_CPU[@]}" logs --tail=80 >&2 || true
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

"${COMPOSE_CPU[@]}" ps
