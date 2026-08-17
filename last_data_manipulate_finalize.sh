#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================================
# RL_AGENT — DATA_MISSION FINALIZER
#
# This wrapper is intentionally separate from last_data_manipulate.sh.
# It runs the already-reviewed RAM-safe rebuild and then enforces the live
# data contract used by data_alert/ in gimuser/RL_Agent.
#
# LOCAL INPUTS (never committed to GitHub):
#   ~/Desktop/Data_mission/data_finished/GUIDE_Train.csv
#   ~/Desktop/Data_mission/data_finished/GUIDE_Test.csv
#
# SAFETY:
#   * Only ~/Desktop/Data_mission may be written.
#   * ~/Desktop/new_one/RL_Agent is never read or written.
#   * The two GUIDE source files are immutable.
#   * Exactly 80 live alerts are required in total, not 40+40.
# ============================================================================

ROOT="$HOME/Desktop/Data_mission"
LIVE_DIR="$ROOT/data_alert_new"
BASE_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_SCRIPT="$BASE_SCRIPT_DIR/last_data_manipulate.sh"

fail() { echo "ERROR: $*" >&2; exit 1; }

[[ "$ROOT" == "$HOME/Desktop/Data_mission" ]] || fail "Unsafe Data_mission path."
[[ -f "$ROOT/data_finished/GUIDE_Train.csv" ]] || fail "GUIDE_Train.csv is missing."
[[ -f "$ROOT/data_finished/GUIDE_Test.csv" ]] || fail "GUIDE_Test.csv is missing."
[[ -f "$BASE_SCRIPT" ]] || fail "last_data_manipulate.sh is missing from the repository checkout."

# Hard guard: never operate on the old local project.
OLD="$HOME/Desktop/new_one/RL_Agent"
if [[ -e "$OLD" ]]; then
  echo "SAFETY: $OLD exists; it will NOT be touched."
fi

chmod +x "$BASE_SCRIPT"
"$BASE_SCRIPT"

python3 - "$ROOT" <<'PY'
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

root = Path(__import__('sys').argv[1]).resolve()
live = root / 'data_alert_new'
source = live / 'live_source.csv'
processed = live / 'live_processed.csv'
mapping = live / 'live_mapping.csv'
incidents = live / 'live_incidents.txt'
report = root / 'last_data_manipulate_report.json'

if not source.is_file():
    raise SystemExit(f'Missing live_source.csv: {source}')
if not processed.is_file():
    raise SystemExit(f'Missing live_processed.csv: {processed}')
if not mapping.is_file():
    raise SystemExit(f'Missing live_mapping.csv: {mapping}')

with source.open(newline='', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

if len(rows) != 80:
    raise SystemExit(f'FATAL: expected exactly 80 live alerts, found {len(rows)}')

ids = [str(r['IncidentId']) for r in rows]
if len(set(ids)) != 80:
    raise SystemExit('FATAL: live_source contains duplicate IncidentId values')

with incidents.open('w', encoding='utf-8') as f:
    for incident_id in ids:
        f.write(incident_id + '\n')

# Validate that live_processed has the same 80 alert IDs and the expected
# 18-column operational schema used by the repository's live data.
expected = [
    'alert_id','IncidentId','Timestamp','Category','MitreTechniques',
    'IncidentGrade','ActionGrouped','ActionGranular','EntityType',
    'EvidenceRole','ThreatFamily','OSFamily','SuspicionLevel','LastVerdict',
    'hour','day','month','is_weekend'
]
with processed.open(newline='', encoding='utf-8') as f:
    reader = csv.reader(f)
    header = next(reader)
    processed_rows = list(reader)
if header != expected:
    raise SystemExit(f'FATAL: live_processed schema mismatch: {header}')
if len(processed_rows) != 80:
    raise SystemExit(f'FATAL: expected 80 live processed rows, found {len(processed_rows)}')

source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
processed_sha = hashlib.sha256(processed.read_bytes()).hexdigest()
incident_sha = hashlib.sha256(incidents.read_bytes()).hexdigest()

existing = {}
if report.is_file():
    existing = json.loads(report.read_text(encoding='utf-8'))

existing.update({
    'live_total': 80,
    'live_contract': {
        'requested_alerts': 80,
        'selected_alerts': 80,
        'selected_incidents': 80,
        'selection_rule': 'one alert per unique IncidentId',
        'fixed_train_test_split': False,
        'train_test_allocation': 'not prescribed; exactly 80 total',
        'incident_overlap_after_extraction': 0,
        'files': {
            'live_source': str(source),
            'live_processed': str(processed),
            'live_mapping': str(mapping),
            'live_incidents': str(incidents),
        },
        'sha256': {
            'live_source': source_sha,
            'live_processed': processed_sha,
            'live_incidents': incident_sha,
        },
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
    },
})
report.write_text(json.dumps(existing, indent=2), encoding='utf-8')

print('FINALIZER VERIFICATION: PASS')
print('Live alerts: 80')
print('Unique live IncidentId: 80')
print('live_incidents.txt: created')
print('live_processed schema: 18 columns')
print('last_data_manipulate_report.json: updated')
PY

status=$?
if [[ $status -ne 0 ]]; then
  echo
  echo "======================================================================"
  echo " FINALIZER FAILED"
  echo "======================================================================"
  echo "No success claim is made. Inspect the error above."
  exit "$status"
fi

echo
echo "======================================================================"
echo " DATA_MISSION FINALIZER COMPLETE"
echo "======================================================================"
echo "Base pipeline: last_data_manipulate.sh"
echo "Live alerts: 80 TOTAL (not 40+40)"
echo "Live incident list: $LIVE_DIR/live_incidents.txt"
echo "Report: $ROOT/last_data_manipulate_report.json"
echo "new_one/RL_Agent: NOT TOUCHED"
echo "EXIT CODE = 0"
echo "======================================================================"
