from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from .triage_env import INCIDENT_ID

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED = PROJECT_ROOT / "data" / "processed"
RL_DATA = PROJECT_ROOT / "data" / "rl_incident"
TRAIN_PATH = PROCESSED / "train_processed.csv"
TEST_PATH = PROCESSED / "test_processed.csv"
INCIDENT_TRAIN_PATH = RL_DATA / "train_incident.csv"
INCIDENT_TEST_PATH = RL_DATA / "test_incident.csv"
SPLIT_REPORT = RL_DATA / "split_report.json"


def _read_ids(path: Path, chunksize: int = 100_000) -> set[str]:
    ids: set[str] = set()
    for chunk in pd.read_csv(
        path,
        usecols=[INCIDENT_ID],
        dtype={INCIDENT_ID: "string"},
        chunksize=chunksize,
        low_memory=True,
    ):
        values = chunk[INCIDENT_ID].dropna().astype(str)
        ids.update(values.tolist())
    return ids


def _row_count(path: Path) -> int:
    result = subprocess.run(
        ["wc", "-l", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return max(0, int(result.stdout.strip().split()[0]) - 1)


def _read_authoritative_incident_ids(path: Path, label: str) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(path)

    ids = _read_ids(path)
    print(
        f"[HARD SPLIT] {label}: authoritative incidents={len(ids):,}",
        flush=True,
    )
    return ids


def _fallback_read_processed_ids(path: Path, label: str) -> set[str]:
    print(
        f"[HARD SPLIT] WARNING: {label} incident file unavailable; "
        f"falling back to streaming {path.name}",
        flush=True,
    )
    return _read_ids(path)


def prepare_data_split() -> dict:
    """Prepare incident-disjoint TRAIN/VALIDATION/TEST without full-dataframe load."""
    if not TRAIN_PATH.exists():
        raise FileNotFoundError(TRAIN_PATH)
    if not TEST_PATH.exists():
        raise FileNotFoundError(TEST_PATH)

    print("[HARD SPLIT] using authoritative incident-level split files", flush=True)

    if INCIDENT_TRAIN_PATH.exists():
        train_ids = _read_authoritative_incident_ids(INCIDENT_TRAIN_PATH, "train_incident.csv")
    else:
        train_ids = _fallback_read_processed_ids(TRAIN_PATH, "TRAIN")

    if INCIDENT_TEST_PATH.exists():
        test_ids = _read_authoritative_incident_ids(INCIDENT_TEST_PATH, "test_incident.csv")
    else:
        test_ids = _fallback_read_processed_ids(TEST_PATH, "TEST")

    if not train_ids:
        raise RuntimeError("FATAL: TRAIN incident set is empty.")
    if not test_ids:
        raise RuntimeError("FATAL: TEST incident set is empty.")

    print("[HARD SPLIT] checking TRAIN/TEST incident overlap", flush=True)
    overlap = train_ids & test_ids
    if overlap:
        raise RuntimeError(f"FATAL: TRAIN/TEST incident overlap detected: {len(overlap):,}")
    print("[HARD SPLIT] TRAIN/TEST incident overlap: 0", flush=True)

    ratio = float(os.getenv("REAL_RL_TRAIN_RATIO_WITHIN_TRAIN_VAL", "0.80"))
    ratio = min(max(ratio, 0.50), 0.95)
    seed = int(os.getenv("REAL_RL_VALIDATION_SEED", "4242"))

    ordered = list(train_ids)
    rng = np.random.default_rng(seed)
    rng.shuffle(ordered)

    train_count = int(len(ordered) * ratio)
    model_train_ids = set(ordered[:train_count])
    validation_ids = set(ordered[train_count:])

    if model_train_ids & validation_ids:
        raise RuntimeError("FATAL: TRAIN/VALIDATION incident overlap.")

    val_test_overlap = validation_ids & test_ids
    if val_test_overlap:
        raise RuntimeError(f"FATAL: validation/TEST incident overlap: {len(val_test_overlap):,}")

    print(
        f"[HARD SPLIT] model-train incidents={len(model_train_ids):,} "
        f"validation incidents={len(validation_ids):,}",
        flush=True,
    )

    RL_DATA.mkdir(parents=True, exist_ok=True)

    (RL_DATA / "validation_incidents.txt").write_text(
        "\n".join(sorted(validation_ids)) + "\n",
        encoding="utf-8",
    )
    (RL_DATA / "train_model_incidents.txt").write_text(
        "\n".join(sorted(model_train_ids)) + "\n",
        encoding="utf-8",
    )

    print("[HARD SPLIT] fast row counts via wc -l", flush=True)
    train_alert_rows = _row_count(TRAIN_PATH)
    test_alert_rows = _row_count(TEST_PATH)

    report = {
        "data_mode": "hard_alert_streaming",
        "train_source": str(TRAIN_PATH),
        "test_source": str(TEST_PATH),
        "train_alert_rows": train_alert_rows,
        "test_alert_rows": test_alert_rows,
        "train_rows": train_alert_rows,
        "test_rows": test_alert_rows,
        "train_incidents_total": len(train_ids),
        "train_incidents": len(train_ids),
        "model_train_incidents": len(model_train_ids),
        "validation_incidents": len(validation_ids),
        "test_incidents": len(test_ids),
        "validation_rows": None,
        "train_test_incident_overlap": 0,
        "incident_overlap": 0,
        "train_validation_incident_overlap": 0,
        "validation_test_incident_overlap": 0,
        "validation_ratio_within_train": 1.0 - ratio,
        "validation_seed": seed,
        "alert_level_training": True,
        "representative_incident_files_used_for_training": False,
        "test_used_for_model_selection": False,
    }

    SPLIT_REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=" * 78)
    print("HARD-DATA SPLIT READY")
    print(f"TRAIN alerts       : {train_alert_rows:,}")
    print(f"TRAIN incidents    : {len(train_ids):,}")
    print(f"MODEL-TRAIN IDs    : {len(model_train_ids):,}")
    print(f"VALIDATION IDs     : {len(validation_ids):,}")
    print(f"TEST alerts        : {test_alert_rows:,}")
    print(f"TEST incidents     : {len(test_ids):,}")
    print("TRAIN/TEST overlap : 0")
    print("VAL/TEST overlap   : 0")
    print("=" * 78)

    return {
        "train_path": TRAIN_PATH,
        "test_path": TEST_PATH,
        "validation_ids": validation_ids,
        "model_train_ids": model_train_ids,
        "train_incidents": train_ids,
        "test_incidents": test_ids,
        "report": report,
    }
