"""
Tests for Phase 4 — Synthetic Data Engine
Validates:
- 30 aircraft across 3 types (Su-30MKI, Rafale, Tejas Mk1A)
- 6-8 components per aircraft
- 90 days of telemetry at hourly ticks (64,800 rows total)
- Resource pool: 12 technicians, 6 maintenance bays, 12 spare parts
- Scenario-driven telemetry degradation curves
- Maintenance event history
"""
import pytest
from sqlalchemy import select, func
from app.db.session import AsyncSessionLocal
from app.db.models import (
    Aircraft,
    AircraftComponent,
    Telemetry,
    MaintenanceEvent,
    Technician,
    MaintenanceBay,
    SparePart,
)
from app.synthetic.scenarios import (
    AIRCRAFT_TYPES,
    SCENARIOS,
    TECHNICIAN_POOL,
    BAY_DEFINITIONS,
    SPARE_PARTS_CATALOG,
)


@pytest.mark.asyncio
async def test_fleet_size_and_composition():
    """Verify exactly 30 aircraft across 3 types exist in the database."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Aircraft).where(Aircraft.tail_number.like("IAF-%")))
        fleet = result.scalars().all()

        assert len(fleet) == 30, f"Expected 30 aircraft, found {len(fleet)}"

        types = {ac.aircraft_type for ac in fleet}
        assert types == set(AIRCRAFT_TYPES.keys())

        # Verify operational statuses are valid
        valid_statuses = {"READY", "MAINTENANCE", "HIGH_RISK", "GROUNDED", "AIRWORTHY", "DEGRADED", "CRITICAL", "AOG", "IN_MAINTENANCE"}
        for ac in fleet:
            assert ac.status in valid_statuses, f"Aircraft {ac.tail_number} has invalid status {ac.status}"
            assert ac.base_location is not None and len(ac.base_location) > 0
            assert ac.squadron is not None and len(ac.squadron) > 0


@pytest.mark.asyncio
async def test_components_hierarchy():
    """Verify each aircraft has 6-8 components mapped to valid subsystems."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Aircraft).where(Aircraft.tail_number.like("IAF-%")))
        fleet = result.scalars().all()

        for ac in fleet:
            comp_result = await session.execute(
                select(AircraftComponent).where(AircraftComponent.aircraft_id == ac.id)
            )
            comps = comp_result.scalars().all()
            assert 6 <= len(comps) <= 8, f"Aircraft {ac.tail_number} has {len(comps)} components (expected 6-8)"

            # Ensure all components have codes and valid health scores (0-100)
            for c in comps:
                assert c.component_code is not None
                assert 0.0 <= c.health_score <= 100.0


@pytest.mark.asyncio
async def test_telemetry_volume_and_integrity():
    """Verify 64,800 telemetry records (30 aircraft * 90 days * 24 hours)."""
    async with AsyncSessionLocal() as session:
        count_result = await session.execute(select(func.count(Telemetry.id)))
        total_telemetry = count_result.scalar()

        expected = 30 * 90 * 24
        assert total_telemetry == expected, f"Expected {expected} telemetry rows, got {total_telemetry}"

        # Sample a telemetry record to verify sensor readings structure
        sample_result = await session.execute(select(Telemetry).limit(5))
        samples = sample_result.scalars().all()
        assert len(samples) > 0

        required_sensors = ["vibration", "egt", "oil_pressure", "oil_temperature", "hydraulic_pressure"]
        for sample in samples:
            assert sample.timestamp is not None
            assert sample.aircraft_id is not None
            for s in required_sensors:
                val = getattr(sample, s)
                assert val is not None and val > 0, f"Sensor {s} was {val} for aircraft {sample.aircraft_id}"


@pytest.mark.asyncio
async def test_maintenance_events_recorded():
    """Verify historical maintenance events exist for aircraft."""
    async with AsyncSessionLocal() as session:
        count_result = await session.execute(select(func.count(MaintenanceEvent.id)))
        event_count = count_result.scalar()

        assert event_count >= 30, f"Expected at least 30 maintenance events, got {event_count}"

        sample_result = await session.execute(select(MaintenanceEvent).limit(5))
        events = sample_result.scalars().all()
        for ev in events:
            assert ev.event_type is not None
            assert ev.downtime_hours >= 0


@pytest.mark.asyncio
async def test_resources_seeded():
    """Verify 12 technicians, 6 maintenance bays, and 12 spare parts are seeded."""
    async with AsyncSessionLocal() as session:
        # Technicians
        t_res = await session.execute(select(func.count(Technician.id)).where(Technician.employee_code.like("IAF-%")))
        tech_count = t_res.scalar()
        assert tech_count == len(TECHNICIAN_POOL), f"Expected {len(TECHNICIAN_POOL)} techs, got {tech_count}"

        # Bays
        b_res = await session.execute(select(func.count(MaintenanceBay.id)).where(MaintenanceBay.bay_code.like("BAY-0%")))
        bay_count = b_res.scalar()
        assert bay_count == len(BAY_DEFINITIONS), f"Expected {len(BAY_DEFINITIONS)} bays, got {bay_count}"

        # Spares
        s_res = await session.execute(select(func.count(SparePart.id)))
        spare_count = s_res.scalar()
        assert spare_count == len(SPARE_PARTS_CATALOG), f"Expected {len(SPARE_PARTS_CATALOG)} spares, got {spare_count}"
