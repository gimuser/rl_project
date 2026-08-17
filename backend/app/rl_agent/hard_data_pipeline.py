from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .triage_env import INCIDENT_ID

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED = PROJECT_ROOT / "data" / "processed"
RL_DATA = PROJECT_ROOT / "data" / "rl_incident"
TRAIN_PATH = PROCESSED / "train_processed.csv"
TEST_PATH = PROCESSED / "test_processed.csv"
SPLIT_REPORT = RL_DATA / "split_report.json"


def _read_ids(path: Path, chunksize: int = 200_000) -> set[str]:
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
            f"[HARD SPLIT] {path.name}: unique_incidents={len(ids):,}",
            flush=True,
        )
    return ids


def prepare_data_split() -> dict:
    """Prepare an incident-disjoint TRAIN/VALIDATION/TEST view without copying millions of rows.

    TRAIN and TEST are the authoritative alert-level processed CSVs.  TEST is
    never used for model selection.  Validation IDs are sampled only from
    TRAIN incidents and are applied as a streaming filter during training.
    """
    if not TRAIN_PATH.exists():
        raise FileNotFoundError(TRAIN_PATH)
    if not TEST_PATH.exists():
        raise FileNotFoundError(TEST_PATH)

    train_ids = _read_ids(TRAIN_PATH)
    test_ids = _read_ids(TEST_PATH)

    overlap = train_ids & test_ids
    if overlap:
        raise RuntimeError(
            f"FATAL: TRAIN/TEST incident overlap detected: {len(overlap):,}"
        )

    ratio = float(os.getenv("REAL_RL_TRAIN_RATIO_WITHIN_TRAIN_VAL", "0.80"))
    ratio = min(max(ratio, 0.50), 0.95)
    seed = int(os.getenv("REAL_RL_VALIDATION_SEED", "4242"))

    ordered = np.array(sorted(train_ids), dtype=object)
    rng = np.random.default_rng(seed)
    rng.shuffle(ordered)

    train_count = int(len(ordered) * ratio)
    model_train_ids = {str(x) for x in ordered[:train_count]}
    validation_ids = {str(x) for x in ordered[train_count:]}

    if model_train_ids & validation_ids:
        raise RuntimeError("FATAL: TRAIN/VALIDATION incident overlap.")

    RL_DATA.mkdir(parents=True, exist_ok=True)

    (RL_DATA / "validation_incidents.txt").write_text(
        "\n".join(sorted(validation_ids)) + "\n",
        encoding="utf-8",
    )

    (RL_DATA / "train_model_incidents.txt").write_text(
        "\n".join(sorted(model_train_ids)) + "\n",
        encoding="utf-8",
    )

    report = {
        "data_mode": "hard_alert_streaming",
        "train_source": str(TRAIN_PATH),
        "test_source": str(TEST_PATH),
        "train_alert_rows": _row_count(TRAIN_PATH),
        "test_alert_rows": _row_count(TEST_PATH),
        "train_incidents_total": len(train_ids),
        "model_train_incidents": len(model_train_ids),
        "validation_incidents": len(validation_ids),
        "test_incidents": len(test_ids),
        "train_test_incident_overlap": 0,
        "train_validation_incident_overlap": 0,
        "validation_test_incident_overlap": len(validation_ids & test_ids),
        "validation_ratio_within_train": 1.0 - ratio,
        "validation_seed": seed,
        "alert_level_training": True,
        "representative_incident_files_used_for_training": False,
        "test_used_for_model_selection": False,
    }

    if validation_ids & test_ids:
        raise RuntimeError(
            f"FATAL: validation/TEST incident overlap: {len(validation_ids & test_ids):,}"
        )

    SPLIT_REPORT.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("=" * 78)
    print("HARD-DATA SPLIT READY")
    print(f"TRAIN alerts       : {report['train_alert_rows']:,}")
    print(f"TRAIN incidents    : {report['train_incidents_total']:,}")
    print(f"MODEL-TRAIN IDs    : {report['model_train_incidents']:,}")
    print(f"VALIDATION IDs     : {report['validation_incidents']:,}")
    print(f"TEST alerts        : {report['test_alert_rows']:,}")
    print(f"TEST incidents     : {report['test_incidents']:,}")
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


def _row_count(path: Path) -> int:
    with path.open("rb") as handle:
        return max(0, sum(1 for _ in handle) - 1)
