from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class SparePart(Base, TimestampMixin):
    __tablename__ = "spare_parts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    part_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # Propulsion, Hydraulics, Avionics, Airframe
    compatible_aircraft_types: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    minimum_threshold: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=14, nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, default=1000.0, nullable=False)
    storage_location: Mapped[str] = mapped_column(String(64), default="Central Hangar Depot", nullable=False)
    reorder_order_placed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    predicted_demand_30d: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class Technician(Base, TimestampMixin):
    __tablename__ = "technicians"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    employee_code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    rank: Mapped[str] = mapped_column(String(64), nullable=False)  # Junior Tech, Lead Tech, Master Specialist
    specialty: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # Propulsion, Avionics, Hydraulics, Airframe
    certifications: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    current_status: Mapped[str] = mapped_column(String(32), default="AVAILABLE", index=True, nullable=False)  # AVAILABLE, ASSIGNED, ON_LEAVE
    shift: Mapped[str] = mapped_column(String(32), default="DAY", nullable=False)  # DAY, NIGHT


class MaintenanceBay(Base, TimestampMixin):
    __tablename__ = "maintenance_bays"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    bay_code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)  # BAY-01 ... BAY-06
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    hangar_name: Mapped[str] = mapped_column(String(128), default="Main Maintenance Hangar", nullable=False)
    bay_type: Mapped[str] = mapped_column(String(64), nullable=False)  # HEAVY_MAINTENANCE, QUICK_TURNAROUND, AVIONICS_CLEANROOM
    capabilities: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    is_operational: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    current_status: Mapped[str] = mapped_column(String(32), default="AVAILABLE", index=True, nullable=False)  # AVAILABLE, OCCUPIED, MAINTENANCE


class WorkOrder(Base, TimestampMixin):
    __tablename__ = "work_orders"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    work_order_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    aircraft_id: Mapped[str] = mapped_column(ForeignKey("aircraft.id", ondelete="CASCADE"), index=True, nullable=False)
    component_id: Mapped[Optional[int]] = mapped_column(ForeignKey("aircraft_components.id", ondelete="SET NULL"), nullable=True, index=True)
    prediction_id: Mapped[Optional[int]] = mapped_column(ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(32), default="SCHEDULED", index=True, nullable=False)  # SCHEDULED, IN_PROGRESS, COMPLETED, REJECTED, CANCELLED
    priority: Mapped[str] = mapped_column(String(32), default="HIGH", index=True, nullable=False)  # CRITICAL, HIGH, MEDIUM, ROUTINE
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)  # REPLACE, INSPECT, OVERHAUL, CALIBRATE, GROUND
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    actual_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    technician_id: Mapped[Optional[int]] = mapped_column(ForeignKey("technicians.id", ondelete="SET NULL"), nullable=True, index=True)
    bay_id: Mapped[Optional[int]] = mapped_column(ForeignKey("maintenance_bays.id", ondelete="SET NULL"), nullable=True, index=True)
    required_spare_id: Mapped[Optional[int]] = mapped_column(ForeignKey("spare_parts.id", ondelete="SET NULL"), nullable=True, index=True)
    required_spare_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    approval_status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True, nullable=False)  # PENDING, APPROVED, MODIFIED, REJECTED
    approved_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    baseline_type: Mapped[str] = mapped_column(String(32), default="OPTIMIZED", nullable=False)  # OPTIMIZED, REACTIVE

    # Relationships
    aircraft: Mapped["Aircraft"] = relationship("Aircraft", back_populates="work_orders")
    technician: Mapped[Optional["Technician"]] = relationship("Technician")
    bay: Mapped[Optional["MaintenanceBay"]] = relationship("MaintenanceBay")
    spare_part: Mapped[Optional["SparePart"]] = relationship("SparePart")

    __table_args__ = (
        # Ensure no duplicate booking for the exact same technician at the exact same start time
        UniqueConstraint("technician_id", "scheduled_start", name="uq_technician_schedule_slot"),
        # Ensure no duplicate booking for the exact same bay at the exact same start time
        UniqueConstraint("bay_id", "scheduled_start", name="uq_bay_schedule_slot"),
        Index("ix_wo_schedule_window", "scheduled_start", "scheduled_end"),
    )


class MaintenanceEvent(Base, TimestampMixin):
    __tablename__ = "maintenance_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    aircraft_id: Mapped[str] = mapped_column(ForeignKey("aircraft.id", ondelete="CASCADE"), index=True, nullable=False)
    component_id: Mapped[Optional[int]] = mapped_column(ForeignKey("aircraft_components.id", ondelete="SET NULL"), nullable=True, index=True)
    work_order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)  # UNSCHEDULED_FAILURE, SCHEDULED_OVERHAUL, PREVENTIVE_REPLACE, SENSOR_CALIBRATION
    description: Mapped[str] = mapped_column(Text, nullable=False)
    downtime_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    findings: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
