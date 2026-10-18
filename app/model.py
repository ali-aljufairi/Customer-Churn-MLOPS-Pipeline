from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

TARGET = "Churn?"
DROP_COLUMNS = {"Phone", TARGET}
EXPECTED_COLUMNS = [
    "State", "Account Length", "Area Code", "Int'l Plan", "VMail Plan", "VMail Message",
    "Day Mins", "Day Calls", "Day Charge", "Eve Mins", "Eve Calls", "Eve Charge",
    "Night Mins", "Night Calls", "Night Charge", "Intl Mins", "Intl Calls", "Intl Charge",
    "CustServ Calls",
]
CATEGORICAL = ["State", "Int'l Plan", "VMail Plan"]
NUMERIC = [name for name in EXPECTED_COLUMNS if name not in CATEGORICAL]


def load_dataset(path: str | Path) -> tuple[pd.DataFrame, pd.Series]:
    frame = pd.read_csv(path)
    missing = set(EXPECTED_COLUMNS + [TARGET]) - set(frame.columns)
    if missing:
        raise ValueError(f"Dataset missing required columns: {sorted(missing)}")
    X = frame[EXPECTED_COLUMNS].copy()
    for col in CATEGORICAL:
        X[col] = X[col].astype("string").str.strip().str.lower()
    for col in NUMERIC:
        X[col] = pd.to_numeric(X[col], errors="raise")
    labels = frame[TARGET].astype("string").str.strip().str.lower().str.rstrip(".")
    mapping = {"true": 1, "false": 0, "yes": 1, "no": 0, "1": 1, "0": 0}
    y = labels.map(mapping)
    if y.isna().any():
        raise ValueError("Target must contain only boolean-like values")
    return X, y.astype("int8")


def build_pipeline() -> Pipeline:
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())])
    categorical = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=True)),
    ])
    prep = ColumnTransformer([
        ("numeric", numeric, NUMERIC), ("categorical", categorical, CATEGORICAL),
    ])
    return Pipeline([
        ("preprocess", prep),
        ("classifier", LogisticRegression(class_weight="balanced", max_iter=2000, random_state=42)),
    ])


def train(data_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    X, y = load_dataset(data_path)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y,
    )
    estimator = build_pipeline()
    estimator.fit(X_train, y_train)
    prob = estimator.predict_proba(X_test)[:, 1]
    pred = (prob >= 0.5).astype(int)
    metrics = {
        "accuracy": round(float(accuracy_score(y_test, pred)), 6),
        "precision": round(float(precision_score(y_test, pred, zero_division=0)), 6),
        "recall": round(float(recall_score(y_test, pred, zero_division=0)), 6),
        "f1": round(float(f1_score(y_test, pred, zero_division=0)), 6),
        "roc_auc": round(float(roc_auc_score(y_test, prob)), 6),
    }
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    artifact = output / "model.joblib"
    joblib.dump(estimator, artifact, compress=3)
    metadata = {
        "model_name": "balanced-logistic-regression", "model_version": "1.0.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_rows": int(len(X)), "positive_count": int(y.sum()),
        "train_rows": int(len(X_train)), "test_rows": int(len(X_test)),
        "random_state": 42, "test_size": 0.2, "threshold": 0.5,
        "features": EXPECTED_COLUMNS, "target": TARGET, "dropped_columns": sorted(DROP_COLUMNS),
        "metrics": metrics, "sklearn_version": sklearn.__version__,
        "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
    }
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the customer churn classifier")
    parser.add_argument("--data", default="churn.csv", help="Path to training CSV")
    parser.add_argument("--output", default="artifacts", help="Output artifact directory")
    args = parser.parse_args()
    print(json.dumps(train(args.data, args.output), indent=2))


if __name__ == "__main__":
    main()
