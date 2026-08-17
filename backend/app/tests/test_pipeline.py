"""Tests for the processed dataset contract and feature schema."""

from app.data_pipeline.contract import FEATURE_COLUMNS, REQUIRED_PROCESSED_COLUMNS, audit_processed_split, load_processed_split


def test_train_and_test_splits_have_expected_schema():
    train = load_processed_split("train")
    test = load_processed_split("test")

    required = set(REQUIRED_PROCESSED_COLUMNS)

    # The processed contract guarantees that the required 17 columns exist.
    # Additional underscore-prefixed columns are allowed as internal
    # preprocessing/lineage fields.
    for split_name, frame in (("train", train), ("test", test)):
        missing = required - set(frame.columns)
        assert not missing, (
            f"{split_name} split is missing required columns: {sorted(missing)}"
        )

        extras = set(frame.columns) - required
        assert all(
            str(column).startswith("_") for column in extras
        ), (
            f"{split_name} split contains unsupported extra columns: "
            f"{sorted(extras)}"
        )

    assert list(FEATURE_COLUMNS) == [
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
    ]

    assert audit_processed_split("train").rows > 0
    assert audit_processed_split("test").rows > 0
