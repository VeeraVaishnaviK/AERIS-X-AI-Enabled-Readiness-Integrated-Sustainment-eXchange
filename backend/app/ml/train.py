"""
AERIS-X ML Training Pipeline
Pre-trains all models during `make seed` and saves to /models:
- IsolationForest (anomaly detection per sensor group)
- XGBoost Classifier (failure probability next 72h)
- Logistic Regression baseline (failure probability)
- XGBoost Regressor (Remaining Useful Life)
- StandardScaler (feature normalisation)

All models are deterministic (random_state=42).
"""
import time
import asyncio
import numpy as np
import pandas as pd
from typing import Any, Dict, Tuple

from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    classification_report,
    recall_score,
    precision_score,
    f1_score,
    mean_squared_error,
    mean_absolute_error,
)
import xgboost as xgb
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.db.models import Telemetry
from app.ml.features import build_training_dataset, get_feature_names, SENSOR_NAMES
from app.ml.registry import save_model, MODELS_DIR

logger = get_logger("aeris.ml.train")

SEED = 42


async def _load_telemetry_df() -> pd.DataFrame:
    """Load all telemetry from database into a pandas DataFrame."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Telemetry).order_by(Telemetry.aircraft_id, Telemetry.timestamp)
        )
        rows = result.scalars().all()

    records = []
    for r in rows:
        record = {
            "aircraft_id": r.aircraft_id,
            "timestamp": r.timestamp,
            "is_anomaly": r.is_anomaly,
        }
        for sensor in SENSOR_NAMES:
            record[sensor] = getattr(r, sensor, 0.0)
        records.append(record)

    df = pd.DataFrame(records)
    logger.info(f"Loaded {len(df)} telemetry rows for training.")
    return df


def _train_anomaly_detector(X: np.ndarray) -> IsolationForest:
    """Train IsolationForest on scaled feature matrix."""
    model = IsolationForest(
        n_estimators=200,
        contamination=0.05,
        max_samples="auto",
        random_state=SEED,
        n_jobs=-1,
    )
    model.fit(X)
    logger.info(f"IsolationForest trained on {X.shape[0]} samples, {X.shape[1]} features.")
    return model


def _train_failure_classifier(
    X_train: np.ndarray, y_train: np.ndarray,
    X_test: np.ndarray, y_test: np.ndarray,
) -> Tuple[xgb.XGBClassifier, LogisticRegression, Dict[str, Any]]:
    """Train XGBoost and Logistic Regression classifiers for 72h failure prediction."""
    # Calculate class weight for imbalanced data
    n_pos = int(np.sum(y_train == 1))
    n_neg = int(np.sum(y_train == 0))
    scale_pos = max(n_neg / max(n_pos, 1), 1.0)

    # XGBoost Classifier
    xgb_clf = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        scale_pos_weight=scale_pos,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=SEED,
        eval_metric="logloss",
        use_label_encoder=False,
    )
    xgb_clf.fit(X_train, y_train, verbose=False)

    # Logistic Regression baseline
    lr_clf = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        random_state=SEED,
        solver="lbfgs",
    )
    lr_clf.fit(X_train, y_train)

    # Evaluate both
    xgb_preds = xgb_clf.predict(X_test)
    lr_preds = lr_clf.predict(X_test)

    metrics = {
        "xgb_recall": float(recall_score(y_test, xgb_preds, zero_division=0)),
        "xgb_precision": float(precision_score(y_test, xgb_preds, zero_division=0)),
        "xgb_f1": float(f1_score(y_test, xgb_preds, zero_division=0)),
        "lr_recall": float(recall_score(y_test, lr_preds, zero_division=0)),
        "lr_precision": float(precision_score(y_test, lr_preds, zero_division=0)),
        "lr_f1": float(f1_score(y_test, lr_preds, zero_division=0)),
        "test_samples": len(y_test),
        "positive_ratio_train": float(n_pos / max(n_pos + n_neg, 1)),
    }

    logger.info(f"XGBoost — Recall: {metrics['xgb_recall']:.3f}, F1: {metrics['xgb_f1']:.3f}")
    logger.info(f"LogReg  — Recall: {metrics['lr_recall']:.3f}, F1: {metrics['lr_f1']:.3f}")

    return xgb_clf, lr_clf, metrics


def _train_rul_regressor(
    X_train: np.ndarray, y_train: np.ndarray,
    X_test: np.ndarray, y_test: np.ndarray,
) -> Tuple[xgb.XGBRegressor, Dict[str, Any]]:
    """Train XGBoost regressor for Remaining Useful Life estimation."""
    rul_model = xgb.XGBRegressor(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=SEED,
    )
    rul_model.fit(X_train, y_train, verbose=False)

    preds = rul_model.predict(X_test)
    preds_clipped = np.clip(preds, 0, None)

    rmse = float(np.sqrt(mean_squared_error(y_test, preds_clipped)))
    mae = float(mean_absolute_error(y_test, preds_clipped))

    metrics = {
        "rul_rmse": rmse,
        "rul_mae": mae,
        "test_samples": len(y_test),
    }
    logger.info(f"RUL Regressor — RMSE: {rmse:.2f}h, MAE: {mae:.2f}h")

    return rul_model, metrics


async def train_all_models() -> Dict[str, Any]:
    """
    Master training pipeline. Called during `make seed`.
    Returns a metrics dict for gate validation.
    """
    start = time.time()
    logger.info("=" * 60)
    logger.info("AERIS-X ML Training Pipeline — Starting")
    logger.info("=" * 60)

    # 1. Load telemetry data
    tel_df = await _load_telemetry_df()

    # 2. Build feature dataset
    logger.info("Building rolling-window feature dataset...")
    feature_df, failure_labels, rul_labels = build_training_dataset(tel_df, window_size=24)
    feature_names = get_feature_names()
    X_raw = feature_df[feature_names].values.astype(np.float64)

    # Replace any NaN/Inf with 0
    X_raw = np.nan_to_num(X_raw, nan=0.0, posinf=0.0, neginf=0.0)

    logger.info(f"Feature matrix shape: {X_raw.shape}")

    # 3. Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_raw)
    save_model("feature_scaler", scaler)

    # 4. Train anomaly detector
    logger.info("Training IsolationForest anomaly detector...")
    anomaly_model = _train_anomaly_detector(X_scaled)
    save_model("anomaly_detector", anomaly_model)

    # 5. Train failure classifiers (XGBoost + LR baseline)
    y_failure = failure_labels.values if failure_labels is not None else np.zeros(len(X_scaled))
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y_failure, test_size=0.2, random_state=SEED, stratify=y_failure
    )

    logger.info("Training failure classifiers (XGBoost + LogReg)...")
    xgb_clf, lr_clf, failure_metrics = _train_failure_classifier(X_train, y_train, X_test, y_test)
    save_model("failure_xgb", xgb_clf)
    save_model("failure_lr", lr_clf)

    # 6. Train RUL regressor
    y_rul = rul_labels.values if rul_labels is not None else np.full(len(X_scaled), 500.0)
    X_train_r, X_test_r, y_train_r, y_test_r = train_test_split(
        X_scaled, y_rul, test_size=0.2, random_state=SEED
    )

    logger.info("Training RUL regressor (XGBoost)...")
    rul_model, rul_metrics = _train_rul_regressor(X_train_r, y_train_r, X_test_r, y_test_r)
    save_model("rul_xgb", rul_model)

    elapsed = time.time() - start

    # 7. Write metrics report
    all_metrics = {
        "training_time_s": round(elapsed, 1),
        "feature_count": len(feature_names),
        "training_samples": X_raw.shape[0],
        "failure_classification": failure_metrics,
        "rul_regression": rul_metrics,
        "models_saved": list(MODELS_DIR.glob("*.joblib")),
    }

    metrics_path = MODELS_DIR / "metrics.txt"
    with open(metrics_path, "w") as f:
        f.write("AERIS-X ML Training Metrics\n")
        f.write("=" * 50 + "\n")
        f.write(f"Training samples:   {X_raw.shape[0]}\n")
        f.write(f"Feature dimensions: {X_raw.shape[1]}\n")
        f.write(f"Training time:      {elapsed:.1f}s\n\n")
        f.write("Failure Classification (72h lookahead)\n")
        f.write("-" * 40 + "\n")
        for k, v in failure_metrics.items():
            f.write(f"  {k}: {v}\n")
        f.write(f"\nRUL Regression\n")
        f.write("-" * 40 + "\n")
        for k, v in rul_metrics.items():
            f.write(f"  {k}: {v}\n")

    logger.info("=" * 60)
    logger.info(f"ML Training Complete — {elapsed:.1f}s")
    logger.info(f"Models saved to: {MODELS_DIR}")
    logger.info("=" * 60)

    print(f"\n{'='*60}")
    print(f"AERIS-X ML Training Pipeline — Complete")
    print(f"{'='*60}")
    print(f"  Training samples: {X_raw.shape[0]}")
    print(f"  Features:         {X_raw.shape[1]}")
    print(f"  XGB Recall:       {failure_metrics['xgb_recall']:.3f}")
    print(f"  LR  Recall:       {failure_metrics['lr_recall']:.3f}")
    print(f"  RUL RMSE:         {rul_metrics['rul_rmse']:.2f}h")
    print(f"  Elapsed:          {elapsed:.1f}s")
    print(f"{'='*60}")

    return all_metrics


if __name__ == "__main__":
    asyncio.run(train_all_models())
