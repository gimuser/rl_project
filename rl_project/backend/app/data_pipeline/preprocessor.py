"""Complete data preprocessing pipeline."""


from loader import load_train_data, load_test_data
from cleaner import clean_data
from validator import validate_data
from encoder import encode_data
from feature_engineering import create_features
from normalizer import normalize_data



def preprocess_data():

    print("===== LOADING DATA =====")

    train = load_train_data()
    test = load_test_data()


    print("\n===== CLEANING DATA =====")

    train = clean_data(train)
    test = clean_data(test)



    print("\n===== VALIDATION =====")

    validate_data(train, "TRAIN")
    validate_data(test, "TEST")



    print("\n===== ENCODING =====")

    train, test = encode_data(
        train,
        test
    )



    print("\n===== FEATURE ENGINEERING =====")

    train, test = create_features(
        train,
        test
    )



    print("\n===== NORMALIZATION =====")

    train, test = normalize_data(
        train,
        test
    )


    print("\n===== PIPELINE FINISHED =====")


    return train, test





if __name__ == "__main__":


    train, test = preprocess_data()


    print("\n===== FINAL TRAIN =====")

    print(train.head())


    print("\n===== FINAL TEST =====")

    print(test.head())


    print("\nTrain shape :", train.shape)

    print("Test shape :", test.shape)