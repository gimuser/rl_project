"""Export helpers for processed datasets."""
"""Export processed datasets."""

import os

from preprocessor import preprocess_data



def export_data():

    train, test = preprocess_data()


    output_path = "data/processed"


    os.makedirs(
        output_path,
        exist_ok=True
    )


    train.to_csv(
        f"{output_path}/train_processed.csv",
        index=False
    )


    test.to_csv(
        f"{output_path}/test_processed.csv",
        index=False
    )


    print("\n[OK] Data exported successfully")

    print(
        "Train saved:",
        f"{output_path}/train_processed.csv"
    )

    print(
        "Test saved:",
        f"{output_path}/test_processed.csv"
    )



if __name__ == "__main__":

    export_data()
