#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================================
# RL_AGENT — LAST DATA MANIPULATION
#
# IMPORTANT:
#   * This script operates ONLY inside ~/Desktop/Data_mission.
#   * It NEVER reads, writes, deletes, or modifies ~/Desktop/new_one/RL_Agent.
#   * GUIDE_Train.csv and GUIDE_Test.csv in data_finished are treated as
#     immutable source files.
#   * Exactly 80 live alerts are reserved before the final train/test split.
#   * Live alerts are NOT a fixed 40/40 split. The script alternates sources
#     while selecting 80 total alerts.
#   * Train/test are incident-disjoint, and live incidents are disjoint from
#     both final train and final test.
#   * Duplicate removal is streaming/disk-backed through SQLite, so the full
#     guides are never loaded into RAM at once.
# ============================================================================

ROOT="$HOME/Desktop/Data_mission"
SOURCE_DIR="$ROOT/data_finished"
GUIDE_DIR="$ROOT/guides_13col"
PROCESSED_DIR="$ROOT/data_processed_new"
INCIDENT_DIR="$ROOT/data_incident_new"
LIVE_DIR="$ROOT/data_alert_new"
WORK_DIR="$ROOT/.last_data_manipulate_work"

TRAIN_SOURCE="$SOURCE_DIR/GUIDE_Train.csv"
TEST_SOURCE="$SOURCE_DIR/GUIDE_Test.csv"

KEEP_COLUMNS=(
  IncidentId Timestamp Category MitreTechniques IncidentGrade
  ActionGrouped ActionGranular EntityType EvidenceRole ThreatFamily
  OSFamily SuspicionLevel LastVerdict
)

# The old backend encoder operates on these categorical fields.
CATEGORICAL_COLUMNS=(
  Category MitreTechniques IncidentGrade ActionGrouped ActionGranular
  EntityType EvidenceRole ThreatFamily OSFamily SuspicionLevel LastVerdict
)

PROCESSED_COLUMNS=(
  IncidentId Timestamp Category MitreTechniques IncidentGrade
  ActionGrouped ActionGranular EntityType EvidenceRole ThreatFamily
  OSFamily SuspicionLevel LastVerdict hour day month is_weekend
)

log() { printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$1"; }
die() { echo; echo "ERROR: $1" >&2; exit 1; }

[[ -d "$ROOT" ]] || die "Missing Data_mission: $ROOT"
[[ "$ROOT" == "$HOME/Desktop/Data_mission" ]] || die "Unsafe ROOT path."
[[ -f "$TRAIN_SOURCE" ]] || die "Missing GUIDE_Train.csv"
[[ -f "$TEST_SOURCE" ]] || die "Missing GUIDE_Test.csv"

# Hard safety check: this script must never operate on the old project.
if [[ -e "$HOME/Desktop/new_one/RL_Agent" ]]; then
  echo "Safety check: ~/Desktop/new_one/RL_Agent exists and will NOT be touched."
fi

log "Cleaning only generated outputs from the previous Data_mission run"
rm -rf "$GUIDE_DIR" "$PROCESSED_DIR" "$INCIDENT_DIR" "$LIVE_DIR" "$WORK_DIR"
mkdir -p "$GUIDE_DIR" "$PROCESSED_DIR" "$INCIDENT_DIR" "$LIVE_DIR" "$WORK_DIR"

command -v python3 >/dev/null 2>&1 || die "python3 is required"

log "Starting RAM-safe rebuild"

python3 - "$ROOT" <<'PY'
import csv
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(sys.argv[1]).resolve()
SOURCE_DIR = ROOT / "data_finished"
GUIDE_DIR = ROOT / "guides_13col"
PROCESSED_DIR = ROOT / "data_processed_new"
INCIDENT_DIR = ROOT / "data_incident_new"
LIVE_DIR = ROOT / "data_alert_new"
WORK_DIR = ROOT / ".last_data_manipulate_work"

TRAIN_SOURCE = SOURCE_DIR / "GUIDE_Train.csv"
TEST_SOURCE = SOURCE_DIR / "GUIDE_Test.csv"

KEEP = [
    "IncidentId", "Timestamp", "Category", "MitreTechniques", "IncidentGrade",
    "ActionGrouped", "ActionGranular", "EntityType", "EvidenceRole", "ThreatFamily",
    "OSFamily", "SuspicionLevel", "LastVerdict",
]
CATS = [
    "Category", "MitreTechniques", "IncidentGrade", "ActionGrouped", "ActionGranular",
    "EntityType", "EvidenceRole", "ThreatFamily", "OSFamily", "SuspicionLevel", "LastVerdict",
]
PROCESSED = KEEP + ["hour", "day", "month", "is_weekend"]
NUMERIC_TO_SCALE = ["IncidentId", "hour", "day", "month", "is_weekend"]
CHUNK = 50_000
LIVE_TOTAL = 80


def msg(s):
    print(f"\n>>> {s}", flush=True)


def require_columns(path):
    header = pd.read_csv(path, nrows=0)
    missing = [c for c in KEEP if c not in header.columns]
    if missing:
        raise RuntimeError(f"{path} is missing required columns: {missing}")


def canonical_row_key(row):
    # SHA-256 over length-prefixed UTF-8 fields. This prevents separator
    # ambiguity and gives a disk-backed duplicate key without holding rows in RAM.
    h = hashlib.sha256()
    for value in row:
        b = str(value).encode("utf-8", errors="surrogatepass")
        h.update(len(b).to_bytes(8, "big"))
        h.update(b)
    return h.digest()


def build_13col_dedup(source, output):
    msg(f"Reducing {source.name} -> 13 columns and removing exact duplicate rows")
    require_columns(source)
    db_path = WORK_DIR / (source.stem + "_dedup.sqlite3")
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA temp_store=FILE")
    con.execute("CREATE TABLE seen (k BLOB PRIMARY KEY)")
    con.commit()

    rows_seen = rows_kept = duplicates = 0
    first = True
    with output.open("w", newline="", encoding="utf-8") as fout:
        writer = csv.writer(fout)
        for chunk in pd.read_csv(source, usecols=KEEP, dtype=str, chunksize=CHUNK, keep_default_na=False):
            chunk = chunk.fillna("Unknown")
            for row in chunk.itertuples(index=False, name=None):
                rows_seen += 1
                key = canonical_row_key(row)
                cur = con.execute("INSERT OR IGNORE INTO seen(k) VALUES (?)", (key,))
                if cur.rowcount == 1:
                    writer.writerow(row)
                    rows_kept += 1
                else:
                    duplicates += 1
            con.commit()
            if rows_seen % 500_000 < CHUNK:
                print(f"    {source.name}: seen={rows_seen:,} kept={rows_kept:,} exact_dups={duplicates:,}", flush=True)
    con.close()
    db_path.unlink(missing_ok=True)
    return rows_seen, rows_kept, duplicates


train_guide = GUIDE_DIR / "GUIDE_Train_13col.csv"
test_guide = GUIDE_DIR / "GUIDE_Test_13col.csv"

train_stats = build_13col_dedup(TRAIN_SOURCE, train_guide)
test_stats = build_13col_dedup(TEST_SOURCE, test_guide)

# ---------------------------------------------------------------------------
# Build the train categorical codebooks exactly like the old backend encoder:
# sorted unique train values, index 0..N-1, test unknown => -1.
# ---------------------------------------------------------------------------

def collect_codebooks(train_path):
    values = {c: set() for c in CATS}
    numeric_minmax = {c: [float("inf"), float("-inf")] for c in NUMERIC_TO_SCALE}
    for chunk in pd.read_csv(train_path, dtype=str, chunksize=CHUNK, keep_default_na=False):
        chunk = chunk.fillna("Unknown")
        for c in CATS:
            values[c].update(chunk[c].astype(str).tolist())
        inc = pd.to_numeric(chunk["IncidentId"], errors="raise").astype(float)
        numeric_minmax["IncidentId"][0] = min(numeric_minmax["IncidentId"][0], float(inc.min()))
        numeric_minmax["IncidentId"][1] = max(numeric_minmax["IncidentId"][1], float(inc.max()))
        ts = pd.to_datetime(chunk["Timestamp"], utc=True, errors="raise")
        t = {
            "hour": ts.dt.hour.astype(float),
            "day": ts.dt.day.astype(float),
            "month": ts.dt.month.astype(float),
            "is_weekend": (ts.dt.dayofweek >= 5).astype(float),
        }
        for c, s in t.items():
            numeric_minmax[c][0] = min(numeric_minmax[c][0], float(s.min()))
            numeric_minmax[c][1] = max(numeric_minmax[c][1], float(s.max()))
    mappings = {c: {v: i for i, v in enumerate(sorted(values[c]))} for c in CATS}
    return mappings, numeric_minmax


msg("Fitting categorical mappings and MinMax normalization ONLY on train")
mappings, train_minmax = collect_codebooks(train_guide)

with (PROCESSED_DIR / "category_mappings.json").open("w", encoding="utf-8") as f:
    json.dump(mappings, f, indent=2, ensure_ascii=False)

with (PROCESSED_DIR / "normalization.json").open("w", encoding="utf-8") as f:
    json.dump({k: {"min": v[0], "max": v[1]} for k, v in train_minmax.items()}, f, indent=2)


def scale_value(value, lo, hi):
    # Same mathematical behavior as sklearn MinMaxScaler: no clipping.
    if hi == lo:
        return 0.0
    return (float(value) - lo) / (hi - lo)


def transform_file(source, output, split):
    msg(f"Applying old backend pipeline to {split}: encoding -> time features -> train-fitted MinMax")
    rows = 0
    first = True
    with output.open("w", newline="", encoding="utf-8") as fout:
        writer = csv.writer(fout)
        writer.writerow(PROCESSED)
        for chunk in pd.read_csv(source, dtype=str, chunksize=CHUNK, keep_default_na=False):
            chunk = chunk.fillna("Unknown")
            out = {}
            # Encoder: exactly the old backend convention.
            for c in KEEP:
                if c in CATS:
                    m = mappings[c]
                    out[c] = chunk[c].astype(str).map(m).fillna(-1).astype(int).tolist()
                elif c == "IncidentId":
                    out[c] = [scale_value(x, *train_minmax[c]) for x in pd.to_numeric(chunk[c], errors="raise")]
                elif c == "Timestamp":
                    ts = pd.to_datetime(chunk[c], utc=True, errors="raise")
                    out[c] = ts.dt.strftime("%Y-%m-%d %H:%M:%S+00:00").tolist()
                else:
                    out[c] = chunk[c].astype(str).tolist()

            ts = pd.to_datetime(chunk["Timestamp"], utc=True, errors="raise")
            time = {
                "hour": ts.dt.hour.astype(float),
                "day": ts.dt.day.astype(float),
                "month": ts.dt.month.astype(float),
                "is_weekend": (ts.dt.dayofweek >= 5).astype(float),
            }
            for c, s in time.items():
                out[c] = [scale_value(x, *train_minmax[c]) for x in s]

            for i in range(len(chunk)):
                writer.writerow([out[c][i] for c in PROCESSED])
            rows += len(chunk)
            if rows % 500_000 < CHUNK:
                print(f"    {split}: processed={rows:,}", flush=True)
    return rows


# ---------------------------------------------------------------------------
# Reserve exactly 80 live alerts BEFORE final train/test assignment.
# We first make train/test incident-disjoint at the raw 13-column level, then
# reserve 80 rows from the two sources by alternating source availability.
# ---------------------------------------------------------------------------

def collect_train_incidents(path):
    ids = set()
    for chunk in pd.read_csv(path, usecols=["IncidentId"], dtype=str, chunksize=CHUNK, keep_default_na=False):
        ids.update(chunk["IncidentId"].astype(str).tolist())
    return ids


msg("Checking incident overlap between the two cleaned guides")
train_incidents = collect_train_incidents(train_guide)
# Test rows sharing an IncidentId with train are removed. This is the only
# direction used: train remains the authoritative first split.
test_disjoint = GUIDE_DIR / "GUIDE_Test_13col_disjoint.csv"
removed_cross_incident = 0
kept_test = 0
with test_disjoint.open("w", newline="", encoding="utf-8") as fout:
    writer = csv.writer(fout)
    writer.writerow(KEEP)
    for chunk in pd.read_csv(test_guide, dtype=str, chunksize=CHUNK, keep_default_na=False):
        chunk = chunk.fillna("Unknown")
        mask = ~chunk["IncidentId"].astype(str).isin(train_incidents)
        removed_cross_incident += int((~mask).sum())
        kept_test += int(mask.sum())
        if mask.any():
            for row in chunk.loc[mask, KEEP].itertuples(index=False, name=None):
                writer.writerow(row)

# Replace the test 13-column working file with the disjoint version.
test_guide.unlink()
test_disjoint.rename(test_guide)

# Recompute test incident IDs after disjointing.
test_incidents = collect_train_incidents(test_guide)
if train_incidents & test_incidents:
    raise RuntimeError("FATAL: train/test incident overlap remains after filtering")


def candidate_rows(path, limit=200):
    result = []
    seen = set()
    for chunk in pd.read_csv(path, dtype=str, chunksize=CHUNK, keep_default_na=False):
        chunk = chunk.fillna("Unknown")
        for row in chunk.itertuples(index=False, name=None):
            incident = str(row[0])
            if incident in seen:
                continue
            seen.add(incident)
            result.append(row)
            if len(result) >= limit:
                return result
    return result


train_candidates = candidate_rows(train_guide, LIVE_TOTAL)
test_candidates = candidate_rows(test_guide, LIVE_TOTAL)
if len(train_candidates) + len(test_candidates) < LIVE_TOTAL:
    raise RuntimeError("FATAL: fewer than 80 eligible distinct incidents for live alerts")

# Alternate sources until 80 total; this is deliberately NOT 40 train + 40 test.
live_rows = []
i = j = 0
while len(live_rows) < LIVE_TOTAL:
    progressed = False
    if i < len(train_candidates):
        live_rows.append(("train", train_candidates[i])); i += 1; progressed = True
        if len(live_rows) == LIVE_TOTAL:
            break
    if j < len(test_candidates):
        live_rows.append(("test", test_candidates[j])); j += 1; progressed = True
    if not progressed:
        raise RuntimeError("FATAL: could not select 80 live alerts")

live_incidents = {str(row[1][0]) for row in live_rows}
if len(live_incidents) != LIVE_TOTAL:
    raise RuntimeError("FATAL: live alerts do not contain 80 distinct incidents")
if live_incidents & train_incidents or live_incidents & test_incidents:
    raise RuntimeError("FATAL: live incident overlaps train/test")

# Write live source and filter those 80 incidents out of both final datasets.
live_source = LIVE_DIR / "live_source.csv"
with live_source.open("w", newline="", encoding="utf-8") as fout:
    writer = csv.writer(fout)
    writer.writerow(["alert_id"] + KEEP)
    for n, (_, row) in enumerate(live_rows, start=1):
        writer.writerow([f"LIVE-{n:04d}"] + list(row))


def remove_incidents(source, output, forbidden):
    rows = kept = removed = 0
    with output.open("w", newline="", encoding="utf-8") as fout:
        writer = csv.writer(fout)
        writer.writerow(KEEP)
        for chunk in pd.read_csv(source, dtype=str, chunksize=CHUNK, keep_default_na=False):
            chunk = chunk.fillna("Unknown")
            mask = ~chunk["IncidentId"].astype(str).isin(forbidden)
            removed += int((~mask).sum())
            kept += int(mask.sum())
            rows += len(chunk)
            if mask.any():
                for row in chunk.loc[mask, KEEP].itertuples(index=False, name=None):
                    writer.writerow(row)
    return rows, kept, removed

train_final_raw = WORK_DIR / "train_final_raw.csv"
test_final_raw = WORK_DIR / "test_final_raw.csv"
_, train_kept, train_live_removed = remove_incidents(train_guide, train_final_raw, live_incidents)
_, test_kept, test_live_removed = remove_incidents(test_guide, test_final_raw, live_incidents)

# Final processed files use the SAME train-fitted codebook/scaler.
train_processed = PROCESSED_DIR / "train_processed.csv"
test_processed = PROCESSED_DIR / "test_processed.csv"
train_rows = transform_file(train_final_raw, train_processed, "TRAIN")
test_rows = transform_file(test_final_raw, test_processed, "TEST")

# ---------------------------------------------------------------------------
# Incident-level datasets: same rows as processed data, but with explicit
# incident lists and a split report. Because each split was made by IncidentId,
# every incident belongs to exactly one final split.
# ---------------------------------------------------------------------------
import shutil
shutil.copy2(train_processed, INCIDENT_DIR / "train_incident.csv")
shutil.copy2(test_processed, INCIDENT_DIR / "test_incident.csv")

with (INCIDENT_DIR / "train_incidents.txt").open("w", encoding="utf-8") as f:
    for x in sorted(train_incidents - live_incidents, key=lambda v: (len(v), v)):
        f.write(x + "\n")
with (INCIDENT_DIR / "test_incidents.txt").open("w", encoding="utf-8") as f:
    for x in sorted(test_incidents - live_incidents, key=lambda v: (len(v), v)):
        f.write(x + "\n")

# ---------------------------------------------------------------------------
# Live processed: same old pipeline shape, with alert_id retained as the
# operational identifier. It is normalized using the TRAIN codebook/scaler.
# ---------------------------------------------------------------------------
live_processed = LIVE_DIR / "live_processed.csv"
with live_processed.open("w", newline="", encoding="utf-8") as fout:
    writer = csv.writer(fout)
    writer.writerow(["alert_id"] + PROCESSED)
    live_df = pd.read_csv(live_source, dtype=str, keep_default_na=False)
    live_df = live_df.fillna("Unknown")
    for _, row in live_df.iterrows():
        out = {"alert_id": row["alert_id"]}
        for c in CATS:
            out[c] = mappings[c].get(str(row[c]), -1)
        out["IncidentId"] = scale_value(row["IncidentId"], *train_minmax["IncidentId"])
        ts = pd.to_datetime(row["Timestamp"], utc=True, errors="raise")
        out["Timestamp"] = ts.strftime("%Y-%m-%d %H:%M:%S+00:00")
        out["hour"] = scale_value(ts.hour, *train_minmax["hour"])
        out["day"] = scale_value(ts.day, *train_minmax["day"])
        out["month"] = scale_value(ts.month, *train_minmax["month"])
        out["is_weekend"] = scale_value(1 if ts.dayofweek >= 5 else 0, *train_minmax["is_weekend"])
        writer.writerow([out["alert_id"]] + [out[c] for c in PROCESSED])

# Mapping/manifest in the same style as the existing data_alert contract.
live_mapping = LIVE_DIR / "live_mapping.csv"
pd.DataFrame({"alert_id": [f"LIVE-{n:04d}" for n in range(1, LIVE_TOTAL + 1)],
              "source": [src for src, _ in live_rows],
              "IncidentId": [row[0] for _, row in live_rows]}).to_csv(live_mapping, index=False)

# Strong final verification using streaming SQLite sets. No full CSV is loaded.
def csv_incidents(path, has_alert_id=False):
    ids = set()
    use = ["IncidentId"]
    for chunk in pd.read_csv(path, usecols=use, dtype=str, chunksize=CHUNK, keep_default_na=False):
        ids.update(chunk["IncidentId"].astype(str).tolist())
    return ids


def duplicate_count(path, columns):
    db = WORK_DIR / (Path(path).stem + "_verify.sqlite3")
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE seen(k BLOB PRIMARY KEY)")
    duplicates = 0
    for chunk in pd.read_csv(path, usecols=columns, dtype=str, chunksize=CHUNK, keep_default_na=False):
        for row in chunk.itertuples(index=False, name=None):
            key = canonical_row_key(row)
            cur = con.execute("INSERT OR IGNORE INTO seen(k) VALUES (?)", (key,))
            if cur.rowcount == 0:
                duplicates += 1
        con.commit()
    con.close(); db.unlink(missing_ok=True)
    return duplicates

msg("FINAL VERIFICATION — duplicates, incident separation, live isolation")
train_dup = duplicate_count(train_final_raw, KEEP)
test_dup = duplicate_count(test_final_raw, KEEP)
if train_dup or test_dup:
    raise RuntimeError(f"FATAL: duplicates remain (train={train_dup}, test={test_dup})")

final_train_inc = csv_incidents(train_final_raw)
final_test_inc = csv_incidents(test_final_raw)
if final_train_inc & final_test_inc:
    raise RuntimeError("FATAL: final train/test share an IncidentId")
if live_incidents & final_train_inc:
    raise RuntimeError("FATAL: live/train IncidentId overlap")
if live_incidents & final_test_inc:
    raise RuntimeError("FATAL: live/test IncidentId overlap")

live_dup = duplicate_count(live_source, ["IncidentId"])
if live_dup:
    raise RuntimeError(f"FATAL: live IncidentId duplicates remain: {live_dup}")

# Check processed schema exactly.
for path in [train_processed, test_processed]:
    header = list(pd.read_csv(path, nrows=0).columns)
    if header != PROCESSED:
        raise RuntimeError(f"FATAL: wrong processed schema in {path}: {header}")

# Keep only final useful metadata in the working directory; the source guides
# remain untouched in data_finished.
manifest = {
    "source_train": str(TRAIN_SOURCE),
    "source_test": str(TEST_SOURCE),
    "source_guides_modified": False,
    "old_project_modified": False,
    "keep_columns": KEEP,
    "processed_columns": PROCESSED,
    "train_source_rows_seen": train_stats[0],
    "train_source_rows_after_exact_dedup": train_stats[1],
    "train_exact_duplicates_removed": train_stats[2],
    "test_source_rows_seen": test_stats[0],
    "test_source_rows_after_exact_dedup": test_stats[1],
    "test_exact_duplicates_removed": test_stats[2],
    "test_rows_removed_for_train_incident_overlap": removed_cross_incident,
    "live_total": LIVE_TOTAL,
    "live_source_counts": {
        "train": sum(1 for s, _ in live_rows if s == "train"),
        "test": sum(1 for s, _ in live_rows if s == "test"),
    },
    "train_live_rows_removed": train_live_removed,
    "test_live_rows_removed": test_live_removed,
    "final_train_rows": train_rows,
    "final_test_rows": test_rows,
    "final_train_incidents": len(final_train_inc),
    "final_test_incidents": len(final_test_inc),
    "live_incidents": len(live_incidents),
    "verification": {
        "train_duplicate_rows": train_dup,
        "test_duplicate_rows": test_dup,
        "train_test_common_incidents": len(final_train_inc & final_test_inc),
        "live_train_common_incidents": len(live_incidents & final_train_inc),
        "live_test_common_incidents": len(live_incidents & final_test_inc),
        "live_duplicate_incidents": live_dup,
    },
}
with (ROOT / "last_data_manipulate_report.json").open("w", encoding="utf-8") as f:
    json.dump(manifest, f, indent=2)

# Remove only transient working files, never the source guides.
import shutil
shutil.rmtree(WORK_DIR, ignore_errors=True)

print("\n======================================================================")
print(" DATA MANIPULATION COMPLETE — ALL VERIFICATIONS PASSED")
print("======================================================================")
print(f"13-col guides : {GUIDE_DIR}")
print(f"Processed     : {PROCESSED_DIR}")
print(f"Incident data : {INCIDENT_DIR}")
print(f"Live data     : {LIVE_DIR}")
print(f"Live alerts   : {LIVE_TOTAL} total (NOT fixed 40/40)")
print(f"Train rows    : {train_rows:,}")
print(f"Test rows     : {test_rows:,}")
print(f"Train incidents: {len(final_train_inc):,}")
print(f"Test incidents : {len(final_test_inc):,}")
print("Train/Test common incidents : 0")
print("Live/Train common incidents : 0")
print("Live/Test common incidents  : 0")
print("Train duplicate rows        : 0")
print("Test duplicate rows         : 0")
print("Live duplicate incidents    : 0")
print("Source GUIDE files modified : NO")
print("~/Desktop/new_one/RL_Agent modified : NO")
print("======================================================================")
PY

status=$?
if [[ $status -ne 0 ]]; then
  echo
  echo "======================================================================"
  echo " DATA MANIPULATION FAILED — NO CLAIM OF SUCCESS"
  echo "======================================================================"
  echo "Source GUIDE files were not intentionally modified by this script."
  echo "Inspect the error above before rerunning."
  exit "$status"
fi

echo
echo "EXIT CODE = 0"
echo "======================================================================"
