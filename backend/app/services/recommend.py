"""
AERIS-X Recommendation Service
Derives prescriptive maintenance actions from ML predictions, RUL, and component criticality.
Rule mapping:
  Prediction + Risk Level + RUL -> Action (MONITOR / INSPECT / CALIBRATE / REPLACE / GROUND),
  Urgency, Duration, Required Spare Category, and Max Maintenance Window.
"""
from typing import Optional
from app.schemas.optimization import (
    ActionType,
    UrgencyLevel,
    RecommendationResult,
)


SPARE_MAPPING = {
    "Propulsion": {
        "default": "Turbine Blade Set",
        "sensor": "Oil Pressure Sensor",
        "nozzle": "Fuel Nozzle Assembly",
        "blade": "Turbine Blade Set",
    },
    "Avionics": {
        "default": "Radar Transmitter Module",
        "sensor": "Pitot-Static Tube Assembly",
        "computer": "Flight Control Computer",
    },
    "Hydraulics": {
        "default": "Main Hydraulic Actuator",
        "filter": "Hydraulic Filter Element",
        "valve": "Return Valve Assembly",
        "actuator": "Main Hydraulic Actuator",
    },
    "Airframe": {
        "default": "Landing Gear Shock Strut",
        "bushing": "Flap Actuator Bushing",
        "fastener": "Wing Root Fastener Kit",
        "gear": "Landing Gear Shock Strut",
    },
}


def get_recommended_spare(category: str, component_name: str = "") -> str:
    """Find appropriate spare part name for given component category."""
    cat_map = SPARE_MAPPING.get(category, SPARE_MAPPING["Propulsion"])
    comp_lower = component_name.lower()
    for keyword, spare in cat_map.items():
        if keyword in comp_lower:
            return spare
    return cat_map.get("default", "Turbine Blade Set")


def generate_recommendation(
    failure_probability: float,
    risk_level: str,
    rul_hours: float,
    component_category: str = "Propulsion",
    component_name: str = "Component",
    is_sensor: bool = False,
) -> RecommendationResult:
    """
    Generate prescriptive maintenance recommendation.

    Thresholds:
    - CRITICAL (prob >= 0.85 or RUL <= 24h):
        Immediate GROUND or EMERGENCY REPLACE. Urgency: CRITICAL. Window <= 12h.
    - HIGH (prob >= 0.60 or RUL <= 72h):
        REPLACE (or CALIBRATE if sensor). Urgency: HIGH. Window <= 48h.
    - MEDIUM (prob >= 0.35 or RUL <= 168h):
        INSPECT. Urgency: MEDIUM. Window <= 96h.
    - LOW (prob < 0.35 and RUL > 168h):
        MONITOR. Urgency: ROUTINE. Window <= 168h.
    """
    category = component_category if component_category in SPARE_MAPPING else "Propulsion"
    spare_name = get_recommended_spare(category, component_name)
    risk_upper = risk_level.upper()

    if risk_upper == "CRITICAL" or failure_probability >= 0.85 or rul_hours <= 24.0:
        if rul_hours <= 12.0 or failure_probability >= 0.90:
            action = ActionType.GROUND
            duration = 10.0
            urgency = UrgencyLevel.CRITICAL
            window = max(2.0, min(rul_hours * 0.5, 12.0))
            rationale = (
                f"CRITICAL failure probability ({failure_probability:.1%}) with RUL of only {rul_hours:.1f}h. "
                f"Immediate flight grounding mandated to prevent catastrophic in-flight loss. "
                f"Requires priority teardown and {spare_name} replacement."
            )
        else:
            action = ActionType.REPLACE
            duration = 6.0
            urgency = UrgencyLevel.CRITICAL
            window = max(4.0, min(rul_hours * 0.7, 24.0))
            rationale = (
                f"Imminent failure risk ({failure_probability:.1%}) within {rul_hours:.1f}h. "
                f"Schedule priority replacement of {component_name} using spare '{spare_name}' "
                f"before dispatching for combat or heavy training sorties."
            )

    elif risk_upper == "HIGH" or failure_probability >= 0.60 or rul_hours <= 72.0:
        if is_sensor:
            action = ActionType.CALIBRATE
            duration = 3.0
            urgency = UrgencyLevel.HIGH
            window = min(rul_hours * 0.8, 48.0)
            rationale = (
                f"Sensor anomaly detected with elevated failure probability ({failure_probability:.1%}). "
                f"Perform diagnostic bench test and calibration within {window:.1f}h."
            )
        else:
            action = ActionType.REPLACE
            duration = 5.0
            urgency = UrgencyLevel.HIGH
            window = min(rul_hours * 0.75, 48.0)
            rationale = (
                f"Elevated failure probability ({failure_probability:.1%}) and declining RUL ({rul_hours:.1f}h). "
                f"Preventive component replacement recommended within {window:.1f}h window."
            )

    elif risk_upper == "MEDIUM" or failure_probability >= 0.35 or rul_hours <= 168.0:
        action = ActionType.INSPECT
        duration = 2.5
        urgency = UrgencyLevel.MEDIUM
        window = min(rul_hours * 0.8, 96.0)
        rationale = (
            f"Moderate risk indicator ({failure_probability:.1%}). "
            f"Perform borescope / physical non-destructive inspection of {component_name} "
            f"during next scheduled turnaround (within {window:.1f}h)."
        )

    else:
        action = ActionType.MONITOR
        duration = 0.5
        urgency = UrgencyLevel.ROUTINE
        window = 168.0
        rationale = (
            f"Nominal telemetry operating state. Failure probability is low ({failure_probability:.1%}) "
            f"and RUL is healthy ({rul_hours:.1f}h). Continue standard health monitoring."
        )

    return RecommendationResult(
        action=action,
        urgency=urgency,
        duration_hours=duration,
        required_spare_category=category,
        required_spare_name=spare_name if action in [ActionType.REPLACE, ActionType.GROUND] else None,
        recommended_window_hours=round(window, 1),
        rationale=rationale,
    )
