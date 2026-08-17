#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path("/home/oualid/Desktop/RL_AGENT")
SOURCE_FILE = PROJECT_ROOT / "data_train.csv"

# Number of simulated incoming alerts.
# Change to 30 if you prefer 30.
N_ALERTS = 40

# Reproducible random selection.
RANDOM_SEED = 20260812

OUTPUT_DIR = PROJECT_ROOT / "data_alert"

REQUIRED_SOURCE_COLUMNS = {
    "IncidentId",
    "Timestamp",
}

# These are used to find the exact processed counterpart.
# Timestamp is the essential linkage in your current format.
TIMESTAMP_COLUMN = "Timestamp"
INCIDENT_COLUMN = "IncidentId"


# ============================================================
# HELPERS
# ============================================================

def fail(message: str) -> None:
    print(f"\n[ERROR] {message}")
    sys.exit(1)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_unique_file(filename: str) -> Path:
    candidates = [
        p for p in PROJECT_ROOT.rglob(filename)
        if OUTPUT_DIR not in p.parents
    ]

    # Prefer exact root/data locations if present.
    preferred = [
        PROJECT_ROOT / filename,
        PROJECT_ROOT / "data" / filename,
        PROJECT_ROOT / "data_train" / filename,
        PROJECT_ROOT / "data" / "splits" / filename,
        PROJECT_ROOT / "splits" / filename,
    ]

    for p in preferred:
        if p.exists() and p.is_file():
            return p

    if not candidates:
        fail(
            f"Could not find {filename} under {PROJECT_ROOT}"
        )

    if len(candidates) > 1:
        print(f"\n[ERROR] Multiple {filename} files found:")
        for p in candidates:
            print(f"  {p}")
        print("\nRefusing to guess. Keep only the intended split file.")
        sys.exit(1)

    return candidates[0]


def normalize_timestamp(series: pd.Series) -> pd.Series:
    return pd.to_datetime(
        series,
        utc=True,
        errors="coerce",
    )


def make_timestamp_occurrence(df: pd.DataFrame) -> pd.Series:
    return df["_timestamp_norm"].astype("string").fillna(
        "__INVALID_TIMESTAMP__"
    ).groupby(
        df["_timestamp_norm"].astype("string").fillna(
            "__INVALID_TIMESTAMP__"
        )
    ).cumcount()


def make_backup(path: Path, backup_dir: Path) -> Path:
    destination = backup_dir / path.name
    shutil.copy2(path, destination)
    return destination


# ============================================================
# START
# ============================================================

print("=" * 72)
print(" RL AGENT — LIVE ALERT HOLDOUT EXTRACTION")
print("=" * 72)
print()

if not PROJECT_ROOT.exists():
    fail(f"Project directory does not exist: {PROJECT_ROOT}")

if not SOURCE_FILE.exists():
    fail(f"Source dataset does not exist: {SOURCE_FILE}")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

timestamp_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
BACKUP_DIR = OUTPUT_DIR / "backup" / timestamp_tag
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

print(f"[INFO] Source dataset:")
print(f"       {SOURCE_FILE}")
print()

# ============================================================
# FIND TRAINING FILES
# ============================================================

TRAIN_PROCESSED = find_unique_file("train_processed.csv")
TRAIN_INCIDENT = find_unique_file("train_incident.csv")

TRAIN_INCIDENTS_TXT = None
txt_candidates = [
    p
    for p in PROJECT_ROOT.rglob("train_incidents.txt")
    if OUTPUT_DIR not in p.parents
]

if len(txt_candidates) == 1:
    TRAIN_INCIDENTS_TXT = txt_candidates[0]
elif len(txt_candidates) > 1:
    print("[WARN] Multiple train_incidents.txt files found.")
    print("       The CSV will still be updated.")
    print("       Text list will not be modified automatically.")

print("[INFO] Training files:")
print(f"       processed : {TRAIN_PROCESSED}")
print(f"       incident  : {TRAIN_INCIDENT}")
if TRAIN_INCIDENTS_TXT:
    print(f"       incidents : {TRAIN_INCIDENTS_TXT}")
print()

