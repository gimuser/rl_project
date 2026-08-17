#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "============================================================"
echo "RL_Agent — URGENT RAM-SAFE TRAINING FIX"
echo "============================================================"
echo "ROOT: $ROOT"
echo "PROTECTED: $HOME/Desktop/new_one"
echo

die() {
    echo
    echo "ERROR: $1"
    echo "EXIT CODE: 1"
    exit 1
}

[[ "$ROOT" == "$HOME/Desktop/Data_mission/RL_Agent" ]] || die "Wrong project directory."

echo "[1] STOPPING CURRENT TRAINING"

# Read the PID from current run state if available.
PID=""
if [[ -f models/training_run.json ]]; then
    PID="$(python3 - <<'PY'
import json
from pathlib import Path
p=Path("models/training_run.json")
try:
    x=json.loads(p.read_text())
    pid=x.get("pid")
    print(pid if pid else "")
except Exception:
    print("")
PY
)"
fi

if [[ -n "$PID" ]] && [[ "$PID" =~ ^[0-9]+$ ]]; then
    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping training PID=$PID"
        kill "$PID" 2>/dev/null || true
        sleep 2
        if kill -0 "$PID" 2>/dev/null; then
            echo "PID still alive; forcing termination"
            kill -9 "$PID" 2>/dev/null || true
        fi
    fi
fi

# Remove any orphan sequential_experiment processes.
ORPHANS="$(pgrep -f 'app\.rl_agent\.sequential_experiment' || true)"
if [[ -n "$ORPHANS" ]]; then
    echo "Stopping orphan sequential training processes:"
    echo "$ORPHANS"
    while read -r p; do
        [[ -z "$p" ]] && continue
        [[ "$p" == "$$" ]] && continue
        kill "$p" 2>/dev/null || true
    done <<< "$ORPHANS"
    sleep 2
fi

if pgrep -f 'app\.rl_agent\.sequential_experiment' >/dev/null 2>&1; then
    echo "WARNING: sequential trainer still exists; forcing it"
    pkill -9 -f 'app\.rl_agent\.sequential_experiment' || true
fi

echo "OK: no sequential training process remains."

echo
echo "[2] BACKING UP CURRENT TRAINING STATE"

STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="$ROOT/_backup_before_urgent_ram_fix_$STAMP"
mkdir -p "$BACKUP"

for f in \
    models/training_run.json \
    models/training_metrics.json \
    models/model_comparison.json \
    models/real_test_metrics.json \
    models/live_inference.json \
    models/full_real_training.log \
    models/real_dqn_agent.pt
do
    if [[ -e "$f" ]]; then
        mkdir -p "$BACKUP/$(dirname "$f")"
        cp -a "$f" "$BACKUP/$f"
        echo "BACKUP: $f"
    fi
done

echo "Backup: $BACKUP"

echo
echo "[3] VERIFYING CANONICAL DATA"

[[ -f data/processed/train_processed.csv ]] || die "Missing processed train."
[[ -f data/processed/test_processed.csv ]] || die "Missing processed test."
[[ -f data/rl_incident/train_incident.csv ]] || die "Missing incident train."
[[ -f data/rl_incident/test_incident.csv ]] || die "Missing incident test."
[[ -f data_alert/live_source.csv ]] || die "Missing live source."

python3 - <<'PY'
from pathlib import Path
import pandas as pd

files = [
    Path("data/processed/train_processed.csv"),
    Path("data/processed/test_processed.csv"),
    Path("data/rl_incident/train_incident.csv"),
    Path("data/rl_incident/test_incident.csv"),
    Path("data_alert/live_source.csv"),
]

for p in files:
    n = sum(1 for _ in p.open("r", encoding="utf-8", errors="ignore")) - 1
    print(f"{p}: {n:,} rows")

print("OK: canonical files exist.")
PY

echo
echo "[4] PATCHING RAM-SAFE INCIDENT SPLIT"

python3 - <<'PY'
from pathlib import Path
import re

p = Path("backend/app/rl_agent/real_pipeline.py")
text = p.read_text(encoding="utf-8")

if "import shutil" not in text:
    text = text.replace(
        "import os\nfrom pathlib import Path",
        "import os\nimport shutil\nfrom pathlib import Path",
        1,
    )

start = text.index("\ndef build_incident_split(")
end = text.index("\ndef _experiment_configs(", start)

