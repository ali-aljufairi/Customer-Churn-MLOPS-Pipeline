from pathlib import Path

import pandas as pd

from app.model import EXPECTED_COLUMNS, TARGET, build_pipeline, load_dataset, train

ROOT = Path(__file__).resolve().parents[1]


def test_dataset_preprocessing_excludes_identifier_and_parses_target():
    X, y = load_dataset(ROOT / "churn.csv")
    assert list(X.columns) == EXPECTED_COLUMNS
    assert "Phone" not in X
    assert len(X) == 3333
    assert int(y.sum()) == 483
    assert set(y.unique()) == {0, 1}


def test_unknown_categories_are_accepted_by_preprocessor():
    X = pd.DataFrame([{
        "State": "ZZ", "Account Length": 10, "Area Code": 415, "Int'l Plan": "no",
        "VMail Plan": "no", "VMail Message": 0, "Day Mins": 1, "Day Calls": 1,
        "Day Charge": 1, "Eve Mins": 1, "Eve Calls": 1, "Eve Charge": 1,
        "Night Mins": 1, "Night Calls": 1, "Night Charge": 1, "Intl Mins": 1,
        "Intl Calls": 1, "Intl Charge": 1, "CustServ Calls": 0,
    }])
    # Fit on a dataset sample; unknown state must not break one-hot transformation.
    X_train, y = load_dataset(ROOT / "churn.csv")
    model = build_pipeline().fit(X_train, y)
    assert model.predict_proba(X)[0, 1] >= 0


def test_training_persists_pipeline_and_metadata(tmp_path):
    metadata = train(ROOT / "churn.csv", tmp_path)
    assert (tmp_path / "model.joblib").exists()
    assert (tmp_path / "metadata.json").exists()
    assert metadata["test_rows"] == 667
    assert metadata["target"] == TARGET
    assert set(metadata["metrics"]) == {"accuracy", "precision", "recall", "f1", "roc_auc"}
    assert all(0 <= score <= 1 for score in metadata["metrics"].values())
