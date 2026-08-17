#!/usr/bin/env python3
"""Memory-safe Microsoft GUIDE -> RL incident processing.

Input is supplied at runtime through RL_AGENT_INPUT_DIR, otherwise
<repo>/data_finished is used. Large CSVs are always processed in chunks.

Flow:
1. Keep the 13 required incident columns and remove exact duplicate rows.
2. Preserve TEST when an IncidentId exists in both TRAIN and TEST; remove all
   rows for overlapping IncidentIds from TRAIN to prevent leakage.
3. Select 40 unique live incidents, then another 40 different incidents from
   the remaining TRAIN incidents only.
4. Remove ALL rows belonging to those 80 live incidents from TRAIN.
5. Fit categorical mappings and MinMax scaler only on the remaining TRAIN rows.
6. Produce data/processed/train_processed.csv and test_processed.csv.
7. Mirror those processed datasets to data/rl_incident/train_incident.csv
   and test_incident.csv.
8. Produce 80 independent live raw/processed alerts in data_alert.
9. Verify train/test/live incident disjointness and final schema.
"""
from __future__ import annotations

import csv
import json
import random
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

ROOT = Path(__file__).resolve().parents[1]
INPUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(
    __import__("os").environ.get("RL_AGENT_INPUT_DIR", ROOT / "data_finished")
).resolve()
WORK = ROOT / "data" / "processing_work"
BACKUP = ROOT / "data" / "processing_backups"
PROCESSED = ROOT / "data" / "processed"
RL = ROOT / "data" / "rl_incident"
ALERT = ROOT / "data_alert"
MODELS = ROOT / "models"
TRAIN = INPUT / "GUIDE_Train.csv"
TEST = INPUT / "GUIDE_Test.csv"

CHUNK_SIZE = 50_000
LIVE_BATCH_SIZE = 40
N_LIVE = LIVE_BATCH_SIZE * 2
SEED = 20260816

KEEP = [
    "IncidentId", "Timestamp", "Category", "MitreTechniques", "IncidentGrade",
    "ActionGrouped", "ActionGranular", "EntityType", "EvidenceRole",
    "ThreatFamily", "OSFamily", "SuspicionLevel", "LastVerdict",
]
FINAL = KEEP + ["hour", "day", "month", "is_weekend"]
CATS = [
    "Category", "MitreTechniques", "IncidentGrade", "ActionGrouped",
    "ActionGranular", "EntityType", "EvidenceRole", "ThreatFamily",
    "OSFamily", "SuspicionLevel", "LastVerdict",
]
SCALED = ["IncidentId", "hour", "day", "month", "is_weekend"]
FEATURES = [
    "Category", "MitreTechniques", "ActionGrouped", "ActionGranular",
    "EntityType", "EvidenceRole", "ThreatFamily", "OSFamily",
    "SuspicionLevel", "hour", "day", "month", "is_weekend",
]
ID = "IncidentId"
TARGET = "IncidentGrade"
DTYPE_HINTS = {"OSFamily": "string", "SuspicionLevel": "string"}


def log(msg: str) -> None:
    print(msg, flush=True)


def fail(msg: str) -> None:
    raise RuntimeError(msg)


def setup() -> None:
    for path in [WORK, BACKUP, PROCESSED, RL, ALERT, MODELS]:
        path.mkdir(parents=True, exist_ok=True)


def header(path: Path) -> list[str]:
    return list(pd.read_csv(path, nrows=0).columns)


def check_inputs() -> None:
    if not TRAIN.is_file() or not TEST.is_file():
        fail(f"Input directory must contain GUIDE_Train.csv and GUIDE_Test.csv: {INPUT}")
    for path in [TRAIN, TEST]:
        missing = [column for column in KEEP if column not in header(path)]
        if missing:
            fail(f"{path.name} missing required columns: {missing}")