# ============================================================
# LOAD SOURCE
# ============================================================

print("[1/10] Loading original source dataset...")

source = pd.read_csv(
    SOURCE_FILE,
    low_memory=False,
)

missing = REQUIRED_SOURCE_COLUMNS - set(source.columns)
if missing:
    fail(
        "data_train.csv is missing required columns: "
        + ", ".join(sorted(missing))
    )

source["_timestamp_norm"] = normalize_timestamp(
    source[TIMESTAMP_COLUMN]
)

if source["_timestamp_norm"].isna().any():
    bad = int(source["_timestamp_norm"].isna().sum())
    fail(
        f"{bad} source rows have invalid timestamps. "
        "Fix timestamps before extracting live alerts."
    )

source["_source_row_number"] = range(len(source))

print(f"       rows: {len(source):,}")
print(
    f"       unique incidents: "
    f"{source[INCIDENT_COLUMN].nunique():,}"
)
print()

# ============================================================
# LOAD PROCESSED DATA
# ============================================================

print("[2/10] Loading already-processed training data...")

processed = pd.read_csv(
    TRAIN_PROCESSED,
    low_memory=False,
)

if TIMESTAMP_COLUMN not in processed.columns:
    fail(
        f"{TRAIN_PROCESSED} does not contain '{TIMESTAMP_COLUMN}'. "
        "The exact processed counterparts cannot be mapped safely."
    )

processed["_timestamp_norm"] = normalize_timestamp(
    processed[TIMESTAMP_COLUMN]
)

if processed["_timestamp_norm"].isna().any():
    bad = int(processed["_timestamp_norm"].isna().sum())
    fail(
        f"{bad} processed rows have invalid timestamps."
    )

print(f"       rows: {len(processed):,}")
print()

# ============================================================
# CREATE ONE-TO-ONE TIMESTAMP OCCURRENCE KEYS
# ============================================================

print("[3/10] Building source ↔ processed row mapping...")

source["_occurrence"] = (
    source.groupby("_timestamp_norm", sort=False).cumcount()
)

processed["_occurrence"] = (
    processed.groupby("_timestamp_norm", sort=False).cumcount()
)

processed_key_columns = [
    "_timestamp_norm",
    "_occurrence",
]

source_map = source[
    [
        "_source_row_number",
        INCIDENT_COLUMN,
        TIMESTAMP_COLUMN,
        "_timestamp_norm",
        "_occurrence",
    ]
].copy()

processed_locator = processed[
    [
        "_timestamp_norm",
        "_occurrence",
    ]
].copy()

processed_locator["_processed_row_number"] = range(len(processed))

mapped = source_map.merge(
    processed_locator,
    on=processed_key_columns,
    how="left",
    validate="one_to_one",
)

mapped_count = int(
    mapped["_processed_row_number"].notna().sum()
)

print(
    f"       source rows with processed counterpart: "
    f"{mapped_count:,} / {len(source):,}"
)

if mapped_count == 0:
    fail(
        "No source rows could be mapped to train_processed.csv."
    )

# Keep only rows that have a processed counterpart.
source_mappable = mapped[
    mapped["_processed_row_number"].notna()
].copy()

source_mappable["_processed_row_number"] = (
    source_mappable["_processed_row_number"].astype(int)
)

print()

# ============================================================
# SELECT 40 DIFFERENT INCIDENTS
# ============================================================

print("[4/10] Selecting independent live alerts...")

# We deliberately select ONE alert per incident.
# This means the selected incident IDs can be completely removed
# from training without leaving the same incident behind.
incident_candidates = (
    source_mappable.groupby(INCIDENT_COLUMN, as_index=False)
    .first()
)

available_incidents = len(incident_candidates)

if available_incidents < N_ALERTS:
    fail(
        f"Only {available_incidents} incidents have mapped "
        f"source/processed rows, but {N_ALERTS} are required."
    )

selected = incident_candidates.sample(
    n=N_ALERTS,
    random_state=RANDOM_SEED,
)

selected = selected.sort_values(
    by=["_timestamp_norm", INCIDENT_COLUMN]
).reset_index(drop=True)

