"""Leakage-safe categorical encoding."""

from pathlib import Path
import json


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = PROJECT_ROOT / "models"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

MAPPINGS_PATH = ARTIFACT_DIR / "category_mappings.json"

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


def encode_data(train_df, test_df):
    train_df = train_df.copy()
    test_df = test_df.copy()

    mappings = {}

    for column in CATEGORICAL_COLUMNS:
        if column not in train_df.columns:
            continue

        train_values = train_df[column].astype(str)
        test_values = test_df[column].astype(str)

        categories = sorted(
            train_values.unique().tolist()
        )

        mapping = {
            value: index
            for index, value in enumerate(categories)
        }

        train_df[column] = (
            train_values
            .map(mapping)
            .fillna(-1)
            .astype(int)
        )

        test_df[column] = (
            test_values
            .map(mapping)
            .fillna(-1)
            .astype(int)
        )

        mappings[column] = mapping

    with MAPPINGS_PATH.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            mappings,
            f,
            indent=2,
        )

    return train_df, test_df


def load_mappings():
    if not MAPPINGS_PATH.exists():
        raise FileNotFoundError(
            f"Category mappings not found: {MAPPINGS_PATH}"
        )

    with MAPPINGS_PATH.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)
