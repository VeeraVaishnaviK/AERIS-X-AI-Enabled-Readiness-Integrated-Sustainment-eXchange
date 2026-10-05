"""
Pydantic schemas for Alerts and Alert Resolution Workflow.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AlertCreate(BaseModel):
    aircraft_id: str
    component_id: Optional[int] = None
    prediction_id: Optional[int] = None
    severity: str = "WARNING"  # CRITICAL, WARNING, INFO
    title: str
    message: str
    trigger_rule: str = "PREDICTIVE_FAILURE_72H"
    evidence_summary: Dict[str, Any] = Field(default_factory=dict)


class AlertUpdate(BaseModel):
    status: str = Field(..., description="OPEN, ACKNOWLEDGED, ACTIONED, RESOLVED, DISMISSED")
    resolution_notes: Optional[str] = None


class AlertResponse(BaseModel):
    id: int
    aircraft_id: str
    component_id: Optional[int] = None
    prediction_id: Optional[int] = None
    severity: str
    title: str
    message: str
    status: str
    trigger_rule: str
    evidence_summary: Dict[str, Any]
    created_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True