selected["alert_id"] = [
    f"LIVE-{i:04d}"
    for i in range(1, len(selected) + 1)
]

selected_incidents = set(
    selected[INCIDENT_COLUMN].tolist()
)

print(f"       selected alerts: {len(selected):,}")
print(f"       selected incidents: {len(selected_incidents):,}")
print()

# ============================================================
# BUILD LIVE SOURCE DATA
# ============================================================

print("[5/10] Creating human-readable live source alerts...")

selected_source_numbers = selected["_source_row_number"].astype(int)

live_source = source[
    source["_source_row_number"].isin(
        selected_source_numbers
    )
].copy()

# Reorder according to selected alert order.
live_source = (
    selected[
        [
            "alert_id",
            "_source_row_number",
        ]
    ]
    .merge(
        live_source,
        on="_source_row_number",
        how="left",
        validate="one_to_one",
    )
    .sort_values("alert_id")
)

# ============================================================
# BUILD LIVE PROCESSED DATA
# ============================================================

print("[6/10] Extracting exact processed counterparts...")

selected_processed_numbers = (
    selected["_processed_row_number"].astype(int)
)

live_processed = processed.iloc[
    selected_processed_numbers.tolist()
].copy()

# Map alert IDs using processed row number.
processed_alert_id_map = dict(
    zip(
        selected["_processed_row_number"].astype(int),
        selected["alert_id"],
    )
)

live_processed.insert(
    0,
    "alert_id",
    [
        processed_alert_id_map[int(i)]
        for i in live_processed.index
    ],
)

# Keep processed rows in alert-id order.
live_processed["_sort_alert"] = live_processed["alert_id"]
live_processed = (
    live_processed
    .sort_values("_sort_alert")
    .drop(columns=["_sort_alert"])
    .reset_index(drop=True)
)

# ============================================================
# BUILD EXPLICIT MAPPING TABLE
# ============================================================

print("[7/10] Creating source ↔ processed lineage mapping...")

mapping = selected[
    [
        "alert_id",
        INCIDENT_COLUMN,
        TIMESTAMP_COLUMN,
        "_source_row_number",
        "_processed_row_number",
    ]
].copy()

mapping = mapping.rename(
    columns={
        "_source_row_number": "source_row_number",
        "_processed_row_number": "processed_row_number",
    }
)

# ============================================================
# VERIFY EXACT COUNTS
# ============================================================

if len(live_source) != N_ALERTS:
    fail(
        "Live source row count does not match requested alert count."
    )

if len(live_processed) != N_ALERTS:
    fail(
        "Live processed row count does not match requested alert count."
    )

if mapping["alert_id"].duplicated().any():
    fail("Duplicate alert_id detected.")

if mapping[INCIDENT_COLUMN].duplicated().any():
    fail(
        "More than one selected alert belongs to the same incident. "
        "This should never happen."
    )

# ============================================================
# BACKUP TRAINING FILES
# ============================================================

print("[8/10] Backing up training files before modification...")

backup_processed = make_backup(
    TRAIN_PROCESSED,
    BACKUP_DIR,
)

backup_incident = make_backup(
    TRAIN_INCIDENT,
    BACKUP_DIR,
)

backup_source = make_backup(
    SOURCE_FILE,
    BACKUP_DIR,
)

if TRAIN_INCIDENTS_TXT:
    backup_incidents_txt = make_backup(
        TRAIN_INCIDENTS_TXT,
        BACKUP_DIR,
    )
else:
    backup_incidents_txt = None

print(f"       backup directory: {BACKUP_DIR}")
print()

# ============================================================
# REMOVE SELECTED INCIDENTS FROM PROCESSED TRAIN
# ============================================================

print("[9/10] Removing selected incidents from training data...")

# Every source row belonging to a selected incident.
selected_source_all = source[
    source[INCIDENT_COLUMN].isin(selected_incidents)
].copy()

selected_source_all_numbers = set(
    selected_source_all["_source_row_number"].astype(int).tolist()
)

# Map ALL source rows of those incidents to processed rows.
all_incident_mapped = source_mappable[
    source_mappable[INCIDENT_COLUMN].isin(selected_incidents)
].copy()

