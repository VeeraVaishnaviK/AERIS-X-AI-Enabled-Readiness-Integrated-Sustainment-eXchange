"""
Tests for Phase 7 — Recommendation, Feasibility, Optimization, and Simulation
Validates:
- Prescriptive recommendation rules across risk and RUL tiers
- Feasibility checks (spares, qualified technician, bay availability, window)
- OR-Tools CP-SAT scheduler with hard constraints (no double-booking, skills, bays)
- PROOF: availability(after) >= availability(before)
- Reactive baseline comparison generation
- What-if simulation engine across scenarios and sliders
- Fleet readiness engine and 7-day forecast
"""
import pytest
from datetime import datetime, timezone

from app.schemas.optimization import (
    ActionType,
    UrgencyLevel,
    FeasibilityStatus,
    MaintenanceTaskInput,
    SimulationScenario,
    SimulationRequest,
)
from app.services.recommend import generate_recommendation, get_recommended_spare
from app.services.feasibility import evaluate_feasibility_in_memory
from app.services.optimize import MaintenanceOptimizer
from app.services.reactive_baseline import simulate_reactive_baseline
from app.services.simulate import run_maintenance_simulation
from app.services.readiness import compute_fleet_readiness


# ---------------------------------------------------------
# 1. Recommendation Rules Tests
# ---------------------------------------------------------

def test_recommendation_critical_risk():
    """CRITICAL risk or near-zero RUL must mandate GROUND or priority REPLACE."""
    rec = generate_recommendation(
        failure_probability=0.92,
        risk_level="CRITICAL",
        rul_hours=10.0,
        component_category="Propulsion",
        component_name="Engine Core Turbine",
    )
    assert rec.action == ActionType.GROUND
    assert rec.urgency == UrgencyLevel.CRITICAL
    assert rec.recommended_window_hours <= 12.0
    assert "Turbine Blade Set" in (rec.required_spare_name or "")
    assert "grounding mandated" in rec.rationale.lower()


def test_recommendation_high_risk():
    """HIGH risk within 72h window triggers component REPLACE."""
    rec = generate_recommendation(
        failure_probability=0.74,
        risk_level="HIGH",
        rul_hours=48.0,
        component_category="Hydraulics",
        component_name="Main Hydraulic Actuator",
    )
    assert rec.action == ActionType.REPLACE
    assert rec.urgency == UrgencyLevel.HIGH
    assert rec.recommended_window_hours <= 48.0
    assert rec.duration_hours > 0


def test_recommendation_sensor_calibration():
    """Sensor anomalies trigger CALIBRATE instead of full hardware replacement."""
    rec = generate_recommendation(
        failure_probability=0.68,
        risk_level="HIGH",
        rul_hours=55.0,
        component_category="Avionics",
        component_name="Pitot-Static Tube Assembly",
        is_sensor=True,
    )
    assert rec.action == ActionType.CALIBRATE
    assert rec.urgency == UrgencyLevel.HIGH
    assert "calibration" in rec.rationale.lower()


def test_recommendation_medium_and_low():
    """MEDIUM triggers INSPECT; LOW triggers MONITOR."""
    rec_med = generate_recommendation(
        failure_probability=0.45,
        risk_level="MEDIUM",
        rul_hours=120.0,
        component_category="Airframe",
        component_name="Flap Actuator Bushing",
    )
    assert rec_med.action == ActionType.INSPECT
    assert rec_med.urgency == UrgencyLevel.MEDIUM

    rec_low = generate_recommendation(
        failure_probability=0.08,
        risk_level="LOW",
        rul_hours=600.0,
        component_category="Propulsion",
        component_name="Turbine Blade Set",
    )
    assert rec_low.action == ActionType.MONITOR
    assert rec_low.urgency == UrgencyLevel.ROUTINE


# ---------------------------------------------------------
# 2. Feasibility Checks Tests
# ---------------------------------------------------------

def test_feasibility_all_resources_available():
    """When spares, techs, and bays exist, action is FEASIBLE."""
    spares = [{"id": 1, "name": "Turbine Blade Set", "category": "Propulsion", "stock_quantity": 5, "lead_time_days": 14}]
    techs = [{"id": 1, "name": "MWO Ramesh Sharma", "specialty": "Propulsion", "current_status": "AVAILABLE"}]
    bays = [{"id": 1, "bay_code": "BAY-01", "bay_type": "HEAVY_MAINTENANCE", "is_operational": True, "current_status": "AVAILABLE"}]

    res = evaluate_feasibility_in_memory(
        required_spare_category="Propulsion",
        required_spare_name="Turbine Blade Set",
        required_duration_hours=6.0,
        window_hours=48.0,
        available_spares=spares,
        available_technicians=techs,
        available_bays=bays,
    )
    assert res.status == FeasibilityStatus.FEASIBLE
    assert res.is_feasible is True
    assert res.spare_feasible is True
    assert res.technician_feasible is True
    assert res.bay_feasible is True
    assert len(res.bottlenecks) == 0


def test_feasibility_spare_stockout_bottleneck():
    """When spare is out of stock and lead time exceeds window, status is PARTIALLY or NOT_FEASIBLE."""
    spares = [{"id": 1, "name": "Turbine Blade Set", "category": "Propulsion", "stock_quantity": 0, "lead_time_days": 14}]
    techs = [{"id": 1, "name": "MWO Ramesh Sharma", "specialty": "Propulsion", "current_status": "AVAILABLE"}]
    bays = [{"id": 1, "bay_code": "BAY-01", "bay_type": "HEAVY_MAINTENANCE", "is_operational": True, "current_status": "AVAILABLE"}]

    res = evaluate_feasibility_in_memory(
        required_spare_category="Propulsion",
        required_spare_name="Turbine Blade Set",
        required_duration_hours=6.0,
        window_hours=24.0,
        available_spares=spares,
        available_technicians=techs,
        available_bays=bays,
    )
    assert res.spare_feasible is False
    assert any("out of stock" in b.lower() for b in res.bottlenecks)


def test_feasibility_all_bays_occupied():
    """When all bays are occupied, action is constrained."""
    spares = [{"id": 1, "name": "Turbine Blade Set", "category": "Propulsion", "stock_quantity": 4, "lead_time_days": 14}]
    techs = [{"id": 1, "name": "MWO Ramesh Sharma", "specialty": "Propulsion", "current_status": "AVAILABLE"}]
    bays = [{"id": 1, "bay_code": "BAY-01", "bay_type": "HEAVY_MAINTENANCE", "is_operational": True, "current_status": "OCCUPIED"}]

    res = evaluate_feasibility_in_memory(
        required_spare_category="Propulsion",
        required_spare_name="Turbine Blade Set",
        required_duration_hours=4.0,
        window_hours=48.0,
        available_spares=spares,
        available_technicians=techs,
        available_bays=bays,
    )
    assert res.bay_feasible is False
    assert res.status != FeasibilityStatus.FEASIBLE


# ---------------------------------------------------------
# 3. OR-Tools CP-SAT Optimizer Tests & Availability Proof
# ---------------------------------------------------------

