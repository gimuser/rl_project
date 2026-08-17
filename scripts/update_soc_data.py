#!/usr/bin/env python3
"""Runtime-only Microsoft GUIDE dataset updater for the RL agent.

Downloads GUIDE train/test at runtime, keeps the incident-level columns used
by the existing pipeline, removes duplicate incidents, creates an independent
80-incident live holdout BEFORE fitting preprocessing artifacts, reuses the
existing cleaner/validator/encoder/feature-engineering/normalizer modules,
and replaces data/rl_incident train/test files.

The downloaded dataset and intermediate files are intentionally ignored by
Git and are never committed to the repository.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_SOC_UPDATE = PROJECT_ROOT / "data_soc_update"
RAW_DIR = DATA_SOC_UPDATE / "raw"
WORK_DIR = DATA_SOC_UPDATE / "work"
BACKUP_DIR = DATA_SOC_UPDATE / "backup"
MANIFEST_PATH = DATA_SOC_UPDATE / "update_manifest.json"
RL_INCIDENT_DIR = PROJECT_ROOT / "data" / "rl_incident"
DATA_ALERT_DIR = PROJECT_ROOT / "data_alert"

TRAIN_RAW_NAME = "GUIDE_Train.csv"
TEST_RAW_NAME = "GUIDE_Test.csv"
TRAIN_WORK = WORK_DIR / "data_train.csv"
TEST_WORK = WORK_DIR / "data_test.csv"

FINAL_TRAIN = RL_INCIDENT_DIR / "train_incident.csv"
FINAL_TEST = RL_INCIDENT_DIR / "test_incident.csv"
TRAIN_IDS = RL_INCIDENT_DIR / "train_incidents.txt"
TEST_IDS = RL_INCIDENT_DIR / "test_incidents.txt"
SPLIT_REPORT = RL_INCIDENT_DIR / "split_report.json"

LIVE_SOURCE = DATA_ALERT_DIR / "live_source.csv"
LIVE_PROCESSED = DATA_ALERT_DIR / "live_processed.csv"
LIVE_MAPPING = DATA_ALERT_DIR / "live_mapping.csv"
LIVE_INCIDENTS = DATA_ALERT_DIR / "live_incidents.txt"

KAGGLE_DATASETS = [
    "microsoft/microsoft-security-incident-prediction",
    "avijitjana101/microsoft-soc-dataset",
]

KEEP_COLUMNS = [
    "IncidentId", "Timestamp", "Category", "MitreTechniques", "IncidentGrade",
    "ActionGrouped", "ActionGranular", "EntityType", "EvidenceRole",
    "ThreatFamily", "OSFamily", "SuspicionLevel", "LastVerdict",
]
FINAL_COLUMNS = KEEP_COLUMNS + ["hour", "day", "month", "is_weekend"]
FEATURE_COLUMNS = [
    "Category", "MitreTechniques", "ActionGrouped", "ActionGranular",
    "EntityType", "EvidenceRole", "ThreatFamily", "OSFamily",
    "SuspicionLevel", "LastVerdict", "hour", "day", "month", "is_weekend",
]
TARGET_COLUMN = "IncidentGrade"
INCIDENT_COLUMN = "IncidentId"
N_LIVE = 80
RANDOM_SEED = 20260816


def log(message: str = "") -> None:
    print(message, flush=True)


def stop(message: str, exc: Exception | None = None) -> None:
    log(f"[ERROR] {message}" + (f": {exc}" if exc else ""))
    raise SystemExit(1)


def ensure_package(import_name: str, pip_name: str) -> None:
    try:
        __import__(import_name)
    except ImportError:
        log(f"[INSTALL] Installing {pip_name} ...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
        except subprocess.CalledProcessError as exc:
            stop(f"Could not install {pip_name}", exc)


def find_file(root: Path, filename: str) -> Path | None:
    hits = sorted(root.rglob(filename), key=lambda p: (len(p.parts), str(p)))
    return hits[0] if hits else None


def download_dataset() -> tuple[Path, Path, str]:
    ensure_package("kagglehub", "kagglehub")
    import kagglehub

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None

    for slug in KAGGLE_DATASETS:
        log(f"[DOWNLOAD] {slug}")
        try:
            try:
                root = Path(kagglehub.dataset_download(slug, path=str(RAW_DIR)))
            except TypeError:
                root = Path(kagglehub.dataset_download(slug))
            train_path = find_file(root, TRAIN_RAW_NAME)
            test_path = find_file(root, TEST_RAW_NAME)
            if train_path and test_path:
                log(f"[DOWNLOAD] train = {train_path}")
                log(f"[DOWNLOAD] test  = {test_path}")
                return train_path, test_path, slug
            last_error = FileNotFoundError(
                f"{TRAIN_RAW_NAME} and {TEST_RAW_NAME} were not found under {root}"
            )
            log(f"[WARN] {last_error}")
        except Exception as exc:
            last_error = exc
            log(f"[WARN] {exc}")

    stop(
        "Kaggle download failed. Configure Kaggle authentication/access and rerun",
        last_error,
    )
    raise AssertionError("unreachable")


def validate_raw_columns(df: pd.DataFrame, name: str) -> None:
    missing = [c for c in KEEP_COLUMNS if c not in df.columns]
    if missing:
        stop(f"{name} is missing required columns: {missing}")


def dedup_incidents(df: pd.DataFrame, name: str) -> tuple[pd.DataFrame, int]:
    before = len(df)
    dup = df[INCIDENT_COLUMN].duplicated(keep=False)
    if not dup.any():
        return df, 0

    conflicts = (
        df.loc[dup]
        .groupby(INCIDENT_COLUMN)[TARGET_COLUMN]
        .nunique(dropna=False)
    )
    bad = conflicts[conflicts > 1]
    if not bad.empty:
        stop(
            f"{name} has conflicting {TARGET_COLUMN} labels for incident IDs: "
            f"{bad.index[:10].tolist()}"
        )

    out = df.drop_duplicates(subset=[INCIDENT_COLUMN], keep="first").copy()
    removed = before - len(out)
    log(f"[DEDUP] {name}: removed {removed:,} duplicate incident rows")
    return out, removed


def ids_to_file(path: Path, ids: pd.Series) -> None:
    path.write_text("\n".join(ids.astype(str).tolist()) + "\n", encoding="utf-8")


def run_existing_pipeline(train: pd.DataFrame, test: pd.DataFrame):
    pipeline_dir = PROJECT_ROOT / "backend" / "app" / "data_pipeline"
    sys.path.insert(0, str(pipeline_dir))

    from cleaner import clean_data
    from encoder import encode_data
    from feature_engineering import create_features
    from normalizer import normalize_data
    from validator import validate_data

    log("[PIPELINE] clean_data()")
    train = clean_data(train)
    test = clean_data(test)

    log("[PIPELINE] validate_data()")
    if not validate_data(train, "TRAIN"):
        stop("Existing train validation failed")
    if not validate_data(test, "TEST"):
        stop("Existing test validation failed")

    log("[PIPELINE] encode_data() — mappings fit on train only")
    train, test = encode_data(train, test)

    log("[PIPELINE] create_features()")
    train, test = create_features(train, test)

    log("[PIPELINE] normalize_data() — scaler fit on train only")
    train, test = normalize_data(train, test)
    return train, test


def process_live_with_fitted_artifacts(live_raw: pd.DataFrame) -> pd.DataFrame:
    pipeline_dir = PROJECT_ROOT / "backend" / "app" / "data_pipeline"
    sys.path.insert(0, str(pipeline_dir))

    from encoder import load_mappings
    from feature_engineering import create_features
    from normalizer import load_scaler

    live = live_raw.copy()
    mappings = load_mappings()
    for column, mapping in mappings.items():
        if column in live.columns:
            live[column] = live[column].astype(str).map(mapping).fillna(-1).astype(int)

    live, _ = create_features(live, live.copy())
    artifact = load_scaler()
    live[artifact["columns"]] = artifact["scaler"].transform(live[artifact["columns"]])
    return live


def main() -> None:
    started = datetime.now(timezone.utc)
    log("=" * 78)
    log("RL AGENT — MICROSOFT GUIDE DATA UPDATE")
    log("=" * 78)
    log(f"Project root : {PROJECT_ROOT}")
    log(f"Live holdout : {N_LIVE} independent incidents")

    for directory in [RAW_DIR, WORK_DIR, BACKUP_DIR, RL_INCIDENT_DIR, DATA_ALERT_DIR]:
        directory.mkdir(parents=True, exist_ok=True)

    train_path, test_path, dataset_slug = download_dataset()

    log("\n[LOAD] Reading raw GUIDE files")
    train_raw = pd.read_csv(train_path, low_memory=False)
    test_raw = pd.read_csv(test_path, low_memory=False)
    log(f"[LOAD] raw train: {len(train_raw):,} rows / {len(train_raw.columns)} columns")
    log(f"[LOAD] raw test : {len(test_raw):,} rows / {len(test_raw.columns)} columns")

    validate_raw_columns(train_raw, TRAIN_RAW_NAME)
    validate_raw_columns(test_raw, TEST_RAW_NAME)

    log("\n[SELECT] Keeping only the required incident columns")
    train = train_raw[KEEP_COLUMNS].drop_duplicates().copy()
    test = test_raw[KEEP_COLUMNS].drop_duplicates().copy()
    train, train_duplicates_removed = dedup_incidents(train, "TRAIN")
    test, test_duplicates_removed = dedup_incidents(test, "TEST")

    overlap = set(train[INCIDENT_COLUMN]) & set(test[INCIDENT_COLUMN])
    if overlap:
        stop(f"Train/test incident leakage detected: {len(overlap):,} shared IncidentId values")
    log("[CHECK] raw train/test IncidentId overlap: 0")

    if len(train) <= N_LIVE:
        stop(f"Not enough train incidents to reserve {N_LIVE} live alerts")

    log("\n[LIVE] Selecting 80 unique live incidents BEFORE preprocessing")
    live_ids = train[[INCIDENT_COLUMN, "Timestamp"]].sample(
        n=N_LIVE, random_state=RANDOM_SEED
    )
    live_ids = live_ids.sort_values(["Timestamp", INCIDENT_COLUMN]).reset_index(drop=True)
    live_set = set(live_ids[INCIDENT_COLUMN].tolist())

    live_raw = train[train[INCIDENT_COLUMN].isin(live_set)].copy()
    train_core = train[~train[INCIDENT_COLUMN].isin(live_set)].copy()
    log(f"[LIVE] selected: {len(live_raw):,}")
    log(f"[LIVE] train retained for fitting: {len(train_core):,}")

    if len(live_raw) != N_LIVE or live_raw[INCIDENT_COLUMN].nunique() != N_LIVE:
        stop("Live holdout is not exactly 80 unique incidents")

    # Runtime-only work copies. These are ignored by Git.
    train_core.to_csv(TRAIN_WORK, index=False)
    test.to_csv(TEST_WORK, index=False)

    log("\n[PIPELINE] Running the existing backend/app/data_pipeline components")
    train_processed, test_processed = run_existing_pipeline(train_core, test)

    missing_final = [
        c for c in FINAL_COLUMNS
        if c not in train_processed.columns or c not in test_processed.columns
    ]
    if missing_final:
        stop(f"Existing pipeline did not produce the required final schema: {missing_final}")

    train_processed = train_processed[FINAL_COLUMNS].copy()
    test_processed = test_processed[FINAL_COLUMNS].copy()

    log("[PIPELINE] Transforming live holdout using the already-fitted train artifacts")
    live_processed = process_live_with_fitted_artifacts(live_raw)[FINAL_COLUMNS].copy()

    # Back up only the existing tracked output files before replacing them.
    backup_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_run = BACKUP_DIR / backup_tag
    backup_run.mkdir(parents=True, exist_ok=True)
    for path in [FINAL_TRAIN, FINAL_TEST, TRAIN_IDS, TEST_IDS, SPLIT_REPORT]:
        if path.exists():
            shutil.copy2(path, backup_run / path.name)

    before_train_rows = int(pd.read_csv(FINAL_TRAIN, low_memory=False).shape[0]) if FINAL_TRAIN.exists() else None
    before_test_rows = int(pd.read_csv(FINAL_TEST, low_memory=False).shape[0]) if FINAL_TEST.exists() else None

    log("\n[REPLACE] Writing new RL incident train/test files")
    train_processed.to_csv(FINAL_TRAIN, index=False)
    test_processed.to_csv(FINAL_TEST, index=False)
    ids_to_file(TRAIN_IDS, train_core[INCIDENT_COLUMN])
    ids_to_file(TEST_IDS, test[INCIDENT_COLUMN])

    # Live data follows the existing data_alert convention.
    alert_ids = [f"LIVE-{i:04d}" for i in range(1, N_LIVE + 1)]
    live_source = live_raw.copy()
    live_source.insert(0, "alert_id", alert_ids)
    live_processed.insert(0, "alert_id", alert_ids)
    live_source.to_csv(LIVE_SOURCE, index=False)
    live_processed.to_csv(LIVE_PROCESSED, index=False)
    pd.DataFrame({
        "alert_id": alert_ids,
        INCIDENT_COLUMN: live_raw[INCIDENT_COLUMN].tolist(),
        "Timestamp": live_raw["Timestamp"].tolist(),
    }).to_csv(LIVE_MAPPING, index=False)
    ids_to_file(LIVE_INCIDENTS, live_raw[INCIDENT_COLUMN])

    train_ids = set(train_core[INCIDENT_COLUMN].tolist())
    test_ids = set(test[INCIDENT_COLUMN].tolist())
    live_ids_final = set(live_raw[INCIDENT_COLUMN].tolist())
    if train_ids & test_ids:
        stop("Final train/test IncidentId overlap detected")
    if train_ids & live_ids_final:
        stop("Final train/live IncidentId overlap detected")
    if test_ids & live_ids_final:
        stop("Final test/live IncidentId overlap detected")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_slug": dataset_slug,
        "runtime_only_download": True,
        "kept_columns": KEEP_COLUMNS,
        "final_columns": FINAL_COLUMNS,
        "features": FEATURE_COLUMNS,
        "incident_id": INCIDENT_COLUMN,
        "target": TARGET_COLUMN,
        "train_rows": int(len(train_processed)),
        "test_rows": int(len(test_processed)),
        "train_incidents": int(train_processed[INCIDENT_COLUMN].nunique()),
        "test_incidents": int(test_processed[INCIDENT_COLUMN].nunique()),
        "live_rows": int(len(live_processed)),
        "live_incidents": int(live_processed[INCIDENT_COLUMN].nunique()),
        "train_test_overlap": int(len(train_ids & test_ids)),
        "train_live_overlap": int(len(train_ids & live_ids_final)),
        "test_live_overlap": int(len(test_ids & live_ids_final)),
        "train_duplicate_rows_removed": int(train_duplicates_removed),
        "test_duplicate_rows_removed": int(test_duplicates_removed),
        "before": {"train_rows": before_train_rows, "test_rows": before_test_rows},
        "after": {"train_rows": int(len(train_processed)), "test_rows": int(len(test_processed))},
        "output_schema_matches_requested": list(train_processed.columns) == FINAL_COLUMNS and list(test_processed.columns) == FINAL_COLUMNS,
        "git_safe": True,
        "backup": str(backup_run),
    }

    SPLIT_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    MANIFEST_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    log("\n" + "=" * 78)
    log("FINAL STATUS")
    log("=" * 78)
    log(f"[OK] Train rows       : {len(train_processed):,}")
    log(f"[OK] Test rows        : {len(test_processed):,}")
    log(f"[OK] Live alerts      : {len(live_processed):,}")
    log(f"[OK] Final columns    : {len(FINAL_COLUMNS)}")
    log(f"[OK] Train/Test overlap: 0")
    log(f"[OK] Train/Live overlap: 0")
    log(f"[OK] Test/Live overlap : 0")
    log(f"[INFO] Previous train rows: {before_train_rows}")
    log(f"[INFO] Previous test rows : {before_test_rows}")
    log(f"[INFO] Backup             : {backup_run}")
    log(f"[INFO] Manifest           : {MANIFEST_PATH}")
    log(f"[INFO] Elapsed            : {datetime.now(timezone.utc) - started}")
    log("[OK] Downloaded raw data remain outside Git under data_soc_update/raw/")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n[ERROR] Interrupted by user")
        raise SystemExit(130)
    except SystemExit:
        raise
    except Exception as exc:
        stop("Unexpected failure", exc)
