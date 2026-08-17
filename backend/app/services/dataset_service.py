from datetime import datetime
from pathlib import Path

import pandas as pd

from app.database.database import pipeline_collection


ROOT = Path(__file__).resolve().parents[3]

TRAIN_PATH = ROOT / "data" / "processed" / "train_processed.csv"
TEST_PATH = ROOT / "data" / "processed" / "test_processed.csv"


def _stats(path: Path):
    if not path.exists():
        raise FileNotFoundError(path)

    header = pd.read_csv(
        path,
        nrows=0,
    )

    rows = sum(
        1
        for _ in open(
            path,
            encoding="utf-8",
            errors="ignore",
        )
    ) - 1

    # Real missing-value count.
    df = pd.read_csv(path)

    return {
        "rows": int(rows),
        "columns": int(len(header.columns)),
        "missing_values": int(
            df.isna().sum().sum()
        ),
        "path": str(path),
    }


def _log_pipeline_event(
    event_type: str,
    stats: dict,
):
    try:
        pipeline_collection.insert_one(
            {
                "type": event_type,
                **stats,
                "timestamp": datetime.utcnow(),
            }
        )
    except Exception:
        pass


def import_train_dataset():

    stats = _stats(TRAIN_PATH)

    _log_pipeline_event(
        "train_import",
        stats,
    )

    return {
        "message": "Real processed train dataset verified",
        "imported_count": stats["rows"],
        "columns": stats["columns"],
        "missing_values": stats["missing_values"],
        "dataset": stats["path"],
        "real_data": True,
    }


def import_test_dataset():

    stats = _stats(TEST_PATH)

    _log_pipeline_event(
        "test_import",
        stats,
    )

    return {
        "message": "Real processed test dataset verified",
        "imported_count": stats["rows"],
        "columns": stats["columns"],
        "missing_values": stats["missing_values"],
        "dataset": stats["path"],
        "real_data": True,
    }


def get_pipeline_status():

    return {
        "status": "available",
        "train_dataset": str(TRAIN_PATH),
        "test_dataset": str(TEST_PATH),
        "real_data": True,
    }


def get_pipeline_statistics():

    train = _stats(TRAIN_PATH)
    test = _stats(TEST_PATH)

    return {
        "train_rows": train["rows"],
        "train_columns": train["columns"],
        "train_missing_values": train["missing_values"],
        "test_rows": test["rows"],
        "test_columns": test["columns"],
        "test_missing_values": test["missing_values"],
        "total_rows": train["rows"] + test["rows"],
        "total_columns": train["columns"],
        "missing_values": (
            train["missing_values"] + test["missing_values"]
        ),
        "real_data": True,
    }
