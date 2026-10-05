"""
Tests for Phase 8 — Monitoring, Alerts, and Realtime Streaming Arc
Validates:
- Alert generation rules and evidence capture
- Alert resolution lifecycle (OPEN -> ACKNOWLEDGED -> RESOLVED)
- Model outcome monitoring and precision/recall/RUL MAE evaluation
- Telemetry simulator 6-stage arc (NORMAL -> DEGRADATION -> ANOMALY -> HIGH_RISK -> MAINTENANCE -> RECOVERY)
- MANDATORY GATE: WebSocket test receives ticks and an alert fires at the correct stage
- POST /api/v1/simulation/live/start endpoint
"""
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.monitoring import OutcomeRecordInput
from app.schemas.simulation_stream import ArcStage
from app.services.alerts import evaluate_alert_rules, create_alert_db, update_alert_status_db
from app.services.monitoring import compute_evaluation_metrics, record_evaluation_to_db
from app.services.telemetry_sim import generate_arc_tick, stream_arc_generator
from app.schemas.alert import AlertCreate


client = TestClient(app)


# ---------------------------------------------------------
# 1. Alert Generation Tests
# ---------------------------------------------------------

def test_alert_generation_rules():
    """Alerts trigger on critical RUL, elevated failure probability, and anomalies."""
    # Critical Alert
    crit_alert = evaluate_alert_rules(
        aircraft_id="AC-01",
        failure_probability=0.91,
        rul_hours=14.0,
        risk_level="CRITICAL",
        anomaly_feature="vibration",
    )
    assert crit_alert is not None
    assert crit_alert.severity == "CRITICAL"
    assert crit_alert.trigger_rule == "CRITICAL_FAILURE_PROBABILITY_OR_RUL"
    assert "evidence_summary" in crit_alert.model_dump()

    # Warning Alert (High Failure Probability)
    warn_alert = evaluate_alert_rules(
        aircraft_id="AC-02",
        failure_probability=0.68,
        rul_hours=42.0,
        risk_level="HIGH",
        anomaly_feature="egt",
    )
    assert warn_alert is not None
    assert warn_alert.severity == "WARNING"
    assert warn_alert.trigger_rule == "HIGH_FAILURE_PROBABILITY_72H"

    # Anomaly Alert (Isolation Forest)
    anom_alert = evaluate_alert_rules(
        aircraft_id="AC-03",
        failure_probability=0.25,
        rul_hours=200.0,
        risk_level="LOW",
        is_anomaly=True,
        anomaly_feature="hydraulic_pressure",
    )
    assert anom_alert is not None
    assert anom_alert.severity == "WARNING"
    assert anom_alert.trigger_rule == "ISOLATION_FOREST_ANOMALY"

    # Nominal (No Alert)
    nominal = evaluate_alert_rules(
        aircraft_id="AC-04",
        failure_probability=0.03,
        rul_hours=600.0,
        risk_level="LOW",
        is_anomaly=False,
    )
    assert nominal is None


@pytest.mark.asyncio
async def test_alert_lifecycle_in_db():
    """Test creating, acknowledging, and resolving an alert."""
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db_session:
        alert_in = AlertCreate(
            aircraft_id="IAF-TS-01",
            severity="WARNING",
            title="Elevated Vibration Alert",
            message="Vibration sensor drift detected on turbine bearing.",
            trigger_rule="ISOLATION_FOREST_ANOMALY",
            evidence_summary={"sensor": "vibration", "value": 2.4},
        )
        # 1. Create
        alert = await create_alert_db(db_session, alert_in)
        assert alert.id is not None
        assert alert.status == "OPEN"

        # 2. Acknowledge
        ack_alert = await update_alert_status_db(db_session, alert.id, "ACKNOWLEDGED")
        assert ack_alert.status == "ACKNOWLEDGED"

        # 3. Resolve
        resolved = await update_alert_status_db(
            db_session, alert.id, "RESOLVED", resolution_notes="Turbine bearing replaced in Bay 01."
        )
        assert resolved.status == "RESOLVED"
        assert resolved.resolved_at is not None
        assert "resolution_notes" in resolved.evidence_summary


# ---------------------------------------------------------
# 2. Model Monitoring & Outcome Metrics Tests
# ---------------------------------------------------------