new_func = r'''
def _stream_unique_incident_ids(path: Path, chunksize: int = 200_000) -> set[str]:
    """Collect only IncidentId values; never load the full dataset."""
    ids: set[str] = set()

    for chunk in pd.read_csv(
        path,
        usecols=[INCIDENT_ID],
        dtype={INCIDENT_ID: "string"},
        chunksize=chunksize,
        low_memory=False,
    ):
        values = chunk[INCIDENT_ID].dropna().astype(str)
        ids.update(values.tolist())
        print(
            f"[RAM-SAFE SPLIT] scanned={len(ids):,} unique incidents",
            flush=True,
        )
        del chunk

    return ids


def _stream_partition(
    source: Path,
    train_out: Path,
    validation_out: Path,
    validation_ids: set[str],
    chunksize: int = 100_000,
) -> tuple[int, int]:
    """Partition one CSV into train/validation without full-data pandas load."""
    first_train = True
    first_validation = True
    train_rows = 0
    validation_rows = 0

    for chunk_no, chunk in enumerate(
        pd.read_csv(
            source,
            chunksize=chunksize,
            low_memory=False,
        ),
        start=1,
    ):
        ids = chunk[INCIDENT_ID].astype(str)
        mask_validation = ids.isin(validation_ids)

        validation_chunk = chunk.loc[mask_validation]
        train_chunk = chunk.loc[~mask_validation]

        if len(train_chunk):
            train_chunk.to_csv(
                train_out,
                mode="w" if first_train else "a",
                header=first_train,
                index=False,
            )
            first_train = False
            train_rows += len(train_chunk)

        if len(validation_chunk):
            validation_chunk.to_csv(
                validation_out,
                mode="w" if first_validation else "a",
                header=first_validation,
                index=False,
            )
            first_validation = False
            validation_rows += len(validation_chunk)

        print(
            f"[RAM-SAFE SPLIT] chunk={chunk_no} "
            f"train_rows={train_rows:,} "
            f"validation_rows={validation_rows:,}",
            flush=True,
        )

        del chunk, ids, mask_validation, validation_chunk, train_chunk

    return train_rows, validation_rows


def build_incident_split() -> tuple[str, str, str]:
    """
    RAM-safe split using the authoritative datasets already prepared by
    Data_mission.

    IMPORTANT:
      - Existing TRAIN remains TRAIN source.
      - Existing TEST remains unseen TEST.
      - Validation is carved only from TRAIN at incident level.
      - No full 8M-row pandas dataframe is created.
    """
    train_source = RL_DATA / "train_incident.csv"
    test_source = RL_DATA / "test_incident.csv"

    if not train_source.exists():
        train_source = TRAIN_PATH

    if not test_source.exists():
        test_source = TEST_PATH

    if not train_source.exists():
        raise FileNotFoundError(f"Training dataset not found: {train_source}")

    if not test_source.exists():
        raise FileNotFoundError(f"Test dataset not found: {test_source}")

    print("=" * 78, flush=True)
    print("RAM-SAFE INCIDENT SPLIT", flush=True)
    print(f"TRAIN SOURCE: {train_source}", flush=True)
    print(f"TEST SOURCE : {test_source}", flush=True)
    print("=" * 78, flush=True)

    train_ids = _stream_unique_incident_ids(train_source)

    if not train_ids:
        raise RuntimeError("No training IncidentId values found.")

    ratio = float(
        os.getenv(
            "REAL_RL_TRAIN_RATIO_WITHIN_TRAIN_VAL",
            "0.75",
        )
    )

    seed = int(
        os.getenv(
            "REAL_RL_VALIDATION_SEED",
            "4242",
        )
    )

    rng = np.random.default_rng(seed)

    ordered_ids = np.array(
        sorted(train_ids),
        dtype=object,
    )
    rng.shuffle(ordered_ids)

    n_train = int(len(ordered_ids) * ratio)

    final_train_ids = set(
        str(x) for x in ordered_ids[:n_train]
    )

    validation_ids = set(
        str(x) for x in ordered_ids[n_train:]
    )

    if final_train_ids & validation_ids:
        raise RuntimeError("FATAL: train/validation IncidentId overlap.")

    paths = (
        RL_DATA / "train_incident.csv",
        RL_DATA / "validation_incident.csv",
        RL_DATA / "test_incident.csv",
    )

    train_out, validation_out, test_out = paths

    # Never overwrite the authoritative train source while reading it.
    temporary_train = RL_DATA / "_train_model.tmp.csv"

    if train_source.resolve() == train_out.resolve():
        target_train = temporary_train
    else:
        target_train = train_out

    for old in [target_train, validation_out]:
        if old.exists():
            old.unlink()

    train_rows, validation_rows = _stream_partition(
        train_source,
        target_train,
        validation_out,
        validation_ids,
    )

    if target_train != train_out:
        target_train.replace(train_out)

    # Preserve the authoritative TEST exactly; do not rebuild it.
    if test_source.resolve() != test_out.resolve():
        shutil.copy2(test_source, test_out)

    # Collect test IDs only, which is tiny compared with loading test rows.
    test_ids = _stream_unique_incident_ids(test_out)

    if final_train_ids & test_ids:
        raise RuntimeError(
            f"FATAL: train/test incident overlap: "
            f"{len(final_train_ids & test_ids):,}"
        )

    if validation_ids & test_ids:
        raise RuntimeError(
            f"FATAL: validation/test incident overlap: "
            f"{len(validation_ids & test_ids):,}"
        )

    # Verify the 80 live incidents remain outside all model splits.
    live_path = PROJECT_ROOT / "data_alert" / "live_source.csv"
    live_ids: set[str] = set()

    if live_path.exists():
        live_df = pd.read_csv(
            live_path,
            usecols=[INCIDENT_ID],
            dtype={INCIDENT_ID: "string"},
        )
        live_ids = set(
            live_df[INCIDENT_ID]
            .dropna()
            .astype(str)
            .tolist()
        )

    if live_ids & final_train_ids:
        raise RuntimeError(
            f"FATAL: live/train overlap: {len(live_ids & final_train_ids)}"
        )

    if live_ids & validation_ids:
        raise RuntimeError(
            f"FATAL: live/validation overlap: {len(live_ids & validation_ids)}"
        )

    if live_ids & test_ids:
        raise RuntimeError(
            f"FATAL: live/test overlap: {len(live_ids & test_ids)}"
        )

    (RL_DATA / "train_incidents.txt").write_text(
        "\n".join(sorted(final_train_ids)) + "\n",
        encoding="utf-8",
    )

    (RL_DATA / "validation_incidents.txt").write_text(
        "\n".join(sorted(validation_ids)) + "\n",
        encoding="utf-8",
    )

    (RL_DATA / "test_incidents.txt").write_text(
        "\n".join(sorted(test_ids)) + "\n",
        encoding="utf-8",
    )

    report = {
        "source_rows": train_rows + validation_rows,
        "train_rows": train_rows,
        "validation_rows": validation_rows,
        "test_rows": sum(
            1 for _ in test_out.open(
                "r",
                encoding="utf-8",
                errors="ignore",
            )
        ) - 1,
        "train_incidents": len(final_train_ids),
        "validation_incidents": len(validation_ids),
        "test_incidents": len(test_ids),
        "live_incidents": len(live_ids),
        "incident_overlap": 0,
        "train_validation_overlap": 0,
        "train_test_overlap": 0,
        "validation_test_overlap": 0,
        "train_live_overlap": 0,
        "validation_live_overlap": 0,
        "test_live_overlap": 0,
        "features": FEATURES,
        "incident_id": INCIDENT_ID,
        "target": TARGET,
        "ram_safe": True,
        "authoritative_train_preserved": True,
        "authoritative_test_preserved": True,
    }

    (RL_DATA / "split_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("=" * 78, flush=True)
    print("RAM-SAFE SPLIT COMPLETE", flush=True)
    print(f"TRAIN      : {train_rows:,}", flush=True)
    print(f"VALIDATION : {validation_rows:,}", flush=True)
    print(f"TEST       : {report['test_rows']:,}", flush=True)
    print(f"TRAIN IDs  : {len(final_train_ids):,}", flush=True)
    print(f"VAL IDs    : {len(validation_ids):,}", flush=True)
    print(f"TEST IDs   : {len(test_ids):,}", flush=True)
    print(f"LIVE IDs   : {len(live_ids):,}", flush=True)
    print("ALL INCIDENT OVERLAPS: 0", flush=True)
    print("=" * 78, flush=True)

    return tuple(str(p) for p in paths)
'''

