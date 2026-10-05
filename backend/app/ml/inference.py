"""
AERIS-X ML Inference Services
Runtime prediction for anomaly detection, failure probability, RUL, and SHAP explanations.
Models are loaded from pre-trained joblib files (created during `make seed`).
"""
import numpy as np
import shap
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging import get_logger
from app.ml.features import build_feature_row, get_feature_names, SENSOR_NAMES
from app.ml.registry import load_model
from app.synthetic.scenarios import SENSOR_BASELINES

logger = get_logger("aeris.ml.inference")


# Human-readable sensor descriptions for SHAP explanations
SENSOR_DESCRIPTIONS = {
    "vibration": "Vibration level (mm/s RMS)",
    "egt": "Exhaust Gas Temperature (°C)",
    "oil_pressure": "Oil Pressure (psi)",
    "oil_temperature": "Oil Temperature (°C)",
    "fuel_flow": "Fuel Flow Rate (kg/h)",
    "hydraulic_pressure": "Hydraulic Pressure (psi)",
    "battery_voltage": "Battery Voltage (V)",
    "n1_rpm": "N1 Turbine RPM (%)",
    "n2_rpm": "N2 Turbine RPM (%)",
}

FEATURE_SUFFIX_LABELS = {
    "latest": "current reading",
    "mean": "24h average",
    "std": "24h variability",
    "min": "24h minimum",
    "max": "24h maximum",
    "rate": "rate of change",
}


def _get_feature_vector(telemetry_window: List[Dict[str, float]]) -> np.ndarray:
    """Build and scale a feature vector from a telemetry window."""
    scaler = load_model("feature_scaler")
    if scaler is None:
        raise RuntimeError("Feature scaler not found. Run training pipeline first.")

    feat = build_feature_row(telemetry_window)
    feature_names = get_feature_names()
    X = np.array([[feat.get(f, 0.0) for f in feature_names]], dtype=np.float64)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    X_scaled = scaler.transform(X)
    return X_scaled


def detect_anomaly(telemetry_window: List[Dict[str, float]]) -> Dict[str, Any]:
    """Run IsolationForest anomaly detection on a telemetry window."""
    model = load_model("anomaly_detector")
    if model is None:
        return {"is_anomaly": False, "anomaly_score": 0.0, "error": "Model not loaded"}

    X = _get_feature_vector(telemetry_window)
    score = float(model.decision_function(X)[0])
    prediction = int(model.predict(X)[0])
    is_anomaly = prediction == -1

    # Normalise score to 0-1 range (more negative = more anomalous)
    anomaly_score = max(0.0, min(1.0, 0.5 - score))

    return {
        "is_anomaly": is_anomaly,
        "anomaly_score": round(anomaly_score, 4),
        "raw_decision_score": round(score, 4),
    }


def predict_failure(telemetry_window: List[Dict[str, float]]) -> Dict[str, Any]:
    """
    Predict failure probability in next 72h using both XGBoost and LR baseline.
    Returns both probabilities and the risk classification.
    """
    xgb_model = load_model("failure_xgb")
    lr_model = load_model("failure_lr")

    if xgb_model is None or lr_model is None:
        return {
            "failure_probability_72h": 0.0,
            "baseline_probability": 0.0,
            "risk_level": "LOW",
            "error": "Models not loaded",
        }

    X = _get_feature_vector(telemetry_window)

    xgb_prob = float(xgb_model.predict_proba(X)[0, 1])
    lr_prob = float(lr_model.predict_proba(X)[0, 1])

    # Risk classification from calibrated thresholds
    if xgb_prob >= 0.80:
        risk_level = "CRITICAL"
    elif xgb_prob >= 0.55:
        risk_level = "HIGH"
    elif xgb_prob >= 0.30:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return {
        "failure_probability_72h": round(xgb_prob, 4),
        "baseline_probability": round(lr_prob, 4),
        "risk_level": risk_level,
    }


def predict_rul(telemetry_window: List[Dict[str, float]]) -> Dict[str, Any]:
    """
    Predict Remaining Useful Life (hours) with confidence interval.
    """
    model = load_model("rul_xgb")
    if model is None:
        return {"rul_hours": 500.0, "rul_lower": 450.0, "rul_upper": 550.0, "error": "Model not loaded"}

    X = _get_feature_vector(telemetry_window)
    rul_pred = float(model.predict(X)[0])
    rul_pred = max(0.0, rul_pred)

    # Approximate confidence interval (±15% or minimum 10h)
    margin = max(rul_pred * 0.15, 10.0)

    return {
        "rul_hours": round(rul_pred, 1),
        "rul_lower_bound": round(max(0, rul_pred - margin), 1),
        "rul_upper_bound": round(rul_pred + margin, 1),
    }


