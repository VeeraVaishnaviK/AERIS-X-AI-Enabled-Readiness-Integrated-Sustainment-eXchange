from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Telemetry(Base):
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    aircraft_id: Mapped[str] = mapped_column(ForeignKey("aircraft.id", ondelete="CASCADE"), index=True, nullable=False)
    component_id: Mapped[Optional[int]] = mapped_column(ForeignKey("aircraft_components.id", ondelete="SET NULL"), nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )

    # Core Physical Telemetry Sensors
    vibration: Mapped[float] = mapped_column(Float, default=1.2, nullable=False)  # mm/s RMS
    egt: Mapped[float] = mapped_column(Float, default=650.0, nullable=False)  # Exhaust Gas Temp °C
    oil_pressure: Mapped[float] = mapped_column(Float, default=45.0, nullable=False)  # psi
    oil_temperature: Mapped[float] = mapped_column(Float, default=95.0, nullable=False)  # °C
    fuel_flow: Mapped[float] = mapped_column(Float, default=1200.0, nullable=False)  # kg/h
    hydraulic_pressure: Mapped[float] = mapped_column(Float, default=3000.0, nullable=False)  # psi
    battery_voltage: Mapped[float] = mapped_column(Float, default=28.2, nullable=False)  # Volts
    n1_rpm: Mapped[float] = mapped_column(Float, default=98.5, nullable=False)  # % RPM
    n2_rpm: Mapped[float] = mapped_column(Float, default=95.0, nullable=False)  # % RPM

    # Diagnostic & Quality Annotations
    anomaly_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    quality_score: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    sensor_status: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    raw_payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_telemetry_aircraft_timestamp", "aircraft_id", "timestamp"),
        Index("ix_telemetry_timestamp_brin", "timestamp"),
    )