def test_optimizer_proves_availability_uplift():
    """
    MANDATORY GATE:
    Optimizer must prove availability(after) >= availability(before).
    """
    optimizer = MaintenanceOptimizer(horizon_hours=72, total_fleet_size=30)

    # 4 degraded aircraft needing maintenance
    tasks = [
        MaintenanceTaskInput(
            task_id="TASK-01",
            aircraft_id="AC-01",
            component_category="Propulsion",
            failure_probability=0.88,
            rul_hours=22.0,
            risk_level="CRITICAL",
            action_type=ActionType.REPLACE,
            duration_hours=6.0,
            deadline_hours=24.0,
            required_skill="Propulsion",
        ),
        MaintenanceTaskInput(
            task_id="TASK-02",
            aircraft_id="AC-02",
            component_category="Avionics",
            failure_probability=0.72,
            rul_hours=45.0,
            risk_level="HIGH",
            action_type=ActionType.REPLACE,
            duration_hours=4.0,
            deadline_hours=48.0,
            required_skill="Avionics",
        ),
        MaintenanceTaskInput(
            task_id="TASK-03",
            aircraft_id="AC-03",
            component_category="Hydraulics",
            failure_probability=0.65,
            rul_hours=55.0,
            risk_level="HIGH",
            action_type=ActionType.REPLACE,
            duration_hours=5.0,
            deadline_hours=60.0,
            required_skill="Hydraulics",
        ),
        MaintenanceTaskInput(
            task_id="TASK-04",
            aircraft_id="AC-04",
            component_category="Propulsion",
            failure_probability=0.45,
            rul_hours=80.0,
            risk_level="MEDIUM",
            action_type=ActionType.INSPECT,
            duration_hours=3.0,
            deadline_hours=72.0,
            required_skill="Propulsion",
        ),
    ]

    # Technicians
    technicians = [
        {"id": 1, "name": "MWO Ramesh Sharma", "specialty": "Propulsion", "current_status": "AVAILABLE"},
        {"id": 2, "name": "WO Priya Nair", "specialty": "Avionics", "current_status": "AVAILABLE"},
        {"id": 3, "name": "JWO Vikram Singh", "specialty": "Hydraulics", "current_status": "AVAILABLE"},
    ]

    # Maintenance bays
    bays = [
        {"id": 1, "bay_code": "BAY-01", "bay_type": "HEAVY_MAINTENANCE", "is_operational": True, "current_status": "AVAILABLE"},
        {"id": 2, "bay_code": "BAY-02", "bay_type": "QUICK_TURNAROUND", "is_operational": True, "current_status": "AVAILABLE"},
    ]

    result = optimizer.solve(tasks=tasks, technicians=technicians, bays=bays)

    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert len(result.schedule) > 0

    # MANDATORY GATE ASSERTION:
    assert result.availability_after >= result.availability_before, (
        f"Gate Failure: availability_after ({result.availability_after}%) "
        f"must be >= availability_before ({result.availability_before}%)"
    )
    assert result.availability_uplift >= 0.0

    # Verify no technician double-booking in scheduled slots
    for i, s1 in enumerate(result.schedule):
        for j, s2 in enumerate(result.schedule):
            if i != j and s1.technician_id == s2.technician_id:
                # Must not overlap
                assert (s1.end_hour <= s2.start_hour) or (s2.end_hour <= s1.start_hour), (
                    f"Technician {s1.technician_id} double-booked between {s1.task_id} and {s2.task_id}"
                )

    # Verify no bay double-booking in scheduled slots
    for i, s1 in enumerate(result.schedule):
        for j, s2 in enumerate(result.schedule):
            if i != j and s1.bay_id == s2.bay_id:
                # Must not overlap
                assert (s1.end_hour <= s2.start_hour) or (s2.end_hour <= s1.start_hour), (
                    f"Bay {s1.bay_id} double-booked between {s1.task_id} and {s2.task_id}"
                )


