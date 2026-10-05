from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(64), default="system", index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="SYSTEM", nullable=False)
    action: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # LOGIN, PREDICTION_RUN, SCHEDULE_OPTIMIZE, WO_APPROVE, WO_MODIFY, WO_REJECT, SIMULATION_TRIGGER
    resource_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # aircraft, work_order, schedule, model, user
    resource_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    previous_value: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    new_value: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), default="127.0.0.1", nullable=False)
    user_agent: Mapped[str] = mapped_column(String(255), default="AERIS-X Core Client", nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )
