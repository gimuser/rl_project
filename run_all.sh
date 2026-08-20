#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -x "rl_project/run_all.sh" ]]; then
  chmod +x "rl_project/run_all.sh"
fi

exec "./rl_project/run_all.sh"
