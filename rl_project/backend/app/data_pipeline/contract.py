"""The single data contract used by training, evaluation, and inference.

The repository's processed CSV files are intentionally treated as immutable
inputs.  Version 1 of their historic preprocessing fitted categorical encoders
separately per split and scaled time values using train+test data.  This module
keeps those files intact while providing a train-fitted runtime adapter for
the operational model.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Literal

import numpy as np
import pandas as pd

from app.config.settings import settings


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = settings.processed_data_dir
RAW_DIR = PROJECT_ROOT / "data"
SCHEMA_VERSION = "alert-observation-v2"
TARGET_COLUMN = "IncidentGrade"

# ActionGrouped and ActionGranular describe downstream handling and are not
# available when a new alert is triaged. IncidentId is a row identifier and
# LastVerdict may be an after-the-fact verdict, so neither is an observation.
FEATURE_COLUMNS = (
    "Category",
    "MitreTechniques",
    "EntityType",
    "EvidenceRole",
    "ThreatFamily",
    "OSFamily",
    "SuspicionLevel",
    "hour",
    "day",
    "month",
    "is_weekend",
)
CATEGORICAL_COLUMNS = FEATURE_COLUMNS[:7]
TIME_COLUMNS = FEATURE_COLUMNS[7:]
REQUIRED_PROCESSED_COLUMNS = (
    "IncidentId",
    "Timestamp",
    "Category",
    "MitreTechniques",
    TARGET_COLUMN,
    "ActionGrouped",
    "ActionGranular",
    "EntityType",
    "EvidenceRole",
    "ThreatFamily",
    "OSFamily",
    "SuspicionLevel",
    "LastVerdict",
    "hour",
    "day",
    "month",
    "is_weekend",
)

ALERT_FIELD_TO_DATASET_COLUMN = {
    "category": "Category",
    "mitre_techniques": "MitreTechniques",
    "entity_type": "EntityType",
    "evidence_role": "EvidenceRole",
    "threat_family": "ThreatFamily",
    "os_family": "OSFamily",
    "suspicion_level": "SuspicionLevel",
}


class DataContractError(ValueError):
    """Raised when a dataset or incoming alert violates the observation contract."""


@dataclass(frozen=True)
class DatasetAudit:
    split: str
    rows: int
    columns: int
    missing_values: int
    duplicate_rows: int
    class_distribution: dict[str, int]


def _processed_path(split: Literal["train", "test"]) -> Path:
    return PROCESSED_DIR / f"{split}_processed.csv"


@lru_cache(maxsize=2)
def load_processed_split(split: Literal["train", "test"]) -> pd.DataFrame:
    """Load and validate an existing processed split without rewriting it."""
    path = _processed_path(split)
    if not path.is_file():
        raise DataContractError(f"Processed {split} dataset is missing: {path}")

    frame = pd.read_csv(path)
    missing = [column for column in REQUIRED_PROCESSED_COLUMNS if column not in frame.columns]
    if missing:
        raise DataContractError(f"Processed {split} dataset is missing columns: {', '.join(missing)}")
    if frame.empty:
        raise DataContractError(f"Processed {split} dataset is empty")
    if frame[list(FEATURE_COLUMNS)].isna().any().any():
        raise DataContractError(f"Processed {split} dataset contains missing observation values")
    return frame


@lru_cache(maxsize=2)
def audit_processed_split(split: Literal["train", "test"]) -> DatasetAudit:
    frame = load_processed_split(split)
    distribution = frame[TARGET_COLUMN].value_counts(dropna=False).sort_index().to_dict()
    return DatasetAudit(
        split=split,
        rows=len(frame),
        columns=len(frame.columns),
        missing_values=int(frame.isna().sum().sum()),
        duplicate_rows=int(frame.duplicated().sum()),
        class_distribution={str(key): int(value) for key, value in distribution.items()},
    )


@lru_cache(maxsize=1)
def _train_feature_limits() -> tuple[dict[str, float], dict[str, tuple[float, float]]]:
    train = load_processed_split("train")
    # Reserve one normalized value for source categories first observed after
    # training. This is an explicit UNKNOWN bucket, not a fabricated category.
    categorical_maxima = {
        column: max(1.0, float(pd.to_numeric(train[column], errors="raise").max()) + 1.0)
        for column in CATEGORICAL_COLUMNS
    }
    timestamp = pd.to_datetime(train["Timestamp"], utc=True, errors="raise")
    time_values = _extract_time_features(timestamp)
    time_ranges = {
        column: (float(time_values[column].min()), float(time_values[column].max()))
        for column in TIME_COLUMNS
    }
    return categorical_maxima, time_ranges


def _extract_time_features(timestamp: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "hour": timestamp.dt.hour.astype(float),
            "day": timestamp.dt.day.astype(float),
            "month": timestamp.dt.month.astype(float),
            "is_weekend": (timestamp.dt.dayofweek >= 5).astype(float),
        },
        index=timestamp.index,
    )


def _scale(value: float, lower: float, upper: float) -> float:
    if upper <= lower:
        return 0.0
    # Values outside the historical training range remain explicit rather than
    # being clipped, so distribution shift is not silently hidden.
    return (value - lower) / (upper - lower)


def observations_for_split(split: Literal["train", "test"]) -> tuple[np.ndarray, np.ndarray]:
    """Return observations and target labels using the train-fitted contract.

    Train categorical codes come from the existing processed data. For test,
    the raw split is aligned with the existing processed rows and translated
    through the *training* codebook, fixing the historic split-local encoding
    mismatch without creating replacement datasets.
    """
    frame = load_processed_split(split)
    categorical_maxima, time_ranges = _train_feature_limits()
    values: dict[str, np.ndarray] = {}

    if split == "train":
        for column in CATEGORICAL_COLUMNS:
            raw_values = pd.to_numeric(frame[column], errors="raise").astype(float)
            values[column] = (raw_values / categorical_maxima[column]).to_numpy(dtype=np.float32)
    else:
        raw = _aligned_raw_split("test")
        mappings = _raw_to_train_codebook()
        for column in CATEGORICAL_COLUMNS:
            mapped = raw[column].astype(str).map(mappings[column])
            # A category legitimately absent from train has no encoder ID in
            # the historical file. Route it to the documented UNKNOWN bucket.
            mapped = mapped.fillna(categorical_maxima[column])
            values[column] = (mapped.astype(float) / categorical_maxima[column]).to_numpy(dtype=np.float32)

    timestamp = pd.to_datetime(frame["Timestamp"], utc=True, errors="raise")
    time_values = _extract_time_features(timestamp)
    for column in TIME_COLUMNS:
        lower, upper = time_ranges[column]
        values[column] = np.asarray(
            [_scale(float(item), lower, upper) for item in time_values[column]], dtype=np.float32
        )

    observations = np.column_stack([values[column] for column in FEATURE_COLUMNS]).astype(np.float32)
    labels = pd.to_numeric(frame[TARGET_COLUMN], errors="raise").to_numpy(dtype=np.int64)
    return observations, labels


@lru_cache(maxsize=2)
def _aligned_raw_split(split: Literal["train", "test"]) -> pd.DataFrame:
    path = RAW_DIR / f"data_{split}.csv"
    if not path.is_file():
        raise DataContractError(f"Raw {split} data is required for encoder compatibility but missing: {path}")
    raw = pd.read_csv(path).drop_duplicates().fillna("Unknown").reset_index(drop=True)
    processed = load_processed_split(split)
    if len(raw) != len(processed):
        raise DataContractError(
            f"Raw/processed {split} row counts differ ({len(raw)} != {len(processed)}); cannot safely align encodings"
        )
    # Timestamp is an immutable cross-check; do not rely only on row order.
    raw_timestamp = pd.to_datetime(raw["Timestamp"], utc=True, errors="raise")
    processed_timestamp = pd.to_datetime(processed["Timestamp"], utc=True, errors="raise")
    if not raw_timestamp.equals(processed_timestamp):
        raise DataContractError(f"Raw/processed {split} timestamps are not aligned")
    return raw


@lru_cache(maxsize=1)
def _raw_to_train_codebook() -> dict[str, dict[str, float]]:
    raw_train = _aligned_raw_split("train")
    processed_train = load_processed_split("train")
    mappings: dict[str, dict[str, float]] = {}
    for column in CATEGORICAL_COLUMNS:
        pairs = pd.DataFrame(
            {
                "raw": raw_train[column].astype(str),
                "code": pd.to_numeric(processed_train[column], errors="raise").astype(float),
            }
        ).drop_duplicates()
        if pairs["raw"].duplicated().any():
            raise DataContractError(f"Training encoder for {column} is not a one-to-one mapping")
        mappings[column] = dict(zip(pairs["raw"], pairs["code"], strict=True))
    return mappings


def observation_from_alert(alert: dict[str, Any]) -> np.ndarray:
    """Transform one canonical external alert into the model observation.

    Categorical fields may be supplied as the original source value or as a
    numeric value already encoded with the training contract. Timestamp must
    be present to produce the train-normalized time features.
    """
    mappings = _raw_to_train_codebook()
    categorical_maxima, time_ranges = _train_feature_limits()
    missing = [field for field in ALERT_FIELD_TO_DATASET_COLUMN if alert.get(field) is None]
    if alert.get("timestamp") is None:
        missing.append("timestamp")
    if missing:
        raise DataContractError("Alert lacks required state fields: " + ", ".join(missing))

    vector: list[float] = []
    for field, column in ALERT_FIELD_TO_DATASET_COLUMN.items():
        value = alert[field]
        if isinstance(value, bool):
            raise DataContractError(f"{field} must be a source value or encoded numeric value")
        if isinstance(value, (int, float)):
            encoded = float(value)
        else:
            encoded = mappings[column].get(str(value), categorical_maxima[column])
        vector.append(encoded / categorical_maxima[column])

    timestamp = pd.to_datetime(pd.Series([alert["timestamp"]]), utc=True, errors="coerce")
    if timestamp.isna().any():
        raise DataContractError("timestamp must be a valid ISO-8601 datetime")
    time_values = _extract_time_features(timestamp)
    for column in TIME_COLUMNS:
        lower, upper = time_ranges[column]
        vector.append(_scale(float(time_values.iloc[0][column]), lower, upper))
    return np.asarray(vector, dtype=np.float32)


def feature_schema() -> dict[str, Any]:
    """Serializable model-contract metadata."""
    categorical_maxima, time_ranges = _train_feature_limits()
    return {
        "version": SCHEMA_VERSION,
        "target_column": TARGET_COLUMN,
        "feature_order": list(FEATURE_COLUMNS),
        "excluded_columns": ["IncidentId", TARGET_COLUMN, "ActionGrouped", "ActionGranular", "LastVerdict"],
        "categorical_maxima": categorical_maxima,
        "time_ranges": {name: list(bounds) for name, bounds in time_ranges.items()},
        "train_rows": audit_processed_split("train").rows,
        "test_rows": audit_processed_split("test").rows,
    }


def clear_dataset_caches() -> None:
    """Test helper for isolated dataset-contract tests."""
    for func in (
        load_processed_split,
        audit_processed_split,
        _train_feature_limits,
        _aligned_raw_split,
        _raw_to_train_codebook,
    ):
        func.cache_clear()
