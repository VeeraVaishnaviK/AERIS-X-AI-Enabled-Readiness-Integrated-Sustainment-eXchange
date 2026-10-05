from datetime import datetime
from typing import Any, Dict, Optional
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Alert(Base, TimestampMixin):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    aircraft_id: Mapped[str] = mapped_column(ForeignKey("aircraft.id", ondelete="CASCADE"), index=True, nullable=False)
    component_id: Mapped[Optional[int]] = mapped_column(ForeignKey("aircraft_components.id", ondelete="SET NULL"), nullable=True, index=True)
    prediction_id: Mapped[Optional[int]] = mapped_column(ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True, index=True)

    severity: Mapped[str] = mapped_column(String(32), default="WARNING", index=True, nullable=False)  # CRITICAL, WARNING, INFO
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="OPEN", index=True, nullable=False)  # OPEN, ACKNOWLEDGED, ACTIONED, RESOLVED
    trigger_rule: Mapped[str] = mapped_column(String(128), default="PREDICTIVE_FAILURE_72H", nullable=False)
    evidence_summary: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    aircraft: Mapped["Aircraft"] = relationship("Aircraft", back_populates="alerts")
