"""
AERIS-X ML Feature Engineering
Builds rolling-window feature vectors from raw telemetry for:
- Anomaly detection (IsolationForest)
- Failure probability (XGBoost Classifier + Logistic Regression baseline)
- RUL estimation (XGBoost Regressor)
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple

from app.synthetic.scenarios import SENSOR_BASELINES

SENSOR_NAMES = list(SENSOR_BASELINES.keys())
WINDOW_SIZES = [6, 24]  # 6-hour and 24-hour rolling windows


def build_feature_row(
    telemetry_window: List[Dict[str, float]],
    sensor_names: Optional[List[str]] = None,
) -> Dict[str, float]:
    """
    Build a single feature vector from a window of telemetry dicts.
    Features per sensor:
        - latest value
        - mean over window
        - std over window
        - min / max over window
        - rate of change (last - first) / window_size
    """
    if sensor_names is None:
        sensor_names = SENSOR_NAMES

    features: Dict[str, float] = {}
    n = len(telemetry_window)

    for sensor in sensor_names:
        vals = [float(t.get(sensor, 0.0)) for t in telemetry_window if t.get(sensor) is not None]

        if not vals:
            features[f"{sensor}_latest"] = 0.0
            features[f"{sensor}_mean"] = 0.0
            features[f"{sensor}_std"] = 0.0
            features[f"{sensor}_min"] = 0.0
            features[f"{sensor}_max"] = 0.0
            features[f"{sensor}_rate"] = 0.0
            continue

        arr = np.array(vals, dtype=np.float64)
        features[f"{sensor}_latest"] = float(arr[-1])
        features[f"{sensor}_mean"] = float(np.mean(arr))
        features[f"{sensor}_std"] = float(np.std(arr))
        features[f"{sensor}_min"] = float(np.min(arr))
        features[f"{sensor}_max"] = float(np.max(arr))
        features[f"{sensor}_rate"] = float((arr[-1] - arr[0]) / max(n, 1))

    return features


def build_training_dataset(
    telemetry_df: pd.DataFrame,
    window_size: int = 24,
) -> Tuple[pd.DataFrame, Optional[pd.Series], Optional[pd.Series]]:
    """
    Build training dataset from telemetry DataFrame.
    Expects columns: aircraft_id, timestamp, + sensor columns,
    and optionally: is_anomaly (bool), rul_hours (float).
    Returns: (feature_df, failure_labels, rul_labels)
    """
    telemetry_df = telemetry_df.sort_values(["aircraft_id", "timestamp"]).reset_index(drop=True)

    all_features = []
    failure_labels = []
    rul_labels = []
    aircraft_ids = []

    for ac_id, group in telemetry_df.groupby("aircraft_id"):
        rows = group.to_dict("records")
        n = len(rows)

        for i in range(window_size, n):
            window = rows[max(0, i - window_size):i]
            feat = build_feature_row(window)
            all_features.append(feat)
            aircraft_ids.append(ac_id)

            # Failure label: does a failure occur in the next 72 ticks (hours)?
            lookahead = rows[i:min(i + 72, n)]
            has_failure = any(r.get("is_anomaly", False) for r in lookahead)
            failure_labels.append(1 if has_failure else 0)

            # RUL: hours until next anomaly, or remaining data length
            rul = None
            for j, r in enumerate(rows[i:]):
                if r.get("is_anomaly", False):
                    rul = j
                    break
            if rul is None:
                rul = n - i
            rul_labels.append(float(rul))

    feature_df = pd.DataFrame(all_features)
    feature_df["aircraft_id"] = aircraft_ids

    return (
        feature_df,
        pd.Series(failure_labels, name="failure_72h") if failure_labels else None,
        pd.Series(rul_labels, name="rul_hours") if rul_labels else None,
    )


def get_feature_names() -> List[str]:
    """Return the ordered list of feature column names (excluding aircraft_id)."""
    names = []
    for sensor in SENSOR_NAMES:
        for suffix in ["latest", "mean", "std", "min", "max", "rate"]:
            names.append(f"{sensor}_{suffix}")
    return names
