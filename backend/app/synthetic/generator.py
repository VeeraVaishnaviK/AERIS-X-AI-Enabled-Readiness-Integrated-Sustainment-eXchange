"""
AERIS-X Synthetic Data Generator
Deterministic seeding of fleet, telemetry, components, maintenance history, spares, techs, bays.
SEED=42 ensures identical demo data every time.
"""
import math
import random
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
from sqlalchemy import select, delete

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.db.models import (
    Aircraft,
    AircraftComponent,
    Telemetry,
    MaintenanceEvent,
    SparePart,
    Technician,
    MaintenanceBay,
)
from app.synthetic.scenarios import (
    AIRCRAFT_TYPES,
    BAY_DEFINITIONS,
    SCENARIOS,
    SENSOR_BASELINES,
    SPARE_PARTS_CATALOG,
    TECHNICIAN_POOL,
)
from app.synthetic.seed_users import seed_users

logger = get_logger("aeris.synthetic")

NUM_AIRCRAFT = 30
TELEMETRY_DAYS = 90
TICKS_PER_DAY = 24  # one reading per hour
BASE_DATE = datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc)


def _degradation_curve(day: int, onset: int, peak: int, magnitude: float, rng: np.random.Generator) -> float:
    """Exponential degradation curve with noise."""
    if day < onset:
        return 1.0 + rng.normal(0, 0.01)
    progress = min((day - onset) / max(peak - onset, 1), 1.0)
    # Exponential ramp: slow start, accelerating
    factor = 1.0 + (magnitude - 1.0) * (1.0 - math.exp(-3.0 * progress))
    noise = rng.normal(0, 0.02 * abs(magnitude))
    return max(factor + noise, 0.5)


def _periodic_spike(day: int, period: int, magnitude: float, rng: np.random.Generator) -> float:
    """Periodic spike pattern for REPEATED_ISSUE scenario."""
    if day % period < 2:
        return magnitude * (1.0 + rng.normal(0, 0.1))
    return 1.0 + rng.normal(0, 0.01)


def _generate_telemetry_tick(
    aircraft_id: str,
    component_id: Optional[int],
    timestamp: datetime,
    day: int,
    scenario: Any,
    rng: np.random.Generator,
) -> Dict[str, Any]:
    """Generate a single telemetry reading for the given day and scenario."""
    sensors = {}
    for sensor_name, (base_min, base_max) in SENSOR_BASELINES.items():
        base = rng.uniform(base_min, base_max)

        if scenario.tag == "REPEATED_ISSUE" and sensor_name in scenario.affected_sensors:
            mult = _periodic_spike(day, 20, scenario.affected_sensors[sensor_name], rng)
        elif sensor_name in scenario.affected_sensors:
            mult = _degradation_curve(day, scenario.onset_day, scenario.peak_day,
                                       scenario.affected_sensors[sensor_name], rng)
        else:
            mult = 1.0 + rng.normal(0, 0.005)

        # After replacement, sensors recover
        if (scenario.replacement_after_failure and scenario.replacement_day
                and day >= scenario.replacement_day):
            mult = 1.0 + rng.normal(0, 0.01)

        # Sensor failure: voltage drops / stuck
        if scenario.tag == "SENSOR_FAILURE" and sensor_name == "battery_voltage":
            if day >= scenario.peak_day:
                base = 18.0  # stuck low
                mult = 1.0
            elif day >= scenario.onset_day:
                progress = (day - scenario.onset_day) / max(scenario.peak_day - scenario.onset_day, 1)
                base = base * (1.0 - 0.35 * progress)
                mult = 1.0

        if scenario.tag == "SENSOR_FAILURE" and sensor_name == "n1_rpm" and day >= scenario.peak_day:
            base = 96.0  # stuck
            mult = 1.0

        sensors[sensor_name] = round(base * mult, 3)

    # Compute anomaly score heuristic
    anomaly_factors = []
    for sensor_name, value in sensors.items():
        bmin, bmax = SENSOR_BASELINES[sensor_name]
        nominal_mid = (bmin + bmax) / 2
        nominal_range = (bmax - bmin) / 2
        deviation = abs(value - nominal_mid) / nominal_range if nominal_range > 0 else 0
        if deviation > 1.5:
            anomaly_factors.append(deviation)

    anomaly_score = min(sum(anomaly_factors) / max(len(anomaly_factors), 1) * 0.3, 1.0) if anomaly_factors else 0.0
    is_anomaly = anomaly_score > 0.4

    return {
        "aircraft_id": aircraft_id,
        "component_id": component_id,
        "timestamp": timestamp,
        **sensors,
        "anomaly_score": round(anomaly_score, 4),
        "is_anomaly": is_anomaly,
        "quality_score": round(rng.uniform(85, 100) if scenario.tag != "SENSOR_FAILURE" else rng.uniform(40, 70), 2),
        "sensor_status": {},
        "raw_payload": {},
    }


