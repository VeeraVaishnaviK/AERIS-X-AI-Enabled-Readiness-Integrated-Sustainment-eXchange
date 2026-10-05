"""
AERIS-X ML Model Registry
Handles loading, saving, and version management of trained models.
Models are stored as joblib files under backend/models/.
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional

import joblib

from app.core.logging import get_logger

logger = get_logger("aeris.ml.registry")

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_MANIFEST: Dict[str, str] = {
    "anomaly_detector": "anomaly_iforest_v1.joblib",
    "failure_xgb": "failure_xgb_v1.joblib",
    "failure_lr": "failure_lr_v1.joblib",
    "rul_xgb": "rul_xgb_v1.joblib",
    "feature_scaler": "feature_scaler_v1.joblib",
}

_model_cache: Dict[str, Any] = {}


def save_model(name: str, model: Any) -> Path:
    """Save a model to disk and register it."""
    if name not in MODEL_MANIFEST:
        MODEL_MANIFEST[name] = f"{name}.joblib"

    filepath = MODELS_DIR / MODEL_MANIFEST[name]
    joblib.dump(model, filepath)
    _model_cache[name] = model
    logger.info(f"Model '{name}' saved to {filepath}")
    return filepath


def load_model(name: str) -> Optional[Any]:
    """Load a model from cache or disk."""
    if name in _model_cache:
        return _model_cache[name]

    filename = MODEL_MANIFEST.get(name)
    if not filename:
        logger.warning(f"Unknown model name: {name}")
        return None

    filepath = MODELS_DIR / filename
    if not filepath.exists():
        logger.warning(f"Model file not found: {filepath}")
        return None

    model = joblib.load(filepath)
    _model_cache[name] = model
    logger.info(f"Model '{name}' loaded from {filepath}")
    return model


def models_exist() -> bool:
    """Check if all required models have been trained and saved."""
    for name, filename in MODEL_MANIFEST.items():
        filepath = MODELS_DIR / filename
        if not filepath.exists():
            return False
    return True


def get_model_versions() -> Dict[str, Dict[str, Any]]:
    """Return version info for all registered models."""
    info = {}
    for name, filename in MODEL_MANIFEST.items():
        filepath = MODELS_DIR / filename
        info[name] = {
            "filename": filename,
            "exists": filepath.exists(),
            "size_bytes": filepath.stat().st_size if filepath.exists() else 0,
        }
    return info