def test_optimizer_respects_solver_time_limit():
    """Optimizer solver completes within the 10-second limit."""
    optimizer = MaintenanceOptimizer(horizon_hours=72, time_limit_seconds=5.0)
    tasks = [
        MaintenanceTaskInput(
            task_id=f"TASK-{i:02d}",
            aircraft_id=f"AC-{i:02d}",
            component_category="Propulsion",
            failure_probability=0.70,
            rul_hours=36.0,
            risk_level="HIGH",
            action_type=ActionType.REPLACE,
            duration_hours=4.0,
            deadline_hours=72.0,
            required_skill="Propulsion",
        )
        for i in range(1, 10)
    ]
    techs = [
        {"id": 1, "name": "Tech 1", "specialty": "Propulsion", "current_status": "AVAILABLE"},
        {"id": 2, "name": "Tech 2", "specialty": "Propulsion", "current_status": "AVAILABLE"},
    ]
    bays = [
        {"id": 1, "bay_code": "BAY-01", "is_operational": True, "current_status": "AVAILABLE"},
        {"id": 2, "bay_code": "BAY-02", "is_operational": True, "current_status": "AVAILABLE"},
    ]

    res = optimizer.solve(tasks=tasks, technicians=techs, bays=bays)
    assert res.solver_time_seconds <= 10.0


# ---------------------------------------------------------
# 4. Reactive Baseline Tests
# ---------------------------------------------------------

def test_reactive_baseline_generates_comparison():
    """
    MANDATORY GATE:
    Reactive baseline comparison is generated with availability uplift and avoided groundings.
    """
    optimizer = MaintenanceOptimizer(horizon_hours=72, total_fleet_size=30)
    tasks = [
        MaintenanceTaskInput(
            task_id="TASK-01",
            aircraft_id="AC-01",
            component_category="Propulsion",
            failure_probability=0.90,
            rul_hours=18.0,
            risk_level="CRITICAL",
            action_type=ActionType.REPLACE,
            duration_hours=6.0,
            deadline_hours=24.0,
            required_skill="Propulsion",
        ),
        MaintenanceTaskInput(
            task_id="TASK-02",
            aircraft_id="AC-02",
            component_category="Avionics",
            failure_probability=0.75,
            rul_hours=40.0,
            risk_level="HIGH",
            action_type=ActionType.REPLACE,
            duration_hours=5.0,
            deadline_hours=48.0,
            required_skill="Avionics",
        ),
    ]
    techs = [{"id": 1, "name": "Tech A", "specialty": "Propulsion", "current_status": "AVAILABLE"}]
    bays = [{"id": 1, "bay_code": "BAY-01", "is_operational": True, "current_status": "AVAILABLE"}]

    opt_result = optimizer.solve(tasks=tasks, technicians=techs, bays=bays)
    comp = simulate_reactive_baseline(tasks=tasks, optimized_result=opt_result, fleet_size=30)

    assert comp.optimized_availability >= comp.reactive_availability
    assert comp.unpredicted_groundings_avoided >= 1
    assert comp.reactive_downtime_hours >= comp.optimized_downtime_hours
    assert comp.cost_savings_estimate_inr > 0
    assert "AERIS-X predictive optimization" in comp.summary


# ---------------------------------------------------------
# 5. What-If Simulation Tests
# ---------------------------------------------------------

def test_what_if_simulation_scenarios_and_sliders():
    """Validates what-if simulation scenarios and interactive sliders."""
    tasks = [
        MaintenanceTaskInput(
            task_id="TASK-01",
            aircraft_id="AC-01",
            component_category="Propulsion",
            failure_probability=0.85,
            rul_hours=20.0,
            risk_level="CRITICAL",
            action_type=ActionType.REPLACE,
            duration_hours=6.0,
            deadline_hours=24.0,
            required_skill="Propulsion",
        ),
        MaintenanceTaskInput(
            task_id="TASK-02",
            aircraft_id="AC-02",
            component_category="Hydraulics",
            failure_probability=0.65,
            rul_hours=60.0,
            risk_level="HIGH",
            action_type=ActionType.REPLACE,
            duration_hours=4.0,
            deadline_hours=72.0,
            required_skill="Hydraulics",
        ),
    ]

    # Scenario 1: MAINTAIN_NOW
    req_now = SimulationRequest(scenario=SimulationScenario.MAINTAIN_NOW, delay_hours=0.0)
    res_now = run_maintenance_simulation(req_now, tasks, fleet_size=30)
    assert res_now.scenario == "MAINTAIN_NOW"
    assert res_now.projected_availability >= 85.0
    assert res_now.risk_exposure_index < 50.0

    # Scenario 2: DEFER_MAINTENANCE with high delay
    req_defer = SimulationRequest(
        scenario=SimulationScenario.DEFER_MAINTENANCE,
        delay_hours=72.0,
        spare_availability_pct=60.0,
    )
    res_defer = run_maintenance_simulation(req_defer, tasks, fleet_size=30)
    # Deferring increases risk exposure
    assert res_defer.risk_exposure_index > res_now.risk_exposure_index
    assert res_defer.backlog_count >= 1


