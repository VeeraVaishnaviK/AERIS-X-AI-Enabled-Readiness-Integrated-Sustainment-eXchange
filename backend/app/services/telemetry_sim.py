"""
AERIS-X Telemetry Simulator & Realtime Streaming Arc
Simulates the operational lifecycle of an aircraft across 6 deterministic stages:
  1. NORMAL: Stable baseline telemetry
  2. DEGRADATION: Thermal and mechanical wear drift
  3. ANOMALY: Out-of-bounds anomaly; IsolationForest flags event; ANOMALY ALERT fires
  4. HIGH_RISK: Critical risk threshold breached; CRITICAL ALERT fires
  5. MAINTENANCE: Engine shutdown, hangar servicing, blade replacement
  6. RECOVERY: Calibrated post-overhaul return to nominal flight ready state
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator, Dict, Optional

from app.schemas.simulation_stream import ArcStage, TelemetryTick
from app.services.alerts import evaluate_alert_rules


def generate_arc_tick(
    tick_number: int,
    aircraft_id: str = "IAF-TS-01",
    total_ticks: int = 60,
    base_time: Optional[datetime] = None,
) -> TelemetryTick:
    """
    Generates a single tick along the 6-stage telemetry arc.
    """
    base_time = base_time or datetime.now(timezone.utc)
    tick_timestamp = base_time + timedelta(seconds=tick_number * 2)

    # Determine stage based on progress
    pct = tick_number / max(1, total_ticks)

    if pct < 0.20:
        stage = ArcStage.NORMAL
        vibration = 0.82 + (0.05 * (tick_number % 3))
        egt = 618.0 + (3.0 * (tick_number % 4))
        oil_temp = 84.5 + (1.0 * (tick_number % 2))
        oil_pressure = 48.0 - (0.5 * (tick_number % 2))
        fuel_flow = 1450.0
        hydraulic_pressure = 3000.0
        health_score = 98.0
        fail_prob = 0.03
        rul_hours = 650.0
        risk_level = "LOW"
        is_anomaly = False

    elif pct < 0.40:
        stage = ArcStage.DEGRADATION
        prog = (pct - 0.20) / 0.20
        vibration = 0.95 + (0.6 * prog)
        egt = 630.0 + (35.0 * prog)
        oil_temp = 86.0 + (8.0 * prog)
        oil_pressure = 47.0 - (3.0 * prog)
        fuel_flow = 1480.0 + (40.0 * prog)
        hydraulic_pressure = 2980.0
        health_score = round(92.0 - (12.0 * prog), 1)
        fail_prob = round(0.08 + (0.25 * prog), 3)
        rul_hours = round(500.0 - (280.0 * prog), 1)
        risk_level = "MEDIUM" if fail_prob >= 0.25 else "LOW"
        is_anomaly = False

    elif pct < 0.60:
        stage = ArcStage.ANOMALY
        prog = (pct - 0.40) / 0.20
        vibration = 1.65 + (0.75 * prog)
        egt = 675.0 + (30.0 * prog)
        oil_temp = 96.0 + (12.0 * prog)
        oil_pressure = 43.0 - (4.0 * prog)
        fuel_flow = 1530.0 + (60.0 * prog)
        hydraulic_pressure = 2950.0
        health_score = round(78.0 - (18.0 * prog), 1)
        fail_prob = round(0.38 + (0.28 * prog), 3)
        rul_hours = round(200.0 - (110.0 * prog), 1)
        risk_level = "HIGH" if fail_prob >= 0.60 else "MEDIUM"
        is_anomaly = True  # Triggers anomaly detector

    elif pct < 0.75:
        stage = ArcStage.HIGH_RISK
        prog = (pct - 0.60) / 0.15
        vibration = 2.60 + (0.90 * prog)  # Severe vibration
        egt = 720.0 + (45.0 * prog)
        oil_temp = 112.0 + (15.0 * prog)
        oil_pressure = 37.0 - (6.0 * prog)
        fuel_flow = 1620.0 + (80.0 * prog)
        hydraulic_pressure = 2910.0
        health_score = round(55.0 - (30.0 * prog), 1)
        fail_prob = round(0.72 + (0.22 * prog), 3)
        rul_hours = max(6.0, round(80.0 - (68.0 * prog), 1))
        risk_level = "CRITICAL"
        is_anomaly = True

    elif pct < 0.90:
        stage = ArcStage.MAINTENANCE
        # Hangar servicing: aircraft engines powered down, blade changeout
        vibration = 0.05
        egt = 38.0
        oil_temp = 32.0
        oil_pressure = 0.0
        fuel_flow = 0.0
        hydraulic_pressure = 0.0
        health_score = 65.0  # Under repair
        fail_prob = 0.10
        rul_hours = 12.0
        risk_level = "LOW"
        is_anomaly = False

    else:
        stage = ArcStage.RECOVERY
        # Repaired and test flown: restored to prime condition
        vibration = 0.78
        egt = 612.0
        oil_temp = 83.0
        oil_pressure = 48.5
        fuel_flow = 1440.0
        hydraulic_pressure = 3010.0
        health_score = 99.0
        fail_prob = 0.02
        rul_hours = 720.0
        risk_level = "LOW"
        is_anomaly = False

    sensors = {
        "vibration": round(vibration, 3),
        "egt": round(egt, 1),
        "oil_temp": round(oil_temp, 1),
        "oil_pressure": round(oil_pressure, 1),
        "fuel_flow": round(fuel_flow, 1),
        "hydraulic_pressure": round(hydraulic_pressure, 1),
        "n1_rpm_pct": 98.5 if stage not in [ArcStage.MAINTENANCE] else 0.0,
        "n2_rpm_pct": 99.1 if stage not in [ArcStage.MAINTENANCE] else 0.0,
    }

    # Evaluate if an alert should accompany this tick
    alert_candidate = evaluate_alert_rules(
        aircraft_id=aircraft_id,
        failure_probability=fail_prob,
        rul_hours=rul_hours,
        risk_level=risk_level,
        is_anomaly=is_anomaly,
        anomaly_feature="vibration" if is_anomaly else "",
        telemetry_snapshot=sensors,
    )

    alert_dict = None
    if alert_candidate:
        alert_dict = {
            "severity": alert_candidate.severity,
            "title": alert_candidate.title,
            "trigger_rule": alert_candidate.trigger_rule,
            "stage": stage.value,
        }

    return TelemetryTick(
        tick_number=tick_number,
        timestamp=tick_timestamp,
        aircraft_id=aircraft_id,
        stage=stage,
        sensors=sensors,
        health_score=health_score,
        failure_probability=fail_prob,
        rul_hours=rul_hours,
        risk_level=risk_level,
        active_alert=alert_dict,
    )


async def stream_arc_generator(
    aircraft_id: str = "IAF-TS-01",
    tick_delay_s: float = 0.05,
    total_ticks: int = 60,
) -> AsyncGenerator[TelemetryTick, None]:
    """Async generator yielding simulated ticks."""
    base_time = datetime.now(timezone.utc)
    for tick_idx in range(1, total_ticks + 1):
        tick = generate_arc_tick(
            tick_number=tick_idx,
            aircraft_id=aircraft_id,
            total_ticks=total_ticks,
            base_time=base_time,
        )
        yield tick
        if tick_delay_s > 0:
            await asyncio.sleep(tick_delay_s)
