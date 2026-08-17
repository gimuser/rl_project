"""Data validation helpers."""

REQUIRED_COLUMNS = [
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
    "LastVerdict"
]


def validate_data(df, dataset_name):

    print(f"\n=== {dataset_name} ===")

    missing_columns = []

    for col in REQUIRED_COLUMNS:

        if col not in df.columns:
            missing_columns.append(col)

    if len(missing_columns) == 0:

        print("[OK] Validation OK")
        print("Nombre de colonnes :", len(df.columns))

    else:

        print("Colonnes manquantes :")
        print(missing_columns)

    return len(missing_columns) == 0


if __name__ == "__main__":

    from loader import load_train_data, load_test_data
    from cleaner import clean_data

    train = clean_data(load_train_data())
    test = clean_data(load_test_data())

    validate_data(train, "TRAIN")
    validate_data(test, "TEST")