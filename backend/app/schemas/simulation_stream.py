"""
Pydantic schemas for Telemetry Simulator and Realtime Streaming Arc.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ArcStage(str, Enum):
    NORMAL = "NORMAL"
    DEGRADATION = "DEGRADATION"
    ANOMALY = "ANOMALY"
    HIGH_RISK = "HIGH_RISK"
    MAINTENANCE = "MAINTENANCE"
    RECOVERY = "RECOVERY"


class TelemetryTick(BaseModel):
    tick_number: int
    timestamp: datetime
    aircraft_id: str
    stage: ArcStage
    sensors: Dict[str, float]
    health_score: float
    failure_probability: float
    rul_hours: float
    risk_level: str
    active_alert: Optional[Dict[str, Any]] = None


class LiveSimulationStartRequest(BaseModel):
    aircraft_id: str = "IAF-TS-01"
    tick_interval_ms: int = 500
    total_ticks: int = 60
    scenario_arc: str = "FULL_LIFECYCLE"