async def _clear_existing_data(session) -> None:
    """Remove previously seeded data for idempotent re-runs."""
    for model in [Telemetry, MaintenanceEvent, AircraftComponent, Aircraft,
                  SparePart, Technician, MaintenanceBay]:
        await session.execute(delete(model))
    await session.commit()
    logger.info("Cleared existing synthetic data.")


async def seed_fleet(session) -> Dict[str, Any]:
    """Seed 30 aircraft across 3 types with components."""
    rng = np.random.default_rng(settings.SEED)
    aircraft_map = {}
    ac_counter = 100

    type_names = list(AIRCRAFT_TYPES.keys())
    # Distribute: 12 Su-30MKI, 10 Rafale, 8 Tejas
    distribution = [("Su-30MKI", 12), ("Rafale", 10), ("Tejas Mk1A", 8)]

    for type_name, count in distribution:
        type_info = AIRCRAFT_TYPES[type_name]
        for i in range(count):
            ac_counter += 1
            ac_id = f"AF-{ac_counter}"
            squadron = type_info["squadrons"][i % len(type_info["squadrons"])]
            base = type_info["bases"][i % len(type_info["bases"])]

            # Assign scenario deterministically
            scenario_idx = (ac_counter - 101) % len(SCENARIOS)
            scenario = SCENARIOS[scenario_idx]

            flight_hours = round(rng.uniform(500, 4000), 1)
            flight_cycles = int(flight_hours / rng.uniform(1.5, 3.0))

            aircraft = Aircraft(
                id=ac_id,
                tail_number=f"IAF-{type_name[:2].upper()}-{ac_counter}",
                aircraft_type=type_name,
                squadron=squadron,
                base_location=base,
                status="READY",
                health_score=round(rng.uniform(60, 100), 1),
                risk_level="LOW",
                total_flight_hours=flight_hours,
                flight_cycles=flight_cycles,
                commissioning_date=BASE_DATE - timedelta(days=int(rng.uniform(365, 3650))),
                last_maintenance_date=BASE_DATE - timedelta(days=int(rng.uniform(10, 90))),
                specifications={"type": type_name, "scenario": scenario.tag},
            )
            session.add(aircraft)

            # Create components
            comp_ids = []
            for comp_code, comp_name, zone in type_info["components"]:
                comp = AircraftComponent(
                    aircraft_id=ac_id,
                    component_code=comp_code,
                    name=comp_name,
                    zone=zone,
                    serial_number=f"{comp_code}-{ac_id}-{rng.integers(10000, 99999)}",
                    health_score=round(rng.uniform(55, 100), 1),
                    degradation_percent=round(rng.uniform(0, 40), 1),
                    operating_hours=flight_hours * rng.uniform(0.8, 1.0),
                    status="OPERATIONAL",
                )
                session.add(comp)
                comp_ids.append(comp)

            aircraft_map[ac_id] = {
                "aircraft": aircraft,
                "components": comp_ids,
                "scenario": scenario,
                "type": type_name,
            }

    await session.flush()
    logger.info(f"Seeded {len(aircraft_map)} aircraft with components.")
    return aircraft_map


async def seed_telemetry(session, aircraft_map: Dict[str, Any]) -> int:
    """Generate 90 days of hourly telemetry for all aircraft."""
    rng = np.random.default_rng(settings.SEED + 1)
    total_rows = 0
    batch = []

    for ac_id, info in aircraft_map.items():
        scenario = info["scenario"]
        # Use first component for telemetry association
        comp = info["components"][0] if info["components"] else None
        comp_id = comp.id if comp else None

        for day in range(TELEMETRY_DAYS):
            for hour in range(TICKS_PER_DAY):
                ts = BASE_DATE + timedelta(days=day, hours=hour)
                tick = _generate_telemetry_tick(ac_id, comp_id, ts, day, scenario, rng)
                batch.append(Telemetry(**tick))
                total_rows += 1

            # Flush in batches to avoid memory issues
            if len(batch) >= 5000:
                session.add_all(batch)
                await session.flush()
                batch = []

    if batch:
        session.add_all(batch)
        await session.flush()

    logger.info(f"Seeded {total_rows} telemetry rows ({NUM_AIRCRAFT} aircraft × {TELEMETRY_DAYS} days × {TICKS_PER_DAY} ticks/day).")
    return total_rows


