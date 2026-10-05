"""
Pydantic schemas for Fleet Readiness and Forecasts.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DailyForecast(BaseModel):
    day_offset: int
    date: str
    predicted_availability_pct: float
    predicted_ready_count: int
    predicted_maintenance_count: int
    predicted_risk_count: int
    confidence_interval: List[float] = Field(default_factory=list)


class SquadronReadiness(BaseModel):
    squadron_name: str
    total_aircraft: int
    operational: int
    in_maintenance: int
    high_risk: int
    grounded: int
    availability_pct: float
    fmc_pct: float


class TypeReadiness(BaseModel):
    aircraft_type: str
    total_aircraft: int
    operational: int
    in_maintenance: int
    high_risk: int
    grounded: int
    availability_pct: float


class FleetReadinessOverview(BaseModel):
    total_aircraft: int
    operational_count: int
    maintenance_count: int
    high_risk_count: int
    grounded_count: int
    availability_percentage: float
    mission_capable_percentage: float
    trend: str  # IMPROVING, STABLE, DEGRADING
    backlog_count: int
    predicted_downtime_7d_hours: float
    seven_day_forecast: List[DailyForecast]
    squadron_breakdown: Dict[str, SquadronReadiness]
    aircraft_type_breakdown: Dict[str, TypeReadiness]
