"""Leakage-safe normalization."""

from pathlib import Path
import joblib
from sklearn.preprocessing import MinMaxScaler


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = PROJECT_ROOT / "models"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

SCALER_PATH = ARTIFACT_DIR / "feature_scaler.joblib"

NUMERIC_COLUMNS = [
    "IncidentId",
    "hour",
    "day",
    "month",
    "is_weekend",
]


def normalize_data(train_df, test_df):
    train_df = train_df.copy()
    test_df = test_df.copy()

    columns = [
        c for c in NUMERIC_COLUMNS
        if c in train_df.columns and c in test_df.columns
    ]

    scaler = MinMaxScaler()

    train_df[columns] = scaler.fit_transform(
        train_df[columns]
    )

    test_df[columns] = scaler.transform(
        test_df[columns]
    )

    joblib.dump(
        {
            "scaler": scaler,
            "columns": columns,
        },
        SCALER_PATH,
    )

    return train_df, test_df


def load_scaler():
    if not SCALER_PATH.exists():
        raise FileNotFoundError(
            f"Scaler not found: {SCALER_PATH}"
        )

    return joblib.load(SCALER_PATH)