def stream_clean(source: Path, target: Path, name: str) -> tuple[int, int, int, set[str]]:
    """Keep required columns, remove exact duplicate rows, and fill missing values.

    IncidentId is NOT deduplicated here because one incident can legitimately
    have multiple distinct alert/evidence rows.
    """
    if target.exists():
        target.unlink()
    total = kept = duplicate_rows = 0
    first = True
    incident_ids: set[str] = set()
    for chunk_no, chunk in enumerate(
        pd.read_csv(
            source,
            usecols=KEEP,
            chunksize=CHUNK_SIZE,
            low_memory=True,
            dtype=DTYPE_HINTS,
        ),
        1,
    ):
        before = len(chunk)
        chunk = chunk.drop_duplicates().fillna("Unknown")
        duplicate_rows += before - len(chunk)
        total += before
        kept += len(chunk)
        incident_ids.update(chunk[ID].astype(str))
        if not chunk.empty:
            chunk.to_csv(target, mode="w" if first else "a", header=first, index=False)
            first = False
        if chunk_no % 10 == 0:
            log(
                f"  [{name}] chunks={chunk_no:,} rows_seen={total:,} "
                f"rows_kept={kept:,} exact_dups={duplicate_rows:,}"
            )
    if first:
        fail(f"{name}: no usable rows after cleaning")
    return total, kept, duplicate_rows, incident_ids


def remove_incident_ids(source: Path, target: Path, excluded_ids: set[str]) -> tuple[int, int]:
    """Stream-copy rows whose IncidentId is not excluded."""
    if target.exists():
        target.unlink()
    first = True
    rows_seen = rows_kept = 0
    for chunk in pd.read_csv(
        source,
        usecols=KEEP,
        chunksize=CHUNK_SIZE,
        low_memory=True,
        dtype=DTYPE_HINTS,
    ):
        rows_seen += len(chunk)
        if excluded_ids:
            chunk = chunk[~chunk[ID].astype(str).isin(excluded_ids)]
        if not chunk.empty:
            chunk.to_csv(target, mode="w" if first else "a", header=first, index=False)
            first = False
            rows_kept += len(chunk)
    if first:
        fail(f"No rows remain after excluding incident IDs from {source}")
    return rows_seen, rows_kept


def reservoir_incident_rows(
    path: Path,
    n: int,
    excluded: set[str] | None = None,
    seed_offset: int = 0,
) -> pd.DataFrame:
    """Reservoir-sample one representative row per unique IncidentId."""
    excluded = excluded or set()
    rng = random.Random(SEED + seed_offset)
    sample: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for chunk in pd.read_csv(
        path,
        usecols=KEEP,
        chunksize=CHUNK_SIZE,
        low_memory=True,
        dtype=DTYPE_HINTS,
    ):
        for row in chunk.itertuples(index=False, name=None):
            item = dict(zip(KEEP, row))
            incident_id = str(item[ID])
            if incident_id in excluded or incident_id in seen_ids:
                continue
            seen_ids.add(incident_id)
            count = len(seen_ids)
            if len(sample) < n:
                sample.append(item)
            else:
                index = rng.randrange(count)
                if index < n:
                    sample[index] = item
    if len(sample) < n:
        fail(f"Only {len(sample)} eligible incidents available; {n} required")
    return pd.DataFrame(sample, columns=KEEP)


def fit_mappings(train_path: Path, excluded_ids: set[str]) -> dict[str, dict[str, int]]:
    values = {column: set() for column in CATS}
    for chunk in pd.read_csv(
        train_path,
        usecols=CATS + [ID],
        chunksize=CHUNK_SIZE,
        low_memory=True,
        dtype=DTYPE_HINTS,
    ):
        chunk = chunk[~chunk[ID].astype(str).isin(excluded_ids)]
        if chunk.empty:
            continue
        chunk = chunk.fillna("Unknown")
        for column in CATS:
            values[column].update(chunk[column].astype(str).unique())
    mappings = {
        column: {value: index for index, value in enumerate(sorted(values[column]))}
        for column in CATS
    }
    (MODELS / "category_mappings.json").write_text(json.dumps(mappings, indent=2), encoding="utf-8")
    return mappings


