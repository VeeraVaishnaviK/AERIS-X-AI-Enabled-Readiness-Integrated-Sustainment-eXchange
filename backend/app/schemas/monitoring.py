"""
Pydantic schemas for Model Monitoring and Outcome Evaluation.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class OutcomeRecordInput(BaseModel):
    prediction_id: int
    work_order_id: Optional[int] = None
    aircraft_id: str
    component_id: Optional[int] = None
    predicted_failure: bool
    predicted_probability: float
    predicted_rul_hours: float
    actual_failure_occurred: bool
    actual_failure_time: Optional[datetime] = None
    prediction_timestamp: datetime
    resolution_timestamp: datetime
    actual_lead_time_hours: float
    component_inspected_condition: str  # FAILED, HEAVILY_WORN, NOMINAL_FALSE_ALARM
    model_version: str = "v1.0.0-xgb"


class ModelEvaluationMetrics(BaseModel):
    model_name: str
    model_version: str
    sample_count: int
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float
    false_positive_rate: float
    false_negative_rate: float
    rul_mae_hours: float
    rul_rmse_hours: float
    mean_lead_time_hours: float
    evaluation_notes: Dict[str, Any] = Field(default_factory=dict)
