from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Aircraft(Base, TimestampMixin):
    __tablename__ = "aircraft"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, index=True)  # e.g., 'AF-204'
    tail_number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    aircraft_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # 'Su-30MKI', 'Rafale', 'Tejas Mk1A'
    squadron: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    base_location: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="READY", index=True, nullable=False)  # READY, MAINTENANCE, HIGH_RISK, GROUNDED
    health_score: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), default="LOW", index=True, nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    total_flight_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    flight_cycles: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    commissioning_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_maintenance_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_scheduled_inspection: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    specifications: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    components: Mapped[List["AircraftComponent"]] = relationship(
        "AircraftComponent", back_populates="aircraft", cascade="all, delete-orphan", lazy="selectin"
    )
    predictions: Mapped[List["Prediction"]] = relationship(
        "Prediction", back_populates="aircraft", cascade="all, delete-orphan", lazy="select"
    )
    work_orders: Mapped[List["WorkOrder"]] = relationship(
        "WorkOrder", back_populates="aircraft", cascade="all, delete-orphan", lazy="select"
    )
    alerts: Mapped[List["Alert"]] = relationship(
        "Alert", back_populates="aircraft", cascade="all, delete-orphan", lazy="select"
    )


class AircraftComponent(Base, TimestampMixin):
    __tablename__ = "aircraft_components"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    aircraft_id: Mapped[str] = mapped_column(ForeignKey("aircraft.id", ondelete="CASCADE"), index=True, nullable=False)
    component_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    zone: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # ENGINES, HYDRAULICS, AVIONICS, FUEL, LANDING_GEAR, AIRFRAME
    serial_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    health_score: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    degradation_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    operating_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    installed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="OPERATIONAL", nullable=False)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    aircraft: Mapped["Aircraft"] = relationship("Aircraft", back_populates="components")
