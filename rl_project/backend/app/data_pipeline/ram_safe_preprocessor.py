"""RAM-safe equivalent of the existing data_pipeline.

Preserves the old pipeline's semantics while processing CSV files in chunks.
Expected source columns are the 13 columns validated by validator.py.

Stages preserved from the original pipeline:
  1. exact row de-duplication is assumed to have happened upstream
  2. fill missing values with "Unknown"
  3. validate the 13 required columns
  4. categorical mappings learned ONLY from TRAIN, sorted like encoder.py
  5. TEST uses TRAIN mappings; unseen values become -1
  6. hour/day/month/is_weekend from Timestamp
  7. MinMax normalization learned ONLY from TRAIN

Unlike preprocessor.py, this module never loads the full train and test
DataFrames at once. It makes several sequential passes over the CSV files.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

import pandas as pd


SOURCE_COLUMNS = [
    "IncidentId",
    "Timestamp",
    "Category",
    "MitreTechniques",
    "IncidentGrade",
    "ActionGrouped",
    "ActionGranular",
    "EntityType",
    "EvidenceRole",
    "ThreatFamily",
    "OSFamily",
    "SuspicionLevel",
    "LastVerdict",
]

CATEGORICAL_COLUMNS = [
    "Category",
    "MitreTechniques",
    "IncidentGrade",
    "ActionGrouped",
    "ActionGranular",
    "EntityType",
    "EvidenceRole",
    "ThreatFamily",
    "OSFamily",
    "SuspicionLevel",
    "LastVerdict",
]

NUMERIC_COLUMNS = [
    "IncidentId",
    "hour",
    "day",
    "month",
    "is_weekend",
]

OUTPUT_COLUMNS = SOURCE_COLUMNS + [
    "hour",
    "day",
    "month",
    "is_weekend",
]

DEFAULT_CHUNK_SIZE = 50_000


def _check_header(path: Path) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
    if header != SOURCE_COLUMNS:
        raise ValueError(
            f"{path}: expected exactly these 13 columns:\n"
            f"{SOURCE_COLUMNS}\nGot:\n{header}"
        )


def _chunks(path: Path, chunk_size: int) -> Iterable[pd.DataFrame]:
    _check_header(path)
    for chunk in pd.read_csv(
        path,
        chunksize=chunk_size,
        keep_default_na=True,
        na_filter=True,
        low_memory=True,
    ):
        # Same cleaner semantics as the old pipeline.
        chunk = chunk.fillna("Unknown")
        yield chunk


def _prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(df["Timestamp"], errors="raise", utc=False)
    df["hour"] = ts.dt.hour.astype("int64")
    df["day"] = ts.dt.day.astype("int64")
    df["month"] = ts.dt.month.astype("int64")
    df["is_weekend"] = (ts.dt.dayofweek >= 5).astype("int64")
    return df


def _collect_mappings(train_path: Path, chunk_size: int) -> dict[str, dict[str, int]]:
    values = {column: set() for column in CATEGORICAL_COLUMNS}
    for chunk in _chunks(train_path, chunk_size):
        for column in CATEGORICAL_COLUMNS:
            values[column].update(chunk[column].astype(str).unique().tolist())

    mappings: dict[str, dict[str, int]] = {}
    for column in CATEGORICAL_COLUMNS:
        categories = sorted(values[column])
        mappings[column] = {value: index for index, value in enumerate(categories)}
    return mappings


def _collect_train_minmax(
    train_path: Path,
    mappings: dict[str, dict[str, int]],
    chunk_size: int,
) -> dict[str, tuple[float, float]]:
    mins = {column: float("inf") for column in NUMERIC_COLUMNS}
    maxs = {column: float("-inf") for column in NUMERIC_COLUMNS}

    for chunk in _chunks(train_path, chunk_size):
        chunk = _encode_and_features(chunk, mappings)
        for column in NUMERIC_COLUMNS:
            values = pd.to_numeric(chunk[column], errors="raise").astype("float64")
            local_min = float(values.min())
            local_max = float(values.max())
            if local_min < mins[column]:
                mins[column] = local_min
            if local_max > maxs[column]:
                maxs[column] = local_max

    return {column: (mins[column], maxs[column]) for column in NUMERIC_COLUMNS}


def _encode_and_features(
    df: pd.DataFrame,
    mappings: dict[str, dict[str, int]],
) -> pd.DataFrame:
    for column in CATEGORICAL_COLUMNS:
        mapping = mappings[column]
        values = df[column].astype(str)
        # Exactly like old encoder.py: unknown test categories become -1.
        df[column] = values.map(mapping).fillna(-1).astype("int64")

    return _prepare_features(df)


def _normalize_chunk(
    df: pd.DataFrame,
    minmax: dict[str, tuple[float, float]],
) -> pd.DataFrame:
    for column in NUMERIC_COLUMNS:
        values = pd.to_numeric(df[column], errors="raise").astype("float64")
        minimum, maximum = minmax[column]
        if maximum == minimum:
            df[column] = 0.0
        else:
            df[column] = (values - minimum) / (maximum - minimum)
    return df[OUTPUT_COLUMNS]


def preprocess_files(
    train_path: str | Path,
    test_path: str | Path,
    output_dir: str | Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> tuple[Path, Path]:
    """Process train/test CSVs without loading either whole file into RAM."""
    train_path = Path(train_path)
    test_path = Path(test_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    train_out = output_dir / "train_processed.csv"
    test_out = output_dir / "test_processed.csv"
    mappings_path = output_dir / "category_mappings.json"
    scaler_path = output_dir / "feature_scaler.json"

    print("===== RAM-SAFE PIPELINE =====")
    print(f"Chunk size: {chunk_size:,}")
    print("\n===== VALIDATING INPUTS =====")
    _check_header(train_path)
    _check_header(test_path)
    print("[OK] TRAIN 13-column schema")
    print("[OK] TEST 13-column schema")

    print("\n===== LEARNING TRAIN CATEGORICAL MAPPINGS =====")
    mappings = _collect_mappings(train_path, chunk_size)
    with mappings_path.open("w", encoding="utf-8") as f:
        json.dump(mappings, f, indent=2, ensure_ascii=False)
    print(f"[OK] mappings saved: {mappings_path}")

    print("\n===== LEARNING TRAIN MIN/MAX =====")
    minmax = _collect_train_minmax(train_path, mappings, chunk_size)
    with scaler_path.open("w", encoding="utf-8") as f:
        json.dump(
            {column: {"min": mn, "max": mx} for column, (mn, mx) in minmax.items()},
            f,
            indent=2,
        )
    print(f"[OK] scaler statistics saved: {scaler_path}")

    for output in (train_out, test_out):
        if output.exists():
            output.unlink()

    print("\n===== WRITING TRAIN PROCESSED =====")
    _write_processed(train_path, train_out, mappings, minmax, chunk_size, "TRAIN")

    print("\n===== WRITING TEST PROCESSED =====")
    _write_processed(test_path, test_out, mappings, minmax, chunk_size, "TEST")

    print("\n===== PIPELINE FINISHED =====")
    print(f"TRAIN: {train_out}")
    print(f"TEST : {test_out}")
    return train_out, test_out


def _write_processed(
    source: Path,
    destination: Path,
    mappings: dict[str, dict[str, int]],
    minmax: dict[str, tuple[float, float]],
    chunk_size: int,
    label: str,
) -> None:
    rows = 0
    first = True

    for chunk in _chunks(source, chunk_size):
        chunk = _encode_and_features(chunk, mappings)
        chunk = _normalize_chunk(chunk, minmax)
        chunk.to_csv(
            destination,
            mode="w" if first else "a",
            header=first,
            index=False,
            lineterminator="\n",
        )
        first = False
        rows += len(chunk)
        print(f"  [{label}] processed={rows:,}", flush=True)

    if first:
        raise RuntimeError(f"{source}: no rows found")


def preprocess_data(*args, **kwargs):
    """Compatibility entry point for callers that use this module directly.

    Unlike the original preprocessor.py, this returns output paths rather than
    two giant in-memory DataFrames. Use preprocess_files() explicitly when
    integrating into scripts.
    """
    return preprocess_files(*args, **kwargs)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RAM-safe RL_Agent preprocessing")
    parser.add_argument("train")
    parser.add_argument("test")
    parser.add_argument("output_dir")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    args = parser.parse_args()

    preprocess_files(
        args.train,
        args.test,
        args.output_dir,
        chunk_size=args.chunk_size,
    )
