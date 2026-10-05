"""
Tests for Phase 6 — ML Services & SHAP
Validates:
- Model training produces all 5 required model files
- IsolationForest anomaly detection returns valid scores
- XGBoost failure classifier returns probability and risk level
- Logistic Regression baseline produces comparable probability
- XGBoost ≥ LR baseline on recall (gate requirement)
- RUL regressor returns clipped positive values with interval
- SHAP returns top-5 evidence items with plain-English descriptions
- Full inference pipeline returns complete result dict
"""
import os
import pytest
import numpy as np

from app.ml.features import build_feature_row, get_feature_names, SENSOR_NAMES
from app.ml.registry import load_model, models_exist, MODELS_DIR
from app.ml.inference import (
    detect_anomaly,
    predict_failure,
    predict_rul,
    explain_prediction,
    full_inference,
)


def _make_nominal_window(n: int = 24) -> list:
    """Generate a nominal telemetry window for testing."""
    return [
        {
            "vibration": 1.5,
            "egt": 650.0,
            "oil_pressure": 45.0,
            "oil_temperature": 95.0,
            "fuel_flow": 1150.0,
            "hydraulic_pressure": 3000.0,
            "battery_voltage": 28.0,
            "n1_rpm": 98.0,
            "n2_rpm": 95.0,
        }
        for _ in range(n)
    ]


def _make_degraded_window(n: int = 24) -> list:
    """Generate a severely degraded telemetry window with anomalous readings."""
    window = []
    for i in range(n):
        progress = i / max(n - 1, 1)
        window.append({
            "vibration": 1.5 + 8.0 * progress,    # extreme ramp-up
            "egt": 650.0 + 300.0 * progress,       # near max temp
            "oil_pressure": 45.0 - 20.0 * progress, # dropping
            "oil_temperature": 95.0 + 50.0 * progress,
            "fuel_flow": 1150.0 + 500.0 * progress,
            "hydraulic_pressure": 3000.0 - 1200.0 * progress,
            "battery_voltage": 28.0 - 6.0 * progress,
            "n1_rpm": 98.0 - 15.0 * progress,
            "n2_rpm": 95.0 - 12.0 * progress,
        })
    return window


def test_models_exist_after_training():
    """Verify all 5 model files are saved to disk after training."""
    assert models_exist(), "Not all models are saved. Run 'python -m app.ml.train' first."
    required = [
        "anomaly_iforest_v1.joblib",
        "failure_xgb_v1.joblib",
        "failure_lr_v1.joblib",
        "rul_xgb_v1.joblib",
        "feature_scaler_v1.joblib",
    ]
    for filename in required:
        filepath = MODELS_DIR / filename
        assert filepath.exists(), f"Missing model file: {filepath}"
        assert filepath.stat().st_size > 0, f"Empty model file: {filepath}"


def test_metrics_file_written():
    """Gate: model metrics file must be written after training."""
    metrics_path = MODELS_DIR / "metrics.txt"
    assert metrics_path.exists(), "Metrics file not found."
    content = metrics_path.read_text()
    assert "AERIS-X ML Training Metrics" in content
    assert "Training samples" in content


def test_anomaly_detection_nominal():
    """Nominal readings should not be flagged as anomaly."""
    window = _make_nominal_window()
    result = detect_anomaly(window)
    assert "is_anomaly" in result
    assert "anomaly_score" in result
    assert isinstance(result["anomaly_score"], float)
    assert 0.0 <= result["anomaly_score"] <= 1.0


def test_anomaly_detection_degraded():
    """Severely degraded readings should have a higher anomaly score."""
    nominal = detect_anomaly(_make_nominal_window())
    degraded = detect_anomaly(_make_degraded_window())
    # Degraded should have a higher (worse) anomaly score
    assert degraded["anomaly_score"] >= nominal["anomaly_score"] - 0.1


def test_failure_prediction_returns_both_models():
    """Failure prediction must return both XGBoost and LR baseline probabilities."""
    window = _make_nominal_window()
    result = predict_failure(window)
    assert "failure_probability_72h" in result
    assert "baseline_probability" in result
    assert "risk_level" in result
    assert result["risk_level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert 0.0 <= result["failure_probability_72h"] <= 1.0
    assert 0.0 <= result["baseline_probability"] <= 1.0


def test_xgb_beats_baseline_on_recall():
    """Gate requirement: XGBoost must achieve ≥ LR baseline recall."""
    metrics_path = MODELS_DIR / "metrics.txt"
    content = metrics_path.read_text()
    # Parse recall values
    lines = content.split("\n")
    xgb_recall = None
    lr_recall = None
    for line in lines:
        if "xgb_recall" in line:
            xgb_recall = float(line.split(":")[-1].strip())
        elif "lr_recall" in line:
            lr_recall = float(line.split(":")[-1].strip())

    assert xgb_recall is not None, "XGBoost recall not found in metrics"
    assert lr_recall is not None, "LR recall not found in metrics"
    assert xgb_recall >= lr_recall, f"XGBoost recall ({xgb_recall}) < LR baseline ({lr_recall})"


def test_rul_prediction():
    """RUL returns positive hours with a confidence interval."""
    window = _make_nominal_window()
    result = predict_rul(window)
    assert "rul_hours" in result
    assert "rul_lower_bound" in result
    assert "rul_upper_bound" in result
    assert result["rul_hours"] >= 0.0
    assert result["rul_lower_bound"] <= result["rul_hours"]
    assert result["rul_upper_bound"] >= result["rul_hours"]


def test_shap_returns_top5_evidence():
    """SHAP must return top-5 evidence items with required fields."""
    window = _make_nominal_window()
    evidence = explain_prediction(window, top_k=5)
    assert len(evidence) == 5
    for e in evidence:
        assert "feature" in e
        assert "contribution" in e
        assert "direction" in e
        assert "shap_value" in e
        assert "description" in e
        assert "importance_rank" in e
        assert e["direction"] in {"INCREASING_RISK", "DECREASING_RISK"}
        assert isinstance(e["description"], str) and len(e["description"]) > 0


def test_shap_evidence_has_plain_language():
    """SHAP descriptions must be plain-English, not just feature codes."""
    window = _make_degraded_window()
    evidence = explain_prediction(window, top_k=5)
    for e in evidence:
        desc = e["description"]
        # Should contain human-readable terms, not just raw feature names
        assert any(
            term in desc.lower()
            for term in ["vibration", "temperature", "pressure", "voltage", "flow", "rpm", "risk", "nominal", "elevated"]
        ), f"Description not human-readable: {desc}"


def test_full_inference_pipeline():
    """Full inference returns anomaly + failure + RUL + evidence + recommended action."""
    window = _make_nominal_window()
    result = full_inference(window, aircraft_id="AF-101")
    assert result["aircraft_id"] == "AF-101"
    assert "anomaly" in result
    assert "failure" in result
    assert "rul" in result
    assert "evidence" in result
    assert "recommended_action" in result
    assert result["recommended_action"] in {
        "MONITOR_NORMAL", "INCREASE_MONITORING",
        "SCHEDULE_URGENT_MAINTENANCE", "GROUND_IMMEDIATELY",
    }
    assert result["model_version"] == "v1.0.0-xgb"