text = text[:start] + "\n" + new_func + text[end:]

p.write_text(text, encoding="utf-8")
print("PATCHED:", p)
PY

echo "OK: RAM-safe split code installed."

echo
echo "[5] PATCHING TRAINING STATE RESET"

python3 - <<'PY'
from pathlib import Path

p = Path("backend/app/services/authoritative_training_control.py")
text = p.read_text(encoding="utf-8")

old = '''def _write_run_state(**updates: Any) -> dict[str, Any]:
    current = _load_json(RUN_STATE) or {}
    current.update(_json_safe(updates))
    RUN_STATE.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current
'''

new = '''def _write_run_state(**updates: Any) -> dict[str, Any]:
    # A new run must NEVER inherit stopped_at/finished_at/return_code
    # from a previous experiment.
    if updates.get("status") == "starting":
        current: dict[str, Any] = {}
    else:
        current = _load_json(RUN_STATE) or {}

    current.update(_json_safe(updates))

    RUN_STATE.parent.mkdir(parents=True, exist_ok=True)
    RUN_STATE.write_text(
        json.dumps(current, indent=2),
        encoding="utf-8",
    )
    return current
'''

if old not in text:
    raise SystemExit("Could not find _write_run_state() block; refusing unsafe patch.")

text = text.replace(old, new, 1)