def test_model_monitoring_evaluation_metrics():
    """Verify precision, recall, F1, and RUL error calculations."""
    base_t = datetime.now(timezone.utc)
    outcomes = [
        # True Positive (TP)
        OutcomeRecordInput(
            prediction_id=1,
            aircraft_id="AC-01",
            predicted_failure=True,
            predicted_probability=0.85,
            predicted_rul_hours=40.0,
            actual_failure_occurred=True,
            prediction_timestamp=base_t,
            resolution_timestamp=base_t,
            actual_lead_time_hours=44.0,
            component_inspected_condition="FAILED",
        ),
        # True Positive (TP)
        OutcomeRecordInput(
            prediction_id=2,
            aircraft_id="AC-02",
            predicted_failure=True,
            predicted_probability=0.72,
            predicted_rul_hours=50.0,
            actual_failure_occurred=True,
            prediction_timestamp=base_t,
            resolution_timestamp=base_t,
            actual_lead_time_hours=48.0,
            component_inspected_condition="HEAVILY_WORN",
        ),
        # False Positive (FP) - False Alarm
        OutcomeRecordInput(
            prediction_id=3,
            aircraft_id="AC-03",
            predicted_failure=True,
            predicted_probability=0.62,
            predicted_rul_hours=60.0,
            actual_failure_occurred=False,
            prediction_timestamp=base_t,
            resolution_timestamp=base_t,
            actual_lead_time_hours=72.0,
            component_inspected_condition="NOMINAL_FALSE_ALARM",
        ),
        # True Negative (TN)
        OutcomeRecordInput(
            prediction_id=4,
            aircraft_id="AC-04",
            predicted_failure=False,
            predicted_probability=0.10,
            predicted_rul_hours=400.0,
            actual_failure_occurred=False,
            prediction_timestamp=base_t,
            resolution_timestamp=base_t,
            actual_lead_time_hours=400.0,
            component_inspected_condition="NOMINAL",
        ),
    ]

    metrics = compute_evaluation_metrics(outcomes)

    assert metrics.sample_count == 4
    assert metrics.true_positives == 2
    assert metrics.false_positives == 1
    assert metrics.true_negatives == 1
    assert metrics.false_negatives == 0
    # Precision = 2 / (2 + 1) = 0.6667
    assert 0.65 <= metrics.precision <= 0.68
    # Recall = 2 / (2 + 0) = 1.0
    assert metrics.recall == 1.0
    assert metrics.rul_mae_hours >= 0.0
    assert metrics.mean_lead_time_hours > 0.0


# ---------------------------------------------------------
# 3. Telemetry Simulator Arc Tests
# ---------------------------------------------------------

def test_telemetry_simulator_arc_stages():
    """Verify all 6 stages of the telemetry arc and alert trigger points."""
    stages_encountered = set()
    alerts_fired = []

    for t in range(1, 61):
        tick = generate_arc_tick(tick_number=t, aircraft_id="IAF-TS-01", total_ticks=60)
        stages_encountered.add(tick.stage)

        if tick.active_alert:
            alerts_fired.append((tick.stage, tick.active_alert))

    # All 6 stages must be visited
    expected_stages = {
        ArcStage.NORMAL,
        ArcStage.DEGRADATION,
        ArcStage.ANOMALY,
        ArcStage.HIGH_RISK,
        ArcStage.MAINTENANCE,
        ArcStage.RECOVERY,
    }
    assert stages_encountered == expected_stages

    # Alerts must fire at ANOMALY and HIGH_RISK
    stages_with_alerts = set(item[0] for item in alerts_fired)
    assert ArcStage.ANOMALY in stages_with_alerts
    assert ArcStage.HIGH_RISK in stages_with_alerts


# ---------------------------------------------------------
# 4. Mandatory Gate: WebSocket Stream and Alert Firing
# ---------------------------------------------------------

def test_websocket_telemetry_stream_gate():
    """
    MANDATORY GATE:
    WebSocket test receives ticks and an alert fires at the correct stage.
    """
    with client.websocket_connect("/ws/telemetry?aircraft_id=IAF-TS-01") as ws:
        received_ticks = []
        alerts_received = []

        # Read 60 ticks from stream
        for _ in range(60):
            data = ws.receive_json()
            received_ticks.append(data)
            if data.get("active_alert"):
                alerts_received.append(data)

        # Gate assertion 1: WebSocket receives ticks
        assert len(received_ticks) == 60, f"Expected 60 ticks, received {len(received_ticks)}"

        # Gate assertion 2: Alert fires at the correct stage
        assert len(alerts_received) > 0, "No alerts fired during telemetry stream"

        alert_stages = [a["stage"] for a in alerts_received]
        assert "ANOMALY" in alert_stages or "HIGH_RISK" in alert_stages, (
            f"Alert did not fire at ANOMALY or HIGH_RISK stage! Stages: {alert_stages}"
        )

        # Verify initial and terminal states
        first_tick = received_ticks[0]
        assert first_tick["stage"] == "NORMAL"
        assert first_tick["health_score"] >= 95.0

        last_tick = received_ticks[-1]
        assert last_tick["stage"] == "RECOVERY"
        assert last_tick["health_score"] >= 95.0
        assert last_tick["risk_level"] == "LOW"


def test_post_simulation_live_start():
    """Verify POST /api/v1/simulation/live/start endpoint."""
    resp = client.post(
        "/api/v1/simulation/live/start",
        json={"aircraft_id": "IAF-TS-01", "tick_interval_ms": 100, "total_ticks": 60},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "STARTED"
    assert data["aircraft_id"] == "IAF-TS-01"
    assert data["websocket_endpoint"] == "/ws/telemetry"
    assert "initial_tick" in data
