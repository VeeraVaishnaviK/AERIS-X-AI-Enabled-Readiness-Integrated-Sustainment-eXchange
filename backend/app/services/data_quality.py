"""
AERIS-X Data Quality Engine
Performs multi-criteria telemetry validation:
- Missing / Null check
- Physical plausible range validation
- Sudden spike / rate-of-change check
- Stuck sensor / flatline detection over temporal window
- Sensor drift detection
Computes a transparent 0-100 quality score with itemized penalty audit.
"""
import math
from typing import Any, Dict, List, Optional
import numpy as np

from app.schemas.quality import DataQualityResult, SensorQualityDetail


PHYSICAL_SENSOR_BOUNDS: Dict[str, Dict[str, float]] = {
    "vibration": {
        "min_phys": 0.0,
        "max_phys": 15.0,
        "max_rate_of_change": 3.0,
        "drift_threshold": 1.5,
    },
    "egt": {
        "min_phys": 0.0,
        "max_phys": 1200.0,
        "max_rate_of_change": 250.0,
        "drift_threshold": 100.0,
    },
    "oil_pressure": {
        "min_phys": 0.0,
        "max_phys": 100.0,
        "max_rate_of_change": 25.0,
        "drift_threshold": 12.0,
    },
    "oil_temperature": {
        "min_phys": -40.0,
        "max_phys": 180.0,
        "max_rate_of_change": 30.0,
        "drift_threshold": 15.0,
    },
    "fuel_flow": {
        "min_phys": 0.0,
        "max_phys": 4000.0,
        "max_rate_of_change": 800.0,
        "drift_threshold": 300.0,
    },
    "hydraulic_pressure": {
        "min_phys": 0.0,
        "max_phys": 5000.0,
        "max_rate_of_change": 800.0,
        "drift_threshold": 400.0,
    },
    "battery_voltage": {
        "min_phys": 10.0,
        "max_phys": 36.0,
        "max_rate_of_change": 5.0,
        "drift_threshold": 3.0,
    },
    "n1_rpm": {
        "min_phys": 0.0,
        "max_phys": 120.0,
        "max_rate_of_change": 20.0,
        "drift_threshold": 6.0,
    },
    "n2_rpm": {
        "min_phys": 0.0,
        "max_phys": 120.0,
        "max_rate_of_change": 20.0,
        "drift_threshold": 6.0,
    },
}

PENALTY_WEIGHTS = {
    "MISSING": 15.0,
    "OUT_OF_BOUNDS": 20.0,
    "STUCK_SENSOR": 12.0,
    "SPIKE": 10.0,
    "DRIFT": 8.0,
}


class DataQualityEngine:
    """Evaluates telemetry records and windows for data quality and anomalies."""

    @staticmethod
    def evaluate_record(
        telemetry: Dict[str, Any],
        aircraft_id: str,
        recent_window: Optional[List[Dict[str, Any]]] = None,
    ) -> DataQualityResult:
        """
        Evaluate a single telemetry tick, optionally comparing against a recent history window.
        Returns a DataQualityResult with 0-100 score and itemized deductions.
        """
        penalties: List[SensorQualityDetail] = []
        sensor_statuses: Dict[str, str] = {}

        for sensor_name, bounds in PHYSICAL_SENSOR_BOUNDS.items():
            val = telemetry.get(sensor_name)

            # 1. Missing Check
            if val is None or (isinstance(val, float) and math.isnan(val)):
                sensor_statuses[sensor_name] = "MISSING"
                penalties.append(
                    SensorQualityDetail(
                        sensor_name=sensor_name,
                        value=None,
                        status="MISSING",
                        penalty=PENALTY_WEIGHTS["MISSING"],
                        details=f"Sensor {sensor_name} reported null or NaN value.",
                    )
                )
                continue

            val_float = float(val)

            # 2. Physical Range Check
            if val_float < bounds["min_phys"] or val_float > bounds["max_phys"]:
                sensor_statuses[sensor_name] = "OUT_OF_BOUNDS"
                penalties.append(
                    SensorQualityDetail(
                        sensor_name=sensor_name,
                        value=val_float,
                        status="OUT_OF_BOUNDS",
                        penalty=PENALTY_WEIGHTS["OUT_OF_BOUNDS"],
                        details=f"Value {val_float} is outside plausible physics range [{bounds['min_phys']}, {bounds['max_phys']}].",
                    )
                )
                continue

            # Temporal Window Checks (if historical sequence provided)
            status = "NOMINAL"
            if recent_window and len(recent_window) > 0:
                history_vals = [
                    float(r[sensor_name]) for r in recent_window
                    if r.get(sensor_name) is not None and not math.isnan(float(r[sensor_name]))
                ]

                if len(history_vals) > 0:
                    prev_val = history_vals[-1]
                    rate_of_change = abs(val_float - prev_val)

                    # 3. Sudden Spike / Unphysical Rate of Change
                    if rate_of_change > bounds["max_rate_of_change"]:
                        status = "SPIKE"
                        penalties.append(
                            SensorQualityDetail(
                                sensor_name=sensor_name,
                                value=val_float,
                                status="SPIKE",
                                penalty=PENALTY_WEIGHTS["SPIKE"],
                                details=f"Rate of change ({rate_of_change:.2f}) exceeds physical threshold ({bounds['max_rate_of_change']}).",
                            )
                        )

                    # 4. Stuck Sensor / Flatline Check (needs at least 4 previous identical values)
                    elif len(history_vals) >= 4:
                        all_vals = history_vals[-4:] + [val_float]
                        std_dev = float(np.std(all_vals))
                        if std_dev < 1e-5:
                            status = "STUCK_SENSOR"
                            penalties.append(
                                SensorQualityDetail(
                                    sensor_name=sensor_name,
                                    value=val_float,
                                    status="STUCK_SENSOR",
                                    penalty=PENALTY_WEIGHTS["STUCK_SENSOR"],
                                    details=f"Sensor is flatlined across {len(all_vals)} consecutive readings (std={std_dev:.5f}).",
                                )
                            )

                    # 5. Persistent Drift Check (mean deviation over 10+ samples)
                    elif len(history_vals) >= 10:
                        baseline_mean = float(np.mean(history_vals[:5]))
                        current_mean = float(np.mean(history_vals[-5:] + [val_float]))
                        drift = abs(current_mean - baseline_mean)
                        if drift > bounds["drift_threshold"]:
                            status = "DRIFT"
                            penalties.append(
                                SensorQualityDetail(
                                    sensor_name=sensor_name,
                                    value=val_float,
                                    status="DRIFT",
                                    penalty=PENALTY_WEIGHTS["DRIFT"],
                                    details=f"Sensor baseline drifted by {drift:.2f}, exceeding drift tolerance {bounds['drift_threshold']}.",
                                )
                            )

            sensor_statuses[sensor_name] = status

        total_penalty = sum(p.penalty for p in penalties)
        quality_score = max(0.0, min(100.0, round(100.0 - total_penalty, 2)))
        confidence = round(quality_score / 100.0, 3)
        is_valid = quality_score >= 60.0

        return DataQualityResult(
            aircraft_id=aircraft_id,
            quality_score=quality_score,
            is_valid=is_valid,
            penalties=penalties,
            sensor_statuses=sensor_statuses,
            confidence=confidence,
        )