def transform_chunk(chunk: pd.DataFrame, mappings: dict[str, dict[str, int]]) -> pd.DataFrame:
    chunk = chunk.copy().fillna("Unknown")
    for column in CATS:
        chunk[column] = chunk[column].astype(str).map(mappings[column]).fillna(-1).astype("int32")
    chunk["IncidentId"] = pd.to_numeric(chunk["IncidentId"], errors="coerce")
    if chunk["IncidentId"].isna().any():
        fail("IncidentId contains non-numeric values after cleaning")
    chunk["Timestamp"] = pd.to_datetime(chunk["Timestamp"], utc=True, errors="raise")
    chunk["hour"] = chunk["Timestamp"].dt.hour.astype("int16")
    chunk["day"] = chunk["Timestamp"].dt.day.astype("int16")
    chunk["month"] = chunk["Timestamp"].dt.month.astype("int16")
    chunk["is_weekend"] = (chunk["Timestamp"].dt.dayofweek >= 5).astype("int8")
    return chunk


def fit_scaler(train_path: Path, mappings: dict[str, dict[str, int]]) -> MinMaxScaler:
    scaler = MinMaxScaler()
    fitted = False
    for chunk in pd.read_csv(
        train_path,
        usecols=KEEP,
        chunksize=CHUNK_SIZE,
        low_memory=True,
        dtype=DTYPE_HINTS,
    ):
        if chunk.empty:
            continue
        encoded = transform_chunk(chunk, mappings)
        scaler.partial_fit(encoded[SCALED].astype(float))
        fitted = True
    if not fitted:
        fail("No train rows remained for scaler fitting")
    joblib.dump({"scaler": scaler, "columns": SCALED}, MODELS / "feature_scaler.joblib")
    return scaler


def write_transformed(
    source: Path,
    target: Path,
    mappings: dict[str, dict[str, int]],
    scaler: MinMaxScaler,
) -> int:
    if target.exists():
        target.unlink()
    first = True
    total = 0
    for chunk in pd.read_csv(
        source,
        usecols=KEEP,
        chunksize=CHUNK_SIZE,
        low_memory=True,
        dtype=DTYPE_HINTS,
    ):
        if chunk.empty:
            continue
        transformed = transform_chunk(chunk, mappings)
        transformed[SCALED] = scaler.transform(transformed[SCALED].astype(float))
        transformed = transformed[FINAL]
        transformed.to_csv(target, mode="w" if first else "a", header=first, index=False)
        first = False
        total += len(transformed)
    if first:
        fail(f"No transformed rows written from {source}")
    return total


def write_ids(source: Path, target: Path) -> None:
    with source.open("r", encoding="utf-8", newline="") as source_handle, target.open(
        "w", encoding="utf-8"
    ) as target_handle:
        for row in csv.DictReader(source_handle):
            target_handle.write(str(row[ID]) + "\n")


def backup_outputs() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    destination = BACKUP / stamp
    destination.mkdir(parents=True, exist_ok=True)
    paths = [
        PROCESSED / "train_processed.csv",
        PROCESSED / "test_processed.csv",
        RL / "train_incident.csv",
        RL / "test_incident.csv",
        RL / "train_incidents.txt",
        RL / "test_incidents.txt",
        RL / "split_report.json",
        ALERT / "live_source.csv",
        ALERT / "live_processed.csv",
        ALERT / "live_mapping.csv",
        ALERT / "live_incidents.txt",
    ]
    for path in paths:
        if path.exists():
            shutil.copy2(path, destination / path.name)
    return destination


def verify_schema(path: Path) -> None:
    columns = header(path)
    if columns != FINAL:
        fail(f"Schema mismatch in {path}. Expected {FINAL}, got {columns}")