processed_rows_to_remove = set(
    all_incident_mapped["_processed_row_number"]
    .astype(int)
    .tolist()
)

before_processed_rows = len(processed)

processed_keep_mask = ~processed.index.isin(
    processed_rows_to_remove
)

processed_updated = processed.loc[
    processed_keep_mask
].copy()

removed_processed_rows = (
    before_processed_rows - len(processed_updated)
)

# ============================================================
# REMOVE SELECTED INCIDENTS FROM TRAIN INCIDENT CSV
# ============================================================

incident_train = pd.read_csv(
    TRAIN_INCIDENT,
    low_memory=False,
)

if INCIDENT_COLUMN not in incident_train.columns:
    fail(
        f"{TRAIN_INCIDENT} does not contain '{INCIDENT_COLUMN}'."
    )

before_incident_rows = len(incident_train)

incident_keep_mask = ~incident_train[
    INCIDENT_COLUMN
].isin(selected_incidents)

incident_updated = incident_train.loc[
    incident_keep_mask
].copy()

removed_incident_rows = (
    before_incident_rows - len(incident_updated)
)

# Save modified training files.
processed_updated.to_csv(
    TRAIN_PROCESSED,
    index=False,
)

incident_updated.to_csv(
    TRAIN_INCIDENT,
    index=False,
)

# ============================================================
# UPDATE TRAIN INCIDENTS TEXT FILE
# ============================================================

if TRAIN_INCIDENTS_TXT:
    original_lines = TRAIN_INCIDENTS_TXT.read_text(
        encoding="utf-8",
        errors="ignore",
    ).splitlines()

    selected_as_strings = {
        str(x) for x in selected_incidents
    }

    filtered_lines = [
        line for line in original_lines
        if line.strip() not in selected_as_strings
    ]

    TRAIN_INCIDENTS_TXT.write_text(
        "\n".join(filtered_lines) + "\n",
        encoding="utf-8",
    )

# ============================================================
# FINAL INDEPENDENCE CHECK
# ============================================================

remaining_train_incidents = set(
    incident_updated[INCIDENT_COLUMN]
    .dropna()
    .astype(str)
    .tolist()
)

selected_incidents_str = {
    str(x) for x in selected_incidents
}

overlap = selected_incidents_str.intersection(
    remaining_train_incidents
)

if overlap:
    fail(
        "CRITICAL: selected live incidents still exist in "
        f"train_incident.csv: {sorted(overlap)[:20]}"
    )

# ============================================================
# SAVE LIVE ALERT DATA
# ============================================================

LIVE_SOURCE_FILE = OUTPUT_DIR / "live_source.csv"
LIVE_PROCESSED_FILE = OUTPUT_DIR / "live_processed.csv"
LIVE_MAPPING_FILE = OUTPUT_DIR / "live_mapping.csv"
LIVE_INCIDENTS_FILE = OUTPUT_DIR / "live_incidents.txt"
LIVE_MANIFEST_FILE = OUTPUT_DIR / "manifest.json"

# Remove internal helper columns from human-readable source.
source_helper_columns = [
    "_timestamp_norm",
    "_occurrence",
    "_source_row_number",
]

live_source_save = live_source.drop(
    columns=[
        c for c in source_helper_columns
        if c in live_source.columns
    ],
    errors="ignore",
)

# Remove helper columns from processed output.
processed_helper_columns = [
    "_timestamp_norm",
    "_occurrence",
]

live_processed_save = live_processed.drop(
    columns=[
        c for c in processed_helper_columns
        if c in live_processed.columns
    ],
    errors="ignore",
)

live_source_save.to_csv(
    LIVE_SOURCE_FILE,
    index=False,
)

live_processed_save.to_csv(
    LIVE_PROCESSED_FILE,
    index=False,
)

mapping.to_csv(
    LIVE_MAPPING_FILE,
    index=False,
)

LIVE_INCIDENTS_FILE.write_text(
    "\n".join(
        str(x) for x in selected[
            INCIDENT_COLUMN
        ].tolist()
    ) + "\n",
    encoding="utf-8",
)

