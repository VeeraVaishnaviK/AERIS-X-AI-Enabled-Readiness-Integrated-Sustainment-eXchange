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
    async with AsyncSessionLocal() as session:
        # Create test aircraft
        aircraft = Aircraft(
            id="TEST-001",
            tail_number="T-001",
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

        # Create component
        comp = AircraftComponent(
            aircraft_id="TEST-001",
            component_code="ENG-PORT",
            name="M88 Turbofan Engine (Port)",
            zone="ENGINES",
            serial_number="M88-TEST-001",
            health_score=92.0,
            degradation_percent=8.0,
            operating_hours=1250.0,
            status="OPERATIONAL",
        )
        session.add(comp)
        await session.commit()

        # Retrieve and verify
        result = await session.execute(select(Aircraft).where(Aircraft.id == "TEST-001"))
        retrieved = result.scalar_one()
        assert retrieved.tail_number == "T-001"
        assert len(retrieved.components) == 1
        assert retrieved.components[0].serial_number == "M88-TEST-001"


@pytest.mark.asyncio
async def test_technician_and_bay_double_booking_constraint():
    """Verify unique constraint prevents overlapping technician or bay double-booking."""
    async with AsyncSessionLocal() as session:
        tech = Technician(
            employee_code="TECH-TEST-01",
            name="Sgt. Ramesh Kumar",
            rank="Lead Tech",
            specialty="Propulsion",
            certifications=["M88 Engine Specialist"],
            current_status="AVAILABLE",
            shift="DAY",
        )
        bay = MaintenanceBay(
            bay_code="BAY-TEST-01",
            name="Heavy Bay Alpha",
            hangar_name="Hangar 1",
            bay_type="HEAVY_MAINTENANCE",
            capabilities=["Engine Overhaul"],
            is_operational=True,
            current_status="AVAILABLE",
        )
        session.add_all([tech, bay])
        await session.commit()

        slot_start = datetime.now(timezone.utc) + timedelta(days=1)
        slot_end = slot_start + timedelta(hours=4)

        # Booking 1
        wo1 = WorkOrder(
            work_order_number="WO-TEST-001",
            aircraft_id="TEST-001",
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

        # Booking 2 with same technician and same start time must trigger IntegrityError
        wo2 = WorkOrder(
            work_order_number="WO-TEST-002",
            aircraft_id="TEST-001",
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
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