# ---------------------------------------------------------
# 6. Fleet Readiness Engine Tests
# ---------------------------------------------------------

def test_fleet_readiness_calculation_and_forecast():
    """Validates readiness percentages, trend, and 7-day daily forecast."""
    fleet = [
        {"id": f"AC-{i:02d}", "tail_number": f"IAF-TS-{i:02d}", "aircraft_type": "HAL Tejas Mk1A", "squadron": "No. 45 Flying Daggers", "current_status": "OPERATIONAL", "has_high_risk": False}
        for i in range(1, 25)
    ]
    # Add some in maintenance and high risk
    fleet.append({"id": "AC-25", "tail_number": "IAF-TS-25", "aircraft_type": "HAL Tejas Mk1A", "squadron": "No. 45 Flying Daggers", "current_status": "MAINTENANCE", "has_high_risk": False})
    fleet.append({"id": "AC-26", "tail_number": "IAF-TS-26", "aircraft_type": "HAL Tejas Mk1A", "squadron": "No. 45 Flying Daggers", "current_status": "GROUNDED", "has_high_risk": False})
    fleet.append({"id": "AC-27", "tail_number": "IAF-TS-27", "aircraft_type": "Su-30MKI", "squadron": "No. 222 Tigersharks", "current_status": "OPERATIONAL", "has_high_risk": True})
    fleet.append({"id": "AC-28", "tail_number": "IAF-TS-28", "aircraft_type": "Su-30MKI", "squadron": "No. 222 Tigersharks", "current_status": "OPERATIONAL", "has_high_risk": False})
    fleet.append({"id": "AC-29", "tail_number": "IAF-TS-29", "aircraft_type": "Rafale", "squadron": "No. 101 Falcons", "current_status": "OPERATIONAL", "has_high_risk": False})
    fleet.append({"id": "AC-30", "tail_number": "IAF-TS-30", "aircraft_type": "Rafale", "squadron": "No. 101 Falcons", "current_status": "OPERATIONAL", "has_high_risk": False})

    overview = compute_fleet_readiness(aircraft_records=fleet)

    assert overview.total_aircraft == 30
    assert overview.operational_count >= 27
    assert overview.grounded_count == 1
    assert overview.maintenance_count == 1
    assert overview.high_risk_count == 1
    assert 85.0 <= overview.availability_percentage <= 98.0
    assert overview.trend in ("IMPROVING", "STABLE", "DEGRADING")

    # 7-day forecast assertions
    assert len(overview.seven_day_forecast) == 7
    for df in overview.seven_day_forecast:
        assert 1 <= df.day_offset <= 7
        assert 50.0 <= df.predicted_availability_pct <= 100.0
        assert len(df.confidence_interval) == 2
        assert df.confidence_interval[0] <= df.confidence_interval[1]

    # Squadron breakdown
    assert "No. 45 Flying Daggers" in overview.squadron_breakdown
    assert "No. 222 Tigersharks" in overview.squadron_breakdown
    assert "No. 101 Falcons" in overview.squadron_breakdown

    # Aircraft type breakdown
    assert "HAL Tejas Mk1A" in overview.aircraft_type_breakdown
    assert "Su-30MKI" in overview.aircraft_type_breakdown
    assert "Rafale" in overview.aircraft_type_breakdown