# ============================================================
# MANIFEST
# ============================================================

manifest = {
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "project_root": str(PROJECT_ROOT),
    "source_dataset": str(SOURCE_FILE),
    "train_processed": str(TRAIN_PROCESSED),
    "train_incident": str(TRAIN_INCIDENT),
    "requested_alerts": N_ALERTS,
    "selected_alerts": len(live_source_save),
    "selected_incidents": len(selected_incidents),
    "random_seed": RANDOM_SEED,
    "selection_rule": "one alert per unique IncidentId",
    "mapping_rule": "normalized Timestamp + occurrence number",
    "source_preserved": True,
    "train_source_modified": False,
    "incident_overlap_after_extraction": len(overlap),
    "removed_processed_rows": removed_processed_rows,
    "removed_incident_rows": removed_incident_rows,
    "selected_source_rows_from_incidents": len(
        selected_source_all
    ),
    "files": {
        "live_source": str(LIVE_SOURCE_FILE),
        "live_processed": str(LIVE_PROCESSED_FILE),
        "live_mapping": str(LIVE_MAPPING_FILE),
        "live_incidents": str(LIVE_INCIDENTS_FILE),
        "backup_directory": str(BACKUP_DIR),
    },
    "sha256_before": {
        "source": sha256_file(backup_source),
        "train_processed": sha256_file(backup_processed),
        "train_incident": sha256_file(backup_incident),
    },
    "sha256_after": {
        "source": sha256_file(SOURCE_FILE),
        "train_processed": sha256_file(TRAIN_PROCESSED),
        "train_incident": sha256_file(TRAIN_INCIDENT),
    },
}

if backup_incidents_txt:
    manifest["sha256_before"]["train_incidents_txt"] = (
        sha256_file(backup_incidents_txt)
    )
    manifest["sha256_after"]["train_incidents_txt"] = (
        sha256_file(TRAIN_INCIDENTS_TXT)
    )

LIVE_MANIFEST_FILE.write_text(
    json.dumps(
        manifest,
        indent=2,
        default=str,
    ),
    encoding="utf-8",
)

# ============================================================
# FINAL REPORT
# ============================================================

print()
print("=" * 72)
print(" EXTRACTION COMPLETED")
print("=" * 72)
print()

print("[OK] Original source preserved:")
print(f"     {SOURCE_FILE}")
print()

print("[OK] Live-alert dataset created:")
print(f"     {OUTPUT_DIR}")
print(f"     {LIVE_SOURCE_FILE}")
print(f"     {LIVE_PROCESSED_FILE}")
print(f"     {LIVE_MAPPING_FILE}")
print(f"     {LIVE_INCIDENTS_FILE}")
print(f"     {LIVE_MANIFEST_FILE}")
print()

print("[OK] Training data updated:")
print(f"     {TRAIN_PROCESSED}")
print(f"     {TRAIN_INCIDENT}")
if TRAIN_INCIDENTS_TXT:
    print(f"     {TRAIN_INCIDENTS_TXT}")
print()

print("[OK] Selected alerts       :", len(live_source_save))
print("[OK] Selected incidents    :", len(selected_incidents))
print("[OK] Removed processed rows:", removed_processed_rows)
print("[OK] Removed incident rows :", removed_incident_rows)
print("[OK] Incident overlap      :", len(overlap))
print()

print("[OK] Backup:")
print(f"     {BACKUP_DIR}")
print()

print("First selected alerts:")
print(
    live_source_save[
        [
            "alert_id",
            INCIDENT_COLUMN,
            TIMESTAMP_COLUMN,
        ]
    ].head(10).to_string(index=False)
)

print()
print("=" * 72)
print(" READY FOR RL LIVE-ALERT REPLAY")
print("=" * 72)
print()
print("RL input:")
print(f"  {LIVE_PROCESSED_FILE}")
print()
print("Human-readable alert/history:")
print(f"  {LIVE_SOURCE_FILE}")
print()
print("Source ↔ processed lineage:")
print(f"  {LIVE_MAPPING_FILE}")
print()

