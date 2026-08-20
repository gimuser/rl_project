"""Feature engineering helpers."""

import pandas as pd


def create_features(train_df, test_df):

    datasets = [train_df, test_df]

    for df in datasets:

        # تحويل Timestamp إلى datetime

        df["Timestamp"] = pd.to_datetime(df["Timestamp"])

        # استخراج الساعة

        df["hour"] = df["Timestamp"].dt.hour

        # استخراج النهار

        df["day"] = df["Timestamp"].dt.day

        # استخراج الشهر

        df["month"] = df["Timestamp"].dt.month

        # واش Weekend

        df["is_weekend"] = (
            df["Timestamp"].dt.dayofweek >= 5
        ).astype(int)

    return train_df, test_df


if __name__ == "__main__":

    from loader import load_train_data, load_test_data
    from cleaner import clean_data
    from validator import validate_data
    from encoder import encode_data

    train = load_train_data()
    test = load_test_data()

    train = clean_data(train)
    test = clean_data(test)

    validate_data(train, "TRAIN")
    validate_data(test, "TEST")

    train, test = encode_data(train, test)

    train, test = create_features(train, test)

    print("\n=== TRAIN ===")
    print(train[["hour", "day", "month", "is_weekend"]].head())

    print("\n=== TEST ===")
    print(test[["hour", "day", "month", "is_weekend"]].head())