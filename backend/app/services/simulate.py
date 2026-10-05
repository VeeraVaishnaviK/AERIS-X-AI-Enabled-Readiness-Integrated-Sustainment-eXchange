"""
AERIS-X What-If Maintenance Simulation Engine
Allows commanders and maintenance planners to simulate scenarios and stress-test resource parameters:
- Scenarios: MAINTAIN_NOW, MAINTAIN_TOMORROW, DEFER_MAINTENANCE, REASSIGN_TECHNICIAN, ALTERNATE_SPARE_LOCATION
- Sliders: delay_hours, technician_availability_pct, spare_availability_pct, bay_capacity_multiplier
"""
from typing import Any, Dict, List
import math
from app.schemas.optimization import (
    MaintenanceTaskInput,
    SimulationScenario,
    SimulationRequest,
    SimulationResult,
)


def run_maintenance_simulation(
    request: SimulationRequest,
    tasks: List[MaintenanceTaskInput],
    fleet_size: int = 30,
) -> SimulationResult:
    """
    Simulate what-if maintenance outcomes based on scenario and resource sliders.
    """
    total_tasks = len(tasks)
    critical_count = sum(1 for t in tasks if t.risk_level.upper() == "CRITICAL")
    high_count = sum(1 for t in tasks if t.risk_level.upper() == "HIGH")
    medium_count = sum(1 for t in tasks if t.risk_level.upper() == "MEDIUM")
    low_count = sum(1 for t in tasks if t.risk_level.upper() in ["LOW", "ROUTINE"])

    base_downtime = sum(t.duration_hours for t in tasks)

    # Apply sliders:
    # 1. Tech capacity factor: < 100% slows down maintenance or creates backlog
    tech_factor = max(0.2, request.technician_availability_pct / 100.0)
    # 2. Spare factor: < 100% starves parts and causes groundings
    spare_factor = max(0.2, request.spare_availability_pct / 100.0)
    # 3. Bay capacity multiplier:
    bay_factor = max(0.2, request.bay_capacity_multiplier)
    # 4. Delay hours:
    delay = request.delay_hours

    # Scenario-specific modifiers
    scenario = request.scenario
    scenario_delay = delay
    risk_multiplier = 1.0
    backlog_multiplier = 1.0

    if scenario == SimulationScenario.MAINTAIN_NOW:
        scenario_delay = 0.0
        risk_multiplier = 0.4
        resolved_pct = 0.95

    elif scenario == SimulationScenario.MAINTAIN_TOMORROW:
        scenario_delay = max(24.0, delay)
        risk_multiplier = 1.3
        resolved_pct = 0.85

    elif scenario == SimulationScenario.DEFER_MAINTENANCE:
        scenario_delay = max(72.0, delay)
        risk_multiplier = 2.2
        # Critical still maintained, medium/low deferred
        resolved_pct = 0.50
        backlog_multiplier = 1.8

    elif scenario == SimulationScenario.REASSIGN_TECHNICIAN:
        scenario_delay = max(0.0, delay * 0.7)
        risk_multiplier = 0.6
        tech_factor = tech_factor * 1.3
        resolved_pct = 0.90

    elif scenario == SimulationScenario.ALTERNATE_SPARE_LOCATION:
        scenario_delay = max(12.0, delay)
        spare_factor = max(1.0, spare_factor * 1.5)
        risk_multiplier = 0.7
        resolved_pct = 0.92
    else:
        resolved_pct = 0.80

    # Effective throughput governed by bottleneck of (tech, bay, spare)
    effective_capacity = min(tech_factor, bay_factor, spare_factor)

    # Workload hours
    effective_workload = (base_downtime / effective_capacity) * (1.0 + (scenario_delay * 0.005))

    # Calculate backlog and groundings
    # Parts starvation or tech shortage causes backlog
    unresolved_ratio = max(0.05, 1.0 - (resolved_pct * min(1.0, effective_capacity)))
    backlog_count = int(math.ceil(total_tasks * unresolved_ratio * backlog_multiplier))

    # Delay penalty on risk and groundings
    # If delay exceeds critical RUL (approx 24h), aircraft are grounded
    delay_groundings = 0
    if scenario_delay > 12.0:
        delay_groundings += int(math.ceil(critical_count * min(1.0, (scenario_delay - 12.0) / 24.0)))
    if scenario_delay > 48.0:
        delay_groundings += int(math.ceil(high_count * min(0.6, (scenario_delay - 48.0) / 48.0)))

    # Spare shortage groundings
    spare_groundings = 0
    if spare_factor < 0.8:
        spare_groundings = int(math.ceil((critical_count + high_count) * (0.8 - spare_factor)))

    total_grounded = min(fleet_size, delay_groundings + spare_groundings)

    # Projected availability calculation
    # Availability = (Fleet - Grounded - (Backlog in bay * 0.5)) / Fleet
    unavailable = total_grounded + (backlog_count * 0.35)
    projected_avail = max(
        30.0,
        min(98.5, round(((fleet_size - unavailable) / fleet_size) * 100.0, 1)),
    )

    # Risk Exposure Index (0 - 100 scale)
    base_risk = (critical_count * 25.0) + (high_count * 15.0) + (medium_count * 5.0)
    delay_risk_adder = scenario_delay * 0.6
    resource_risk_adder = max(0.0, (1.0 - effective_capacity) * 30.0)
    risk_exposure = min(
        100.0,
        max(5.0, round((base_risk * risk_multiplier * 0.2) + delay_risk_adder + resource_risk_adder, 1)),
    )

    comparison = {
        "baseline_availability_pct": 78.5,
        "delta_availability_pct": round(projected_avail - 78.5, 1),
        "total_tasks_evaluated": total_tasks,
        "capacity_utilization_pct": round(min(100.0, (base_downtime / max(1.0, effective_workload)) * 100.0), 1),
        "spare_sufficiency_pct": round(spare_factor * 100.0, 1),
        "primary_bottleneck": (
            "SPARE_PARTS" if spare_factor < min(tech_factor, bay_factor)
            else ("TECHNICIANS" if tech_factor < bay_factor else "BAY_CAPACITY")
        ),
    }

    return SimulationResult(
        scenario=str(scenario.value if hasattr(scenario, "value") else scenario),
        projected_availability=projected_avail,
        projected_downtime_hours=round(effective_workload, 1),
        risk_exposure_index=risk_exposure,
        maintenance_workload_hours=round(effective_workload, 1),
        backlog_count=backlog_count,
        grounded_count=total_grounded,
        comparison_to_baseline=comparison,
    )
