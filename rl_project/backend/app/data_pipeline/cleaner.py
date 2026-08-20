"""Data cleaning."""

import pandas as pd


def clean_data(df):

    print("Shape avant :", df.shape)

    # حذف الأسطر المكررة
    df = df.drop_duplicates()

    # تعويض القيم الخاوية
    df = df.fillna("Unknown")

    print("Shape apres :", df.shape)

    return df


if __name__ == "__main__":

    from loader import load_train_data, load_test_data

    train = load_train_data()
    test = load_test_data()

    print("=== TRAIN ===")
    train = clean_data(train)

    print("\n=== TEST ===")
    test = clean_data(test)
