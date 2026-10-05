"""
Pydantic schemas for Phase 5 — Data Quality & Health Index Engine.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SensorQualityDetail(BaseModel):
    sensor_name: str
    value: Optional[float]
    status: str = Field(..., description="NOMINAL, OUT_OF_BOUNDS, STUCK_SENSOR, SPIKE, DRIFT, MISSING")
    penalty: float = Field(0.0, description="Deduction from 100")
    details: str = Field("", description="Human-readable reason for penalty")


class DataQualityResult(BaseModel):
    aircraft_id: str
    quality_score: float = Field(..., ge=0.0, le=100.0, description="Overall telemetry quality score 0-100")
    is_valid: bool = Field(..., description="Whether telemetry is reliable for downstream ML inference")
    penalties: List[SensorQualityDetail] = Field(default_factory=list)
    sensor_statuses: Dict[str, str] = Field(default_factory=dict)
    confidence: float = Field(..., ge=0.0, le=1.0, description="Quality confidence metric")


class ComponentHealthBreakdown(BaseModel):
    component_id: Optional[int] = None
    component_code: str
    name: str
    zone: str
    health_score: float = Field(..., ge=0.0, le=100.0)
    degradation_percent: float = Field(..., ge=0.0, le=100.0)
    status: str
    primary_contributors: List[str] = Field(default_factory=list)


class AircraftHealthResult(BaseModel):
    aircraft_id: str
    aircraft_type: str
    tail_number: str
    health_score: float = Field(..., ge=0.0, le=100.0, description="Aggregated Aircraft Health Index (AHI)")
    status: str = Field(..., description="READY, DEGRADED, HIGH_RISK, GROUNDED")
    risk_level: str = Field(..., description="LOW, MEDIUM, HIGH, CRITICAL")
    min_component_health: float
    avg_component_health: float
    components: List[ComponentHealthBreakdown] = Field(default_factory=list)
    explanation: str = Field(..., description="Plain-English audit explanation of the health score calculation")
    formula_breakdown: Dict[str, Any] = Field(default_factory=dict)
