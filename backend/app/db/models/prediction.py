from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Prediction(Base, TimestampMixin):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    aircraft_id: Mapped[str] = mapped_column(ForeignKey("aircraft.id", ondelete="CASCADE"), index=True, nullable=False)
    component_id: Mapped[Optional[int]] = mapped_column(ForeignKey("aircraft_components.id", ondelete="SET NULL"), nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )

    # ML Inference Results
    failure_probability_72h: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # XGBoost
    baseline_probability: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # Logistic Regression
    rul_hours: Mapped[float] = mapped_column(Float, default=500.0, nullable=False)  # Predicted Remaining Useful Life
    rul_lower_bound: Mapped[float] = mapped_column(Float, default=450.0, nullable=False)
    rul_upper_bound: Mapped[float] = mapped_column(Float, default=550.0, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), default="LOW", index=True, nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    recommended_action: Mapped[str] = mapped_column(String(255), default="MONITOR_NORMAL", nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), default="v1.0.0-xgb", nullable=False)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    aircraft: Mapped["Aircraft"] = relationship("Aircraft", back_populates="predictions")
    evidence: Mapped[List["PredictionEvidence"]] = relationship(
        "PredictionEvidence", back_populates="prediction", cascade="all, delete-orphan", lazy="selectin"
    )


class PredictionEvidence(Base):
    __tablename__ = "prediction_evidence"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id", ondelete="CASCADE"), index=True, nullable=False)
    feature: Mapped[str] = mapped_column(String(64), nullable=False)
    contribution: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # Percentage / relative weight
    direction: Mapped[str] = mapped_column(String(32), default="INCREASING_RISK", nullable=False)  # INCREASING_RISK, DECREASING_RISK
    shap_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., "Vibration trend +31%"
    importance_rank: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Relationship
    prediction: Mapped["Prediction"] = relationship("Prediction", back_populates="evidence")
