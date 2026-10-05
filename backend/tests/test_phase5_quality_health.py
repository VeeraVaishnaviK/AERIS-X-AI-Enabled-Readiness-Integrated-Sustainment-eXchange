"""
Tests for Phase 5 — Data Quality & Health Index Engine.
Validates:
- 0-100 Data quality scoring, boundary limits, missing sensor handling
- Temporal anomaly checks: spike, flatline/stuck sensor, drift
- Component Health Index (CHI) calculation and penalty breakdown
- Aircraft Health Index (AHI) weighted formula: 0.40 * min(CHI) + 0.60 * weighted_avg(CHI)
- Airworthiness status and risk level derivation
- Plain-English audit explanation generation
"""
import pytest
from app.db.session import AsyncSessionLocal
from app.services.data_quality import DataQualityEngine
from app.services.health_index import HealthIndexEngine


def test_nominal_telemetry_quality():
    """Nominal sensor readings should yield a 100.0 quality score."""
    telemetry = {
        "vibration": 1.2,
        "egt": 650.0,
        "oil_pressure": 45.0,
        "oil_temperature": 95.0,
        "fuel_flow": 1150.0,
        "hydraulic_pressure": 3000.0,
        "battery_voltage": 28.0,
        "n1_rpm": 98.0,
        "n2_rpm": 95.0,
    }
    result = DataQualityEngine.evaluate_record(telemetry, aircraft_id="AF-TEST-01")
    assert result.quality_score == 100.0
    assert result.is_valid is True
    assert result.confidence == 1.0
    assert len(result.penalties) == 0
    for sensor, status in result.sensor_statuses.items():
        assert status == "NOMINAL"


def test_missing_sensor_penalty():
    """Missing or NaN sensor values should be penalized and tagged MISSING."""
    telemetry = {
        "vibration": None,
        "egt": float("nan"),
        "oil_pressure": 45.0,
        "oil_temperature": 95.0,
        "fuel_flow": 1150.0,
        "hydraulic_pressure": 3000.0,
        "battery_voltage": 28.0,
        "n1_rpm": 98.0,
        "n2_rpm": 95.0,
    }
    result = DataQualityEngine.evaluate_record(telemetry, aircraft_id="AF-TEST-02")
    assert result.quality_score == 70.0  # 100 - (15 + 15)
    assert result.sensor_statuses["vibration"] == "MISSING"
    assert result.sensor_statuses["egt"] == "MISSING"
    assert len(result.penalties) == 2


def test_out_of_bounds_sensor_penalty():
    """Physical impossibility should be penalized with OUT_OF_BOUNDS."""
    telemetry = {
        "vibration": -5.0,  # Impossible negative vibration
        "egt": 1800.0,      # Exceeds max physical 1200°C
        "oil_pressure": 45.0,
        "oil_temperature": 95.0,
        "fuel_flow": 1150.0,
        "hydraulic_pressure": 3000.0,
        "battery_voltage": 28.0,
        "n1_rpm": 98.0,
        "n2_rpm": 95.0,
    }
    result = DataQualityEngine.evaluate_record(telemetry, aircraft_id="AF-TEST-03")
    assert result.quality_score == 60.0  # 100 - (20 + 20)
    assert result.sensor_statuses["vibration"] == "OUT_OF_BOUNDS"
    assert result.sensor_statuses["egt"] == "OUT_OF_BOUNDS"


def test_spike_detection():
    """A sudden jump between consecutive readings should be flagged as SPIKE."""
    prev_tick = {"vibration": 1.5, "egt": 650.0, "oil_pressure": 45.0, "oil_temperature": 95.0,
                 "fuel_flow": 1200.0, "hydraulic_pressure": 3000.0, "battery_voltage": 28.0, "n1_rpm": 98.0, "n2_rpm": 95.0}
    curr_tick = {"vibration": 8.0, "egt": 650.0, "oil_pressure": 45.0, "oil_temperature": 95.0,
                 "fuel_flow": 1200.0, "hydraulic_pressure": 3000.0, "battery_voltage": 28.0, "n1_rpm": 98.0, "n2_rpm": 95.0}

    result = DataQualityEngine.evaluate_record(curr_tick, aircraft_id="AF-TEST-04", recent_window=[prev_tick])
    assert result.sensor_statuses["vibration"] == "SPIKE"
    assert any(p.status == "SPIKE" for p in result.penalties)


