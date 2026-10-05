"""
Pydantic schemas for Phase 7:
Recommendations, Feasibility, OR-Tools Optimization, Reactive Baseline, and Simulation.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ActionType(str, Enum):
    MONITOR = "MONITOR"
    INSPECT = "INSPECT"
    CALIBRATE = "CALIBRATE"
    OVERHAUL = "OVERHAUL"
    REPLACE = "REPLACE"
    GROUND = "GROUND"


class UrgencyLevel(str, Enum):
    ROUTINE = "ROUTINE"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FeasibilityStatus(str, Enum):
    FEASIBLE = "FEASIBLE"
    PARTIALLY_FEASIBLE = "PARTIALLY_FEASIBLE"
    NOT_FEASIBLE = "NOT_FEASIBLE"


class RecommendationResult(BaseModel):
    action: ActionType
    urgency: UrgencyLevel
    duration_hours: float = Field(..., description="Estimated maintenance duration in hours")
    required_spare_category: str = Field(..., description="Category of spare part required")
    required_spare_name: Optional[str] = None
    recommended_window_hours: float = Field(..., description="Max window to perform maintenance before failure risk spikes")
    rationale: str = Field(..., description="Human-readable aerospace maintenance rationale")


class FeasibilityCheckResult(BaseModel):
    status: FeasibilityStatus
    is_feasible: bool
    spare_feasible: bool
    spare_details: Dict[str, Any]
    technician_feasible: bool
    technician_details: Dict[str, Any]
    bay_feasible: bool
    bay_details: Dict[str, Any]
    window_feasible: bool
    bottlenecks: List[str]
    recommendation: str


class MaintenanceTaskInput(BaseModel):
    task_id: str
    aircraft_id: str
    component_id: Optional[int] = None
    component_name: str = "Component"
    component_category: str = "Propulsion"
    failure_probability: float = 0.0
    rul_hours: float = 500.0
    risk_level: str = "LOW"
    action_type: ActionType = ActionType.INSPECT
    duration_hours: float = 4.0
    deadline_hours: float = 72.0
    required_skill: str = "Propulsion"
    required_bay_type: str = "QUICK_TURNAROUND"
    required_spare_id: Optional[int] = None
    required_spare_part_number: Optional[str] = None
    required_spare_quantity: int = 1


class ScheduleSlot(BaseModel):
    task_id: str
    aircraft_id: str
    action_type: str
    technician_id: int
    technician_name: str
    bay_id: int
    bay_code: str
    spare_id: Optional[int] = None
    spare_part_number: Optional[str] = None
    start_hour: float
    end_hour: float
    scheduled_start: datetime
    scheduled_end: datetime


class OptimizationResult(BaseModel):
    status: str
    schedule: List[ScheduleSlot]
    unassigned_tasks: List[Dict[str, Any]]
    availability_before: float
    availability_after: float
    availability_uplift: float
    total_downtime_hours: float
    conflicts_avoided: int
    solver_time_seconds: float


class ReactiveComparisonResult(BaseModel):
    reactive_availability: float
    optimized_availability: float
    reactive_downtime_hours: float
    optimized_downtime_hours: float
    unpredicted_groundings_avoided: int
    downtime_reduction_pct: float
    cost_savings_estimate_inr: float
    summary: str


class SimulationScenario(str, Enum):
    MAINTAIN_NOW = "MAINTAIN_NOW"
    MAINTAIN_TOMORROW = "MAINTAIN_TOMORROW"
    DEFER_MAINTENANCE = "DEFER_MAINTENANCE"
    REASSIGN_TECHNICIAN = "REASSIGN_TECHNICIAN"
    ALTERNATE_SPARE_LOCATION = "ALTERNATE_SPARE_LOCATION"


class SimulationRequest(BaseModel):
    scenario: SimulationScenario = SimulationScenario.MAINTAIN_NOW
    delay_hours: float = Field(0.0, ge=0.0, le=168.0, description="Maintenance delay in hours")
    technician_availability_pct: float = Field(100.0, ge=20.0, le=200.0, description="Tech capacity %")
    spare_availability_pct: float = Field(100.0, ge=20.0, le=200.0, description="Spare inventory %")
    bay_capacity_multiplier: float = Field(1.0, ge=0.2, le=2.0, description="Bay capacity factor")
    horizon_days: int = Field(7, ge=1, le=30)


class SimulationResult(BaseModel):
    scenario: str
    projected_availability: float
    projected_downtime_hours: float
    risk_exposure_index: float
    maintenance_workload_hours: float
    backlog_count: int
    grounded_count: int
    comparison_to_baseline: Dict[str, Any]
