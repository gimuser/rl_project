"""Load the real processed SOAR datasets."""

from pathlib import Path
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

TRAIN_PATH = PROCESSED_DIR / "train_processed.csv"
TEST_PATH = PROCESSED_DIR / "test_processed.csv"


def load_train_data() -> pd.DataFrame:
    if not TRAIN_PATH.exists():
        raise FileNotFoundError(
            f"Real training dataset not found: {TRAIN_PATH}"
        )
    return pd.read_csv(TRAIN_PATH)


def load_test_data() -> pd.DataFrame:
    if not TEST_PATH.exists():
        raise FileNotFoundError(
            f"Real test dataset not found: {TEST_PATH}"
        )
    return pd.read_csv(TEST_PATH)


def dataset_info() -> dict:
    train = load_train_data()
    test = load_test_data()

    return {
        "train_path": str(TRAIN_PATH),
        "test_path": str(TEST_PATH),
        "train_rows": len(train),
        "test_rows": len(test),
        "train_columns": len(train.columns),
        "test_columns": len(test.columns),
        "train_missing_values": int(train.isna().sum().sum()),
        "test_missing_values": int(test.isna().sum().sum()),
    }
