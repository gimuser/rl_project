from .real_pipeline import TEST_PATH, MODEL_PATH
from .evaluator import evaluate

if __name__ == "__main__":
    evaluate(
        model_path=MODEL_PATH,
        test_path=TEST_PATH,
    )
