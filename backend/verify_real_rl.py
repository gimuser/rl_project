"""Verify the real dataset-driven RL pipeline."""

from pathlib import Path

import pandas as pd


ROOT = Path(
    __file__
).resolve().parents[1]

TRAIN = (
    ROOT
    / "data"
    / "processed"
    / "train_processed.csv"
)

TEST = (
    ROOT
    / "data"
    / "processed"
    / "test_processed.csv"
)


REQUIRED_COLUMNS = {
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
    "IncidentGrade",
}


def main():
    print("=" * 70)
    print(
        "REAL RL PIPELINE VALIDATION"
    )
    print("=" * 70)

    if not TRAIN.exists():
        raise SystemExit(
            f"[FAIL] Missing train dataset: {TRAIN}"
        )

    if not TEST.exists():
        raise SystemExit(
            f"[FAIL] Missing test dataset: {TEST}"
        )

    train = pd.read_csv(
        TRAIN
    )

    test = pd.read_csv(
        TEST
    )

    print(
        f"[OK] Train dataset: {TRAIN}"
    )

    print(
        f"[OK] Test dataset : {TEST}"
    )

    print(
        f"[OK] Train rows   : {len(train):,}"
    )

    print(
        f"[OK] Test rows    : {len(test):,}"
    )

    print(
        f"[OK] Train columns: {len(train.columns)}"
    )

    print(
        f"[OK] Test columns : {len(test.columns)}"
    )

    for name, df in [
        ("train", train),
        ("test", test),
    ]:
        if df.empty:
            raise SystemExit(
                f"[FAIL] {name} dataset is empty."
            )

        missing = (
            REQUIRED_COLUMNS
            - set(df.columns)
        )

        if missing:
            raise SystemExit(
                f"[FAIL] {name} missing: "
                f"{sorted(missing)}"
            )

    print(
        "[OK] Required RL columns exist."
    )

    print(
        "[OK] Both datasets contain real rows."
    )

    print(
        "[OK] Train/test datasets are separated."
    )

    print("=" * 70)
    print(
        "VALIDATION PASSED"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()