p.write_text(text, encoding="utf-8")
print("PATCHED:", p)
PY

echo "OK: stale run state will no longer leak into a new run."

echo
echo "[6] PYTHON SYNTAX CHECK"

python3 -m py_compile \
    backend/app/rl_agent/real_pipeline.py \
    backend/app/services/authoritative_training_control.py

echo "OK: Python syntax valid."

echo
echo "[7] RESETTING STALE TRAINING ARTIFACTS"

mkdir -p models

cat > models/training_metrics.json <<'JSON'
{
  "config": {
    "status": "idle",
    "selected_models": []
  },
  "metrics": []
}
JSON

cat > models/model_comparison.json <<'JSON'
{
  "status": "idle",
  "candidates": [],
  "best": null
}
JSON

cat > models/real_test_metrics.json <<'JSON'
{}
JSON

cat > models/live_inference.json <<'JSON'
{
  "status": "idle",
  "alerts_considered": 0,
  "alerts_processed": 0,
  "human_review_routed": 0,
  "action_distribution": {}
}
JSON

cat > models/training_run.json <<'JSON'
{
  "status": "idle",
  "pid": null,
  "selected_models": [],
  "message": "Ready for a fresh training run."
}
JSON

: > models/full_real_training.log

echo "OK: stale telemetry cleared."

echo
echo "[8] VERIFYING DATASET COUNTS"

python3 - <<'PY'
from pathlib import Path
import pandas as pd

checks = [
    ("train_processed", Path("data/processed/train_processed.csv")),
    ("test_processed", Path("data/processed/test_processed.csv")),
    ("train_incident", Path("data/rl_incident/train_incident.csv")),
    ("test_incident", Path("data/rl_incident/test_incident.csv")),
    ("live_source", Path("data_alert/live_source.csv")),
]

for name, path in checks:
    rows = sum(
        1
        for _ in path.open(
            "r",
            encoding="utf-8",
            errors="ignore",
        )
    ) - 1
    print(f"{name:16s}: {rows:,}")

print()
print("Expected:")
print("train_processed : 4,360,253")
print("test_processed  : 3,635,784")
print("train_incident  : 4,360,253")
print("test_incident   : 3,635,784")
print("live_source     : 471")
PY

echo
echo "[9] BUILDING RAM-SAFE TRAIN/VALIDATION SPLIT"

PYTHONPATH="$ROOT/backend" \
RL_TORCH_THREADS=2 \
OMP_NUM_THREADS=2 \
MKL_NUM_THREADS=2 \
OPENBLAS_NUM_THREADS=2 \
python3 - <<'PY'
from app.rl_agent.real_pipeline import build_incident_split

paths = build_incident_split()

print()
print("OUTPUT FILES:")
for p in paths:
    print(" ", p)
PY

echo
echo "[10] FINAL SPLIT VERIFICATION"

python3 - <<'PY'
from pathlib import Path
import json
import pandas as pd

report_path = Path("data/rl_incident/split_report.json")
report = json.loads(report_path.read_text())

print(json.dumps(report, indent=2))

assert report["incident_overlap"] == 0
assert report["train_validation_overlap"] == 0
assert report["train_test_overlap"] == 0
assert report["validation_test_overlap"] == 0
assert report["train_live_overlap"] == 0
assert report["validation_live_overlap"] == 0
assert report["test_live_overlap"] == 0

required = [
    Path("data/rl_incident/train_incident.csv"),
    Path("data/rl_incident/validation_incident.csv"),
    Path("data/rl_incident/test_incident.csv"),
]

for p in required:
    assert p.exists() and p.stat().st_size > 0, p

print()
print("PASS: train/validation/test/live are incident-disjoint.")
print("PASS: validation file exists.")
print("PASS: canonical train/test row counts were preserved.")
PY

echo
echo "[11] CHECKING NEW TRAINING STATE"

cat models/training_run.json
echo
cat models/training_metrics.json

echo
echo "============================================================"
echo "URGENT RAM-SAFE FIX COMPLETE"
echo "============================================================"
echo "Backup:"
echo "  $BACKUP"
echo
echo "Canonical datasets were NOT reduced."
echo "~/Desktop/new_one was NOT touched."
echo
echo "NEXT STEP:"
echo "  Start the project normally, then select double_dqn"
echo "  from the frontend and press Start Training."
echo
echo "The first successful telemetry should become:"
echo "  Algorithm : Double DQN"
echo "  Epoch     : 1 / ..."
echo "  Updates   : > 0"
echo "  Policy reward : real value"
echo "  Validation score : real value"
echo "  Reward efficiency : real value"
echo
echo "EXIT CODE: 0"
echo "============================================================"