def test_stuck_sensor_flatline_detection():
    """Flatlined sensor with zero variance over recent window should be flagged as STUCK_SENSOR."""
    history = [
        {"vibration": 2.15, "egt": 650.0, "oil_pressure": 45.0, "oil_temperature": 95.0,
         "fuel_flow": 1200.0, "hydraulic_pressure": 3000.0, "battery_voltage": 28.0, "n1_rpm": 98.0, "n2_rpm": 95.0}
        for _ in range(5)
    ]
    curr_tick = {"vibration": 2.15, "egt": 650.0, "oil_pressure": 45.0, "oil_temperature": 95.0,
                 "fuel_flow": 1200.0, "hydraulic_pressure": 3000.0, "battery_voltage": 28.0, "n1_rpm": 98.0, "n2_rpm": 95.0}

    result = DataQualityEngine.evaluate_record(curr_tick, aircraft_id="AF-TEST-05", recent_window=history)
    assert result.sensor_statuses["vibration"] == "STUCK_SENSOR"
    assert any(p.status == "STUCK_SENSOR" for p in result.penalties)


def test_component_health_nominal():
    """Nominal telemetry yields ~100 component health."""
    telemetry = {"vibration": 1.5, "egt": 650.0, "oil_pressure": 45.0, "oil_temperature": 95.0}
    comp = HealthIndexEngine.calculate_component_health(
        component_code="ENG-L",
        name="AL-31FP Turbofan (Left)",
        zone="ENGINES",
        telemetry=telemetry,
    )
    assert comp.health_score == 100.0
    assert comp.status == "OPERATIONAL"
    assert comp.degradation_percent == 0.0
    assert len(comp.primary_contributors) == 0


def test_component_health_degraded():
    """Severe sensor deviation reduces component health and populates primary contributors."""
    telemetry = {
        "vibration": 7.5,    # severe vibration (baseline max 2.5)
        "egt": 950.0,        # very high EGT (baseline max 720)
        "oil_pressure": 45.0,
        "oil_temperature": 130.0, # high oil temp
    }
    comp = HealthIndexEngine.calculate_component_health(
        component_code="ENG-L",
        name="AL-31FP Turbofan (Left)",
        zone="ENGINES",
        telemetry=telemetry,
    )
    assert comp.health_score < 70.0
    assert comp.degradation_percent > 30.0
    assert len(comp.primary_contributors) > 0
    assert any("vibration" in c for c in comp.primary_contributors)


def test_aircraft_health_aggregation_formula():
    """
    Validates formula: AHI = 0.40 * min(CHI) + 0.60 * weighted_avg(CHI).
    A single severely degraded component should pull down overall airworthiness.
    """
    comp1 = HealthIndexEngine.calculate_component_health("ENG-L", "Engine Left", "ENGINES", {"vibration": 1.5, "egt": 650.0, "oil_pressure": 45.0, "oil_temperature": 95.0})
    comp2 = HealthIndexEngine.calculate_component_health("ENG-R", "Engine Right", "ENGINES", {"vibration": 1.5, "egt": 650.0, "oil_pressure": 45.0, "oil_temperature": 95.0})
    # Heavily degraded hydraulic system
    comp3 = HealthIndexEngine.calculate_component_health("HYD-PRI", "Hydraulic Primary", "HYDRAULICS", {"hydraulic_pressure": 1200.0, "vibration": 5.0, "oil_temperature": 140.0})

    components = [comp1, comp2, comp3]
    result = HealthIndexEngine.calculate_aircraft_health(
        aircraft_id="AF-101",
        aircraft_type="Su-30MKI",
        tail_number="IAF-SU-101",
        components_health=components,
    )

    min_chi = min(c.health_score for c in components)
    assert min_chi < 60.0
    assert result.health_score < 85.0
    assert result.status in {"DEGRADED", "HIGH_RISK", "GROUNDED"}
    assert result.formula_breakdown["min_component"] == "HYD-PRI"
    assert "IAF-SU-101" in result.explanation
    assert "HYD-PRI" in result.explanation


@pytest.mark.asyncio
async def test_evaluate_aircraft_from_db():
    """Verify evaluation against seeded database aircraft and telemetry."""
    async with AsyncSessionLocal() as session:
        # AF-101 is one of our seeded aircraft
        result = await HealthIndexEngine.evaluate_aircraft_from_db(session, aircraft_id="AF-101", update_db=False)
        assert result is not None
        assert result.aircraft_id == "AF-101"
        assert result.aircraft_type == "Su-30MKI"
        assert 0.0 <= result.health_score <= 100.0
        assert len(result.components) >= 6
        assert result.status in {"READY", "DEGRADED", "HIGH_RISK", "GROUNDED"}
        assert len(result.explanation) > 10
