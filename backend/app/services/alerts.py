"""
AERIS-X Alert Generation and Resolution Workflow Service
Handles:
- Alert creation from anomaly scores, failure predictions, RUL drops, and sensor faults
- Evidence attachment
- Workflow transitions: OPEN -> ACKNOWLEDGED -> ACTIONED -> RESOLVED / DISMISSED
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert import Alert
from app.schemas.alert import AlertCreate, AlertResponse


def evaluate_alert_rules(
    aircraft_id: str,
    component_id: Optional[int] = None,
    prediction_id: Optional[int] = None,
    failure_probability: float = 0.0,
    rul_hours: float = 500.0,
    risk_level: str = "LOW",
    is_anomaly: bool = False,
    anomaly_feature: str = "",
    telemetry_snapshot: Optional[Dict[str, float]] = None,
) -> Optional[AlertCreate]:
    """
    Evaluates rule set to determine if an alert should be triggered.
    """
    telemetry_snapshot = telemetry_snapshot or {}

    # Rule 1: CRITICAL or Imminent RUL
    if risk_level.upper() == "CRITICAL" or failure_probability >= 0.85 or rul_hours <= 24.0:
        return AlertCreate(
            aircraft_id=aircraft_id,
            component_id=component_id,
            prediction_id=prediction_id,
            severity="CRITICAL",
            title=f"CRITICAL: Imminent Failure Risk ({failure_probability:.1%}) on {aircraft_id}",
            message=(
                f"Remaining useful life collapsed to {rul_hours:.1f}h. "
                f"Immediate maintenance action required to avoid flight grounding."
            ),
            trigger_rule="CRITICAL_FAILURE_PROBABILITY_OR_RUL",
            evidence_summary={
                "failure_probability": failure_probability,
                "rul_hours": rul_hours,
                "risk_level": "CRITICAL",
                "dominant_sensor": anomaly_feature or "Vibration",
                "sensors": telemetry_snapshot,
            },
        )

    # Rule 2: HIGH Risk Failure Prediction (Next 72h)
    if risk_level.upper() == "HIGH" or failure_probability >= 0.60 or rul_hours <= 72.0:
        return AlertCreate(
            aircraft_id=aircraft_id,
            component_id=component_id,
            prediction_id=prediction_id,
            severity="WARNING",
            title=f"HIGH RISK: Elevated Failure Probability ({failure_probability:.1%}) on {aircraft_id}",
            message=(
                f"Predictive models indicate {failure_probability:.1%} probability of component failure "
                f"within the next 72 operating hours (RUL: {rul_hours:.1f}h)."
            ),
            trigger_rule="HIGH_FAILURE_PROBABILITY_72H",
            evidence_summary={
                "failure_probability": failure_probability,
                "rul_hours": rul_hours,
                "risk_level": "HIGH",
                "evidence_feature": anomaly_feature,
                "sensors": telemetry_snapshot,
            },
        )

    # Rule 3: Unsupervised Sensor Anomaly
    if is_anomaly:
        return AlertCreate(
            aircraft_id=aircraft_id,
            component_id=component_id,
            prediction_id=prediction_id,
            severity="WARNING",
            title=f"ANOMALY: Out-of-Distribution Sensor Signatures on {aircraft_id}",
            message=f"Isolation Forest flagged atypical multivariate telemetry patterns in {anomaly_feature or 'telemetry'}.",
            trigger_rule="ISOLATION_FOREST_ANOMALY",
            evidence_summary={
                "is_anomaly": True,
                "flagged_group": anomaly_feature,
                "sensors": telemetry_snapshot,
            },
        )

    return None


async def create_alert_db(session: AsyncSession, alert_in: AlertCreate) -> Alert:
    """Persist a new alert in database."""
    alert = Alert(
        aircraft_id=alert_in.aircraft_id,
        component_id=alert_in.component_id,
        prediction_id=alert_in.prediction_id,
        severity=alert_in.severity,
        title=alert_in.title,
        message=alert_in.message,
        status="OPEN",
        trigger_rule=alert_in.trigger_rule,
        evidence_summary=alert_in.evidence_summary,
    )
    session.add(alert)
    await session.commit()
    await session.refresh(alert)
    return alert


async def update_alert_status_db(
    session: AsyncSession,
    alert_id: int,
    new_status: str,
    resolution_notes: Optional[str] = None,
) -> Optional[Alert]:
    """Progress alert through resolution workflow."""
    alert = await session.get(Alert, alert_id)
    if not alert:
        return None

    alert.status = new_status.upper()
    if new_status.upper() in ["RESOLVED", "DISMISSED"]:
        alert.resolved_at = datetime.now(timezone.utc)
    if resolution_notes:
        existing_evidence = dict(alert.evidence_summary or {})
        existing_evidence["resolution_notes"] = resolution_notes
        alert.evidence_summary = existing_evidence

    await session.commit()
    await session.refresh(alert)
    return alert


async def get_active_alerts_db(session: AsyncSession, aircraft_id: Optional[str] = None) -> List[Alert]:
    """Query currently open or acknowledged alerts."""
    query = select(Alert).where(Alert.status.in_(["OPEN", "ACKNOWLEDGED"]))
    if aircraft_id:
        query = query.where(Alert.aircraft_id == aircraft_id)
    query = query.order_by(Alert.id.desc())
    result = await session.execute(query)
    return list(result.scalars().all())