async def seed_maintenance_history(session, aircraft_map: Dict[str, Any]) -> int:
    """Generate historical maintenance events based on scenarios."""
    rng = np.random.default_rng(settings.SEED + 2)
    count = 0

    for ac_id, info in aircraft_map.items():
        scenario = info["scenario"]
        comp = info["components"][0] if info["components"] else None

        # Every aircraft gets 2-5 historical maintenance events
        num_events = int(rng.integers(2, 6))
        for i in range(num_events):
            event_day = int(rng.integers(0, TELEMETRY_DAYS))
            event_types = ["SCHEDULED_OVERHAUL", "PREVENTIVE_REPLACE", "SENSOR_CALIBRATION", "UNSCHEDULED_FAILURE"]

            if scenario.causes_failure and scenario.failure_day and event_day >= scenario.failure_day:
                etype = "UNSCHEDULED_FAILURE"
            else:
                etype = event_types[i % len(event_types)]

            event = MaintenanceEvent(
                aircraft_id=ac_id,
                component_id=comp.id if comp else None,
                event_type=etype,
                description=f"{etype.replace('_', ' ').title()} on {ac_id} component {comp.component_code if comp else 'N/A'}",
                downtime_hours=round(rng.uniform(2, 48), 1),
                completed_at=BASE_DATE + timedelta(days=event_day, hours=int(rng.integers(0, 24))),
                outcome_verified=True,
                findings={"scenario": scenario.tag, "synthetic": True},
            )
            session.add(event)
            count += 1

    await session.flush()
    logger.info(f"Seeded {count} maintenance events.")
    return count


async def seed_resources(session) -> None:
    """Seed technicians, maintenance bays, and spare parts."""
    # Technicians
    for t in TECHNICIAN_POOL:
        tech = Technician(
            employee_code=f"IAF-{t['name'].split()[-1].upper()}-{TECHNICIAN_POOL.index(t)+1:03d}",
            name=t["name"],
            rank=t["rank"],
            specialty=t["specialty"],
            certifications=t["certs"],
            current_status="AVAILABLE",
            shift=t["shift"],
        )
        session.add(tech)

    # Bays
    for b in BAY_DEFINITIONS:
        bay = MaintenanceBay(
            bay_code=b["code"],
            name=b["name"],
            hangar_name=b["hangar"],
            bay_type=b["type"],
            capabilities=b["caps"],
            is_operational=True,
            current_status="AVAILABLE",
        )
        session.add(bay)

    # Spare Parts
    for sp in SPARE_PARTS_CATALOG:
        part = SparePart(
            part_number=sp["pn"],
            name=sp["name"],
            category=sp["cat"],
            compatible_aircraft_types=sp["compat"],
            stock_quantity=sp["stock"],
            minimum_threshold=sp["min"],
            lead_time_days=sp["lead"],
            unit_cost=sp["cost"],
            storage_location="Central Maintenance Depot",
        )
        session.add(part)

    await session.flush()
    logger.info(f"Seeded {len(TECHNICIAN_POOL)} technicians, {len(BAY_DEFINITIONS)} bays, {len(SPARE_PARTS_CATALOG)} spare parts.")


async def seed_all() -> None:
    """Master seeding function: users + fleet + telemetry + resources."""
    import time
    start = time.time()

    # Seed users first
    await seed_users()

    async with AsyncSessionLocal() as session:
        await _clear_existing_data(session)
        aircraft_map = await seed_fleet(session)
        await seed_resources(session)
        await session.commit()

        # Telemetry and maintenance in separate transactions for memory management
        telemetry_count = await seed_telemetry(session, aircraft_map)
        await session.commit()

        maint_count = await seed_maintenance_history(session, aircraft_map)
        await session.commit()

    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print(f"AERIS-X Synthetic Data Engine — Seeding Complete")
    print(f"{'='*60}")
    print(f"  Aircraft:           {NUM_AIRCRAFT}")
    print(f"  Telemetry rows:     {telemetry_count:,}")
    print(f"  Maintenance events: {maint_count}")
    print(f"  Technicians:        {len(TECHNICIAN_POOL)}")
    print(f"  Maintenance bays:   {len(BAY_DEFINITIONS)}")
    print(f"  Spare parts:        {len(SPARE_PARTS_CATALOG)}")
    print(f"  SEED:               {settings.SEED}")
    print(f"  Elapsed:            {elapsed:.1f}s")
    print(f"{'='*60}")

    assert telemetry_count == NUM_AIRCRAFT * TELEMETRY_DAYS * TICKS_PER_DAY, \
        f"Expected {NUM_AIRCRAFT * TELEMETRY_DAYS * TICKS_PER_DAY} telemetry rows, got {telemetry_count}"
    assert elapsed < 90, f"Seeding took {elapsed:.1f}s, exceeds 90s gate requirement"


if __name__ == "__main__":
    asyncio.run(seed_all())
