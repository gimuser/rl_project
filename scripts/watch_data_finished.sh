#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT="$ROOT/data_finished"
PROCESSOR="$ROOT/scripts/process_data_finished.py"
LOG_DIR="$INPUT/logs"
ARCHIVE="$INPUT/archive"
POLL_SECONDS="${POLL_SECONDS:-5}"

mkdir -p "$INPUT" "$LOG_DIR" "$ARCHIVE"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

wait_stable() {
  local file="$1"
  local a b
  [[ -s "$file" ]] || return 1
  a=$(stat -c '%s' "$file")
  sleep 2
  b=$(stat -c '%s' "$file")
  [[ "$a" == "$b" ]]
}

run_once() {
  local train="$INPUT/GUIDE_Train.csv"
  local test="$INPUT/GUIDE_Test.csv"
  [[ -f "$train" && -f "$test" ]] || return 0
  wait_stable "$train" || return 0
  wait_stable "$test" || return 0

  local tag log_file archive_dir
  tag=$(date -u '+%Y%m%d_%H%M%S')
  log_file="$LOG_DIR/update_${tag}.log"
  archive_dir="$ARCHIVE/$tag"
  mkdir -p "$archive_dir"

  log "Both GUIDE files detected and stable. Starting processor."
  if python3 "$PROCESSOR" 2>&1 | tee "$log_file"; then
    log "Processor succeeded. Archiving consumed input files."
    mv "$train" "$archive_dir/GUIDE_Train.csv"
    mv "$test" "$archive_dir/GUIDE_Test.csv"
    cp "$log_file" "$archive_dir/processor.log"
    log "Update completed and input pair archived at $archive_dir"
  else
    log "Processor FAILED. Input files were NOT moved, so you can inspect/fix and retry."
    return 1
  fi
}

log "Watching: $INPUT"
log "Drop GUIDE_Train.csv and GUIDE_Test.csv into this folder."
log "Polling every ${POLL_SECONDS}s; set POLL_SECONDS to change it."

while true; do
  if [[ -f "$INPUT/GUIDE_Train.csv" && -f "$INPUT/GUIDE_Test.csv" ]]; then
    run_once || true
    # Prevent immediate repeat attempts on the same broken pair.
    sleep 2
  else
    sleep "$POLL_SECONDS"
  fi
done
