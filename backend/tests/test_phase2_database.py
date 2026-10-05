import uuid
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from app.db.session import async_engine, AsyncSessionLocal
from app.db.models import (
    Aircraft,
    AircraftComponent,
    Telemetry,
    Prediction,
    PredictionEvidence,
    SparePart,
    Technician,
    MaintenanceBay,
    WorkOrder,
    Alert,
    AuditLog,
    User,
    ModelEvaluation,
    DocumentRecord,
)


def _uid() -> str:
    """Short unique suffix to avoid collisions across test runs."""
    return uuid.uuid4().hex[:8]


@pytest.mark.asyncio
async def test_database_tables_exist():
    """Verify all 15 required models/tables exist in the database schema."""
    async with async_engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())

        expected_tables = [
            "aircraft",
            "aircraft_components",
            "telemetry",
            "predictions",
            "prediction_evidence",
            "spare_parts",
            "technicians",
            "maintenance_bays",
            "work_orders",
            "maintenance_events",
            "alerts",
            "audit_logs",
            "users",
            "model_evaluations",
            "document_records",
        ]

        for table in expected_tables:
            assert table in tables, f"Missing expected table '{table}'"


@pytest.mark.asyncio
async def test_aircraft_and_components_crud():
    """Verify insertion and relationship between Aircraft and AircraftComponent."""
    uid = _uid()
    ac_id = f"TEST-{uid}"
    async with AsyncSessionLocal() as session:
        aircraft = Aircraft(
            id=ac_id,
            tail_number=f"T-{uid}",
            aircraft_type="Rafale",
            squadron="No. 17 Golden Arrows",
            base_location="Ambala AFS",
            status="READY",
            health_score=94.5,
            risk_level="LOW",
            total_flight_hours=1250.0,
            flight_cycles=420,
        )
        session.add(aircraft)
        await session.commit()

        comp = AircraftComponent(
            aircraft_id=ac_id,
            component_code="ENG-PORT",
            name="M88 Turbofan Engine (Port)",
            zone="ENGINES",
            serial_number=f"M88-{uid}",
            health_score=92.0,
            degradation_percent=8.0,
            operating_hours=1250.0,
            status="OPERATIONAL",
        )
        session.add(comp)
        await session.commit()

        try:
            result = await session.execute(select(Aircraft).where(Aircraft.id == ac_id))
            retrieved = result.scalar_one()
            assert retrieved.tail_number == f"T-{uid}"
            assert len(retrieved.components) == 1
            assert retrieved.components[0].serial_number == f"M88-{uid}"
        finally:
            async with AsyncSessionLocal() as clean_session:
                from sqlalchemy import delete
                await clean_session.execute(delete(AircraftComponent).where(AircraftComponent.aircraft_id == ac_id))
                await clean_session.execute(delete(Aircraft).where(Aircraft.id == ac_id))
                await clean_session.commit()


@pytest.mark.asyncio
async def test_technician_and_bay_double_booking_constraint():
    """Verify unique constraint prevents overlapping technician or bay double-booking."""
    uid = _uid()
    ac_id = f"BOOK-{uid}"
    async with AsyncSessionLocal() as session:
        # Create prerequisite aircraft
        aircraft = Aircraft(
            id=ac_id, tail_number=f"BK-{uid}", aircraft_type="Su-30MKI",
            squadron="Test", base_location="Test AFS", status="READY",
        )
        tech = Technician(
            employee_code=f"TECH-{uid}",
            name="Sgt. Ramesh Kumar",
            rank="Lead Tech",
            specialty="Propulsion",
            certifications=["M88 Engine Specialist"],
            current_status="AVAILABLE",
            shift="DAY",
        )
        bay = MaintenanceBay(
            bay_code=f"BAY-{uid}",
            name="Heavy Bay Alpha",
            hangar_name="Hangar 1",
            bay_type="HEAVY_MAINTENANCE",
            capabilities=["Engine Overhaul"],
            is_operational=True,
            current_status="AVAILABLE",
        )
        session.add_all([aircraft, tech, bay])
        await session.commit()

        slot_start = datetime.now(timezone.utc) + timedelta(days=1)
        slot_end = slot_start + timedelta(hours=4)

        wo1 = WorkOrder(
            work_order_number=f"WO-{uid}-001",
            aircraft_id=ac_id,
            status="SCHEDULED",
            priority="HIGH",
            action_type="INSPECT",
            title="Inspect Port Engine",
            scheduled_start=slot_start,
            scheduled_end=slot_end,
            technician_id=tech.id,
            bay_id=bay.id,
        )
        session.add(wo1)
        await session.commit()

        wo2 = WorkOrder(
            work_order_number=f"WO-{uid}-002",
            aircraft_id=ac_id,
            status="SCHEDULED",
            priority="HIGH",
            action_type="INSPECT",
            title="Inspect Avionics",
            scheduled_start=slot_start,
            scheduled_end=slot_end,
            technician_id=tech.id,
            bay_id=bay.id,
        )
        session.add(wo2)
        try:
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()
        finally:
            async with AsyncSessionLocal() as clean_session:
                from sqlalchemy import delete
                await clean_session.execute(delete(WorkOrder).where(WorkOrder.work_order_number.like(f"WO-{uid}-%")))
                await clean_session.execute(delete(Aircraft).where(Aircraft.id == ac_id))
                await clean_session.execute(delete(Technician).where(Technician.employee_code == f"TECH-{uid}"))
                await clean_session.execute(delete(MaintenanceBay).where(MaintenanceBay.bay_code == f"BAY-{uid}"))
                await clean_session.commit()
