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

# Build the backend with a temporary CPU-only Dockerfile/Compose override.
# This keeps the project's requirements.txt and permanent Dockerfile unchanged.
TMP_DOCKER_DIR="$ROOT_DIR/.run_all_docker"
TMP_DOCKERFILE="$TMP_DOCKER_DIR/Dockerfile.cpu"
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

COPY requirements.txt /tmp/requirements.txt

# Install every dependency except torch from the project's normal requirements.
# Then install PyTorch explicitly from the CPU wheel index so CUDA packages are
# never selected during the Docker build.
RUN python - <<'PY'
from pathlib import Path
src = Path('/tmp/requirements.txt').read_text()
out = []
for line in src.splitlines():
    stripped = line.strip()
    if stripped.startswith('#'):
        out.append(line)
        continue
    name = stripped.split('#', 1)[0].strip()
    if name.startswith(('torch=', 'torch<', 'torch>', 'torch~=', 'torch==', 'torch!=')):
        continue
    if name == 'torch':
        continue
    out.append(line)
Path('/tmp/requirements.cpu.txt').write_text('\n'.join(out) + '\n')
PY
RUN python -m pip install --no-cache-dir --disable-pip-version-check -r /tmp/requirements.cpu.txt \
    && python -m pip install --no-cache-dir --disable-pip-version-check --index-url https://download.pytorch.org/whl/cpu torch \
    && python -c "import torch; assert torch.version.cuda is None and not torch.cuda.is_available(); print('PyTorch CPU-only:', torch.__version__)"

COPY backend ./backend
COPY data ./data
COPY README.md ./README.md

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
DOCKERFILE

cat > "$TMP_COMPOSE" <<'YAML'
services:
  backend:
    build:
      context: .
      dockerfile: .run_all_docker/Dockerfile.cpu
YAML

log "Using Docker Compose for the project validation stack."
log "CPU-only backend build override enabled; permanent Docker requirements are unchanged."
log "Building and starting MongoDB, backend and frontend..."

COMPOSE_CPU=("${COMPOSE[@]}" -f "$TMP_COMPOSE")
"${COMPOSE_CPU[@]}" up -d --build || die "Docker Compose failed to build/start the project."

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