def main() -> None:
    setup()
    log("=" * 78)
    log("RL AGENT — GUIDE -> PROCESSED -> INCIDENT -> 80 LIVE")
    log("=" * 78)
    log(f"Input directory : {INPUT}")
    log(f"Chunk size      : {CHUNK_SIZE:,}")
    log(f"Live set        : {LIVE_BATCH_SIZE}+{LIVE_BATCH_SIZE}=80")
    check_inputs()

    train_clean = WORK / "train_clean.csv"
    test_clean = WORK / "test_clean.csv"
    train_exclusive = WORK / "train_exclusive.csv"
    train_model = WORK / "train_model.csv"

    log("\n[1/10] Keep 13 columns + remove exact duplicate rows")
    tr_total, tr_kept, tr_dups, train_ids_all = stream_clean(TRAIN, train_clean, "TRAIN")
    te_total, te_kept, te_dups, test_ids = stream_clean(TEST, test_clean, "TEST")

    overlap_ids = train_ids_all.intersection(test_ids)
    log(f"  TRAIN seen={tr_total:,} kept={tr_kept:,} exact_dups={tr_dups:,}")
    log(f"  TEST  seen={te_total:,} kept={te_kept:,} exact_dups={te_dups:,}")
    log(f"  cross-split IncidentId overlap={len(overlap_ids):,}")

    if overlap_ids:
        log("  TEST is preserved; removing all overlapping IncidentId rows from TRAIN")
        _, train_exclusive_rows = remove_incident_ids(train_clean, train_exclusive, overlap_ids)
    else:
        shutil.copy2(train_clean, train_exclusive)
        train_exclusive_rows = tr_kept

    train_ids = train_ids_all - overlap_ids
    if train_ids.intersection(test_ids):
        fail("Internal train/test overlap remained after resolution")
    log(f"  TRAIN rows after overlap resolution={train_exclusive_rows:,}")
    log("  TRAIN/TEST IncidentId overlap after resolution=0")

    log("\n[2/10] Select live batch 1 (40 unique incidents)")
    live_one = reservoir_incident_rows(train_exclusive, LIVE_BATCH_SIZE, seed_offset=1)
    live_one_ids = set(live_one[ID].astype(str))
    log(f"  batch1={len(live_one_ids):,}")

    log("[3/10] Select live batch 2 (40 different incidents)")
    live_two = reservoir_incident_rows(
        train_exclusive,
        LIVE_BATCH_SIZE,
        excluded=live_one_ids,
        seed_offset=2,
    )
    live_two_ids = set(live_two[ID].astype(str))
    log(f"  batch2={len(live_two_ids):,}")

    live_ids = live_one_ids | live_two_ids
    if len(live_ids) != N_LIVE:
        fail(f"Live set is not 80 unique incidents: {len(live_ids)}")
    if live_one_ids.intersection(live_two_ids):
        fail("Live batch 1 and batch 2 overlap")
    if live_ids.intersection(test_ids):
        fail("Live incidents overlap TEST")
    log("  batch1/batch2 overlap=0")
    log("  TEST/LIVE overlap=0")

    live_raw = pd.concat([live_one, live_two], ignore_index=True)
    live_raw = live_raw.sort_values(["Timestamp", ID]).reset_index(drop=True)

    log("\n[4/10] Remove all 80 live incidents from TRAIN")
    _, train_model_rows = remove_incident_ids(train_exclusive, train_model, live_ids)
    final_train_ids = train_ids - live_ids
    log(f"  TRAIN rows retained for model fitting={train_model_rows:,}")

    log("[5/10] Fit categorical mappings on final TRAIN only")
    mappings = fit_mappings(train_model, set())

    log("[6/10] Fit MinMax scaler incrementally on final TRAIN only")
    scaler = fit_scaler(train_model, mappings)

    log("\n[7/10] Transform TRAIN and TEST in bounded chunks")
    train_new_processed = WORK / "train_processed.new.csv"
    test_new_processed = WORK / "test_processed.new.csv"
    train_new_incident = WORK / "train_incident.new.csv"
    test_new_incident = WORK / "test_incident.new.csv"

    train_rows = write_transformed(train_model, train_new_processed, mappings, scaler)
    test_rows = write_transformed(test_clean, test_new_processed, mappings, scaler)
    shutil.copy2(train_new_processed, train_new_incident)
    shutil.copy2(test_new_processed, test_new_incident)
    for path in [train_new_processed, test_new_processed, train_new_incident, test_new_incident]:
        verify_schema(path)

    log("\n[8/10] Transform 80 live alerts using TRAIN-fitted artifacts")
    live_processed = transform_chunk(live_raw, mappings)
    live_processed[SCALED] = scaler.transform(live_processed[SCALED].astype(float))
    live_processed = live_processed[FINAL]
    live_alert_ids = [f"LIVE-{index:04d}" for index in range(1, N_LIVE + 1)]

    live_source_out = live_raw.copy()
    live_source_out.insert(0, "alert_id", live_alert_ids)
    live_processed.insert(0, "alert_id", live_alert_ids)
    live_source_out.to_csv(ALERT / "live_source.csv", index=False)
    live_processed.to_csv(ALERT / "live_processed.csv", index=False)
    pd.DataFrame(
        {
            "alert_id": live_alert_ids,
            ID: live_raw[ID].astype(str).tolist(),
            "Timestamp": live_raw["Timestamp"].tolist(),
        }
    ).to_csv(ALERT / "live_mapping.csv", index=False)
    (ALERT / "live_incidents.txt").write_text(
        "\n".join(live_raw[ID].astype(str).tolist()) + "\n", encoding="utf-8"
    )

    log("\n[9/10] Backup + replace outputs")
    backup = backup_outputs()
    for source, destination in [
        (train_new_processed, PROCESSED / "train_processed.csv"),
        (test_new_processed, PROCESSED / "test_processed.csv"),
        (train_new_incident, RL / "train_incident.csv"),
        (test_new_incident, RL / "test_incident.csv"),
    ]:
        source.replace(destination)
    write_ids(train_model, RL / "train_incidents.txt")
    write_ids(test_clean, RL / "test_incidents.txt")

    if final_train_ids.intersection(test_ids):
        fail("Final TRAIN/TEST overlap detected")
    if final_train_ids.intersection(live_ids):
        fail("Final TRAIN/LIVE overlap detected")
    if test_ids.intersection(live_ids):
        fail("Final TEST/LIVE overlap detected")
    if len(live_raw) != N_LIVE or live_raw[ID].nunique() != N_LIVE:
        fail("Final live dataset is not exactly 80 unique incidents")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_directory": str(INPUT),
        "memory_safe": True,
        "chunk_size": CHUNK_SIZE,
        "raw_keep_columns": KEEP,
        "final_columns": FINAL,
        "features": FEATURES,
        "target": TARGET,
        "incident_id": ID,
        "train_rows_seen": tr_total,
        "test_rows_seen": te_total,
        "train_exact_duplicate_rows_removed": tr_dups,
        "test_exact_duplicate_rows_removed": te_dups,
        "cross_split_overlap_incidents_resolved": len(overlap_ids),
        "train_rows_removed_due_cross_split_overlap": tr_kept - train_exclusive_rows,
        "train_rows_after_overlap_resolution": train_exclusive_rows,
        "train_rows_removed_for_live": train_exclusive_rows - train_model_rows,
        "train_processed_rows": train_rows,
        "test_processed_rows": test_rows,
        "live_batch_1": LIVE_BATCH_SIZE,
        "live_batch_2": LIVE_BATCH_SIZE,
        "live_rows": N_LIVE,
        "train_test_overlap": 0,
        "train_live_overlap": 0,
        "test_live_overlap": 0,
        "batch1_batch2_overlap": 0,
        "outputs": {
            "train_processed": str(PROCESSED / "train_processed.csv"),
            "test_processed": str(PROCESSED / "test_processed.csv"),
            "train_incident": str(RL / "train_incident.csv"),
            "test_incident": str(RL / "test_incident.csv"),
            "live_source": str(ALERT / "live_source.csv"),
            "live_processed": str(ALERT / "live_processed.csv"),
            "live_mapping": str(ALERT / "live_mapping.csv"),
        },
        "artifacts": {
            "category_mappings": str(MODELS / "category_mappings.json"),
            "feature_scaler": str(MODELS / "feature_scaler.joblib"),
        },
        "backup": str(backup),
    }
    (RL / "split_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    log("\n[10/10] Final verification")
    log(f"  data/processed/train_processed.csv = {train_rows:,} rows")
    log(f"  data/processed/test_processed.csv  = {test_rows:,} rows")
    log(f"  data/rl_incident/train_incident.csv = {train_rows:,} rows")
    log(f"  data/rl_incident/test_incident.csv  = {test_rows:,} rows")
    log("  data_alert/live_source.csv = 80 rows")
    log("  data_alert/live_processed.csv = 80 rows")
    log("  train/test/live overlaps = 0/0/0")
    log("  batch1/batch2 overlap = 0")
    log(f"  cross-split IncidentId overlap resolved = {len(overlap_ids):,}")
    log(f"  backup = {backup}")
    log("SUCCESS")


if __name__ == "__main__":
    try:
        main()
    except MemoryError:
        fail("MemoryError: reduce CHUNK_SIZE and rerun")
    except KeyboardInterrupt:
        fail("Interrupted before final replacement")