def _feature_to_description(feature_name: str) -> str:
    """Convert a feature column name to a plain-English description."""
    parts = feature_name.rsplit("_", 1)
    if len(parts) == 2:
        sensor_base = parts[0]
        suffix = parts[1]
    else:
        return feature_name

    # Handle multi-word sensor names like oil_pressure_latest
    for sensor in SENSOR_NAMES:
        if feature_name.startswith(sensor + "_"):
            sensor_base = sensor
            suffix = feature_name[len(sensor) + 1:]
            break

    sensor_label = SENSOR_DESCRIPTIONS.get(sensor_base, sensor_base)
    suffix_label = FEATURE_SUFFIX_LABELS.get(suffix, suffix)
    return f"{sensor_label} ({suffix_label})"


def explain_prediction(
    telemetry_window: List[Dict[str, float]],
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Generate top-k SHAP explanations for the failure prediction.
    Returns evidence items with feature, contribution, direction, SHAP value, and description.
    """
    xgb_model = load_model("failure_xgb")
    if xgb_model is None:
        return []

    X = _get_feature_vector(telemetry_window)
    feature_names = get_feature_names()

    try:
        explainer = shap.TreeExplainer(xgb_model)
        shap_values = explainer.shap_values(X)

        if isinstance(shap_values, list):
            shap_vals = shap_values[1] if len(shap_values) > 1 else shap_values[0]
        else:
            shap_vals = shap_values

        shap_row = shap_vals[0] if shap_vals.ndim > 1 else shap_vals

    except Exception as e:
        logger.warning(f"SHAP explanation failed: {e}. Falling back to feature importance.")
        # Fallback: use feature importances
        importances = xgb_model.feature_importances_
        top_indices = np.argsort(np.abs(importances))[-top_k:][::-1]
        evidence = []
        for rank, idx in enumerate(top_indices, 1):
            feat_name = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"
            val = float(X[0, idx]) if idx < X.shape[1] else 0.0
            evidence.append({
                "feature": feat_name,
                "contribution": round(float(importances[idx]) * 100, 1),
                "direction": "INCREASING_RISK",
                "shap_value": round(float(importances[idx]), 4),
                "description": f"{_feature_to_description(feat_name)} importance: {importances[idx]:.3f}",
                "importance_rank": rank,
            })
        return evidence

    # Sort by absolute SHAP value, take top-k
    abs_shap = np.abs(shap_row)
    top_indices = np.argsort(abs_shap)[-top_k:][::-1]

    total_abs = float(np.sum(abs_shap)) or 1.0
    evidence = []

    for rank, idx in enumerate(top_indices, 1):
        feat_name = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"
        sv = float(shap_row[idx])
        contribution_pct = round(abs(sv) / total_abs * 100, 1)
        direction = "INCREASING_RISK" if sv > 0 else "DECREASING_RISK"

        # Build plain-English description
        feat_val = float(X[0, idx])
        desc = _feature_to_description(feat_name)
        if sv > 0:
            desc = f"{desc} is elevated ({feat_val:+.2f}σ), contributing {contribution_pct}% to risk"
        else:
            desc = f"{desc} is nominal ({feat_val:+.2f}σ), reducing risk by {contribution_pct}%"

        evidence.append({
            "feature": feat_name,
            "contribution": contribution_pct,
            "direction": direction,
            "shap_value": round(sv, 4),
            "description": desc,
            "importance_rank": rank,
        })

    return evidence


def full_inference(
    telemetry_window: List[Dict[str, float]],
    aircraft_id: str = "",
) -> Dict[str, Any]:
    """
    Run the complete ML inference pipeline on a telemetry window:
    anomaly → failure probability → RUL → SHAP explanation.
    """
    anomaly = detect_anomaly(telemetry_window)
    failure = predict_failure(telemetry_window)
    rul = predict_rul(telemetry_window)
    evidence = explain_prediction(telemetry_window, top_k=5)

    # Determine recommended action
    risk = failure.get("risk_level", "LOW")
    if risk == "CRITICAL":
        action = "GROUND_IMMEDIATELY"
    elif risk == "HIGH":
        action = "SCHEDULE_URGENT_MAINTENANCE"
    elif risk == "MEDIUM":
        action = "INCREASE_MONITORING"
    else:
        action = "MONITOR_NORMAL"

    return {
        "aircraft_id": aircraft_id,
        "anomaly": anomaly,
        "failure": failure,
        "rul": rul,
        "evidence": evidence,
        "recommended_action": action,
        "model_version": "v1.0.0-xgb",
    }
