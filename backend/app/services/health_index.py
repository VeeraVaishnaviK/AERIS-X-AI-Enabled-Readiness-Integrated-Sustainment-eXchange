"""
AERIS-X Transparent Weighted Health Formula Engine
Calculates:
- Component Health Index (CHI) in [0, 100] based on sensor deviations and zone criticality
- Aircraft Health Index (AHI) in [0, 100] with minimum component protection formula:
    AHI = 0.40 * min(CHI) + 0.60 * weighted_avg(CHI)
- Readiness status: READY, DEGRADED, HIGH_RISK, GROUNDED
- Risk level: LOW, MEDIUM, HIGH, CRITICAL
- Itemized plain-English explanation for commanders and maintainers
"""
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Aircraft, AircraftComponent, Telemetry
from app.schemas.quality import (
    AircraftHealthResult,
    ComponentHealthBreakdown,
)
from app.synthetic.scenarios import SENSOR_BASELINES


ZONE_SENSOR_WEIGHTS: Dict[str, Dict[str, float]] = {
    "ENGINES": {
        "vibration": 0.35,
        "egt": 0.35,
        "oil_pressure": 0.15,
        "oil_temperature": 0.15,
    },
    "HYDRAULICS": {
        "hydraulic_pressure": 0.60,
        "vibration": 0.20,
        "oil_temperature": 0.20,
    },
    "AVIONICS": {
        "battery_voltage": 0.50,
        "n1_rpm": 0.25,
        "n2_rpm": 0.25,
    },
    "FUEL": {
        "fuel_flow": 0.70,
        "oil_temperature": 0.30,
    },
    "LANDING_GEAR": {
        "vibration": 0.60,
        "hydraulic_pressure": 0.40,
    },
    "AIRFRAME": {
        "vibration": 0.80,
        "hydraulic_pressure": 0.20,
    },
}

# Subsystem critical weights in fleet readiness
ZONE_CRITICALITY: Dict[str, float] = {
    "ENGINES": 0.30,
    "HYDRAULICS": 0.25,
    "AVIONICS": 0.20,
    "LANDING_GEAR": 0.10,
    "FUEL": 0.10,
    "AIRFRAME": 0.05,
}


class HealthIndexEngine:
    """Computes transparent health scores for components and fleet aircraft."""

    @staticmethod
    def calculate_sensor_penalty(sensor_name: str, value: float) -> Tuple[float, Optional[str]]:
        """Calculate penalty (0-100) and rationale for a sensor deviation."""
        if sensor_name not in SENSOR_BASELINES:
            return 0.0, None

        b_min, b_max = SENSOR_BASELINES[sensor_name]
        mid = (b_min + b_max) / 2.0
        span = (b_max - b_min) / 2.0

        if b_min <= value <= b_max:
            return 0.0, None

        # Normalized deviation beyond tolerance
        if value > b_max:
            deviation = (value - b_max) / max(span, 1.0)
            reason = f"{sensor_name} high ({value:.1f} > nominal max {b_max})"
        else:
            deviation = (b_min - value) / max(span, 1.0)
            reason = f"{sensor_name} low ({value:.1f} < nominal min {b_min})"

        # Quadratic ramp penalty
        penalty = min(100.0, max(0.0, 100.0 * (1.0 - (1.0 / (1.0 + deviation * 1.5)))))
        return round(penalty, 2), reason

    @classmethod
    def calculate_component_health(
        cls,
        component_code: str,
        name: str,
        zone: str,
        telemetry: Dict[str, float],
        component_id: Optional[int] = None,
    ) -> ComponentHealthBreakdown:
        """Calculate 0-100 health score for a single aircraft component."""
        weights = ZONE_SENSOR_WEIGHTS.get(zone, {"vibration": 0.5, "hydraulic_pressure": 0.5})
        total_weight = sum(weights.values())

        weighted_penalty = 0.0
        contributors: List[str] = []

        for sensor, w in weights.items():
            val = telemetry.get(sensor)
            if val is not None:
                pen, reason = cls.calculate_sensor_penalty(sensor, float(val))
                weighted_penalty += (w / total_weight) * pen
                if pen > 15.0 and reason:
                    contributors.append(f"{reason} (penalty: {pen:.1f})")

        health_score = max(0.0, min(100.0, round(100.0 - weighted_penalty, 1)))
        degradation_pct = round(100.0 - health_score, 1)

        if health_score >= 85.0:
            status = "OPERATIONAL"
        elif health_score >= 70.0:
            status = "DEGRADED"
        elif health_score >= 50.0:
            status = "FAULT_WARNING"
        else:
            status = "CRITICAL"

        return ComponentHealthBreakdown(
            component_id=component_id,
            component_code=component_code,
            name=name,
            zone=zone,
            health_score=health_score,
            degradation_percent=degradation_pct,
            status=status,
            primary_contributors=contributors,
        )

    @classmethod
    def calculate_aircraft_health(
        cls,
        aircraft_id: str,
        aircraft_type: str,
        tail_number: str,
        components_health: List[ComponentHealthBreakdown],
    ) -> AircraftHealthResult:
        """
        Aggregate component healths into Aircraft Health Index (AHI):
        AHI = 0.40 * min(CHI) + 0.60 * weighted_avg(CHI)
        """
        if not components_health:
            return AircraftHealthResult(
                aircraft_id=aircraft_id,
                aircraft_type=aircraft_type,
                tail_number=tail_number,
                health_score=100.0,
                status="READY",
                risk_level="LOW",
                min_component_health=100.0,
                avg_component_health=100.0,
                components=[],
                explanation="No components recorded. Default nominal health assigned.",
                formula_breakdown={"formula": "default", "ahi": 100.0},
            )

        min_comp = min(components_health, key=lambda c: c.health_score)
        min_chi = min_comp.health_score

        # Criticality-weighted average
        total_w = 0.0
        weighted_sum = 0.0
        for comp in components_health:
            cw = ZONE_CRITICALITY.get(comp.zone, 0.1)
            total_w += cw
            weighted_sum += comp.health_score * cw

        avg_chi = weighted_sum / max(total_w, 1e-4)

        # Transparent AHI Formula
        raw_ahi = (0.40 * min_chi) + (0.60 * avg_chi)
        ahi = max(0.0, min(100.0, round(raw_ahi, 1)))

        # Status & Risk Level Mapping
        if ahi >= 85.0 and min_chi >= 70.0:
            status = "READY"
            risk_level = "LOW"
        elif ahi >= 70.0 and min_chi >= 50.0:
            status = "DEGRADED"
            risk_level = "MEDIUM"
        elif ahi >= 50.0:
            status = "HIGH_RISK"
            risk_level = "HIGH"
        else:
            status = "GROUNDED"
            risk_level = "CRITICAL"

        # Explainable Plain English Audit Summary
        if status == "READY":
            explanation = f"Aircraft {tail_number} ({aircraft_type}) is AIRWORTHY (AHI {ahi:.1f}). All components within nominal thresholds."
        elif status == "DEGRADED":
            explanation = (
                f"Aircraft {tail_number} ({aircraft_type}) in DEGRADED status (AHI {ahi:.1f}). "
                f"Lowest subsystem is {min_comp.name} ({min_comp.component_code}) at {min_chi:.1f}% health. "
                f"{' Issues: ' + '; '.join(min_comp.primary_contributors) if min_comp.primary_contributors else ''}"
            )
        elif status == "HIGH_RISK":
            explanation = (
                f"Aircraft {tail_number} ({aircraft_type}) is HIGH RISK (AHI {ahi:.1f}). "
                f"Subsystem {min_comp.name} ({min_comp.component_code}) degraded to {min_chi:.1f}%."
            )
        else:
            explanation = (
                f"Aircraft {tail_number} ({aircraft_type}) is GROUNDED / CRITICAL (AHI {ahi:.1f}). "
                f"Critical failure detected in {min_comp.name} ({min_comp.component_code}, CHI={min_chi:.1f}%)."
            )

        formula_breakdown = {
            "formula": "AHI = 0.40 * min(CHI) + 0.60 * weighted_avg(CHI)",
            "min_component": min_comp.component_code,
            "min_chi": min_chi,
            "weighted_avg_chi": round(avg_chi, 2),
            "calculated_ahi": ahi,
        }

        return AircraftHealthResult(
            aircraft_id=aircraft_id,
            aircraft_type=aircraft_type,
            tail_number=tail_number,
            health_score=ahi,
            status=status,
            risk_level=risk_level,
            min_component_health=min_chi,
            avg_component_health=round(avg_chi, 1),
            components=components_health,
            explanation=explanation,
            formula_breakdown=formula_breakdown,
        )

    @classmethod
    async def evaluate_aircraft_from_db(
        cls,
        session: AsyncSession,
        aircraft_id: str,
        update_db: bool = True,
    ) -> Optional[AircraftHealthResult]:
        """
        Fetch latest telemetry for the aircraft, evaluate all components, compute AHI,
        and optionally update the database records.
        """
        ac_result = await session.execute(select(Aircraft).where(Aircraft.id == aircraft_id))
        aircraft = ac_result.scalar_one_or_none()
        if not aircraft:
            return None

        # Fetch latest telemetry
        tel_result = await session.execute(
            select(Telemetry)
            .where(Telemetry.aircraft_id == aircraft_id)
            .order_by(desc(Telemetry.timestamp))
            .limit(1)
        )
        latest_tel = tel_result.scalar_one_or_none()

        tel_data = {}
        if latest_tel:
            for s in SENSOR_BASELINES.keys():
                val = getattr(latest_tel, s, None)
                if val is not None:
                    tel_data[s] = float(val)

        # Evaluate components
        comp_breakdowns: List[ComponentHealthBreakdown] = []
        for comp in aircraft.components:
            breakdown = cls.calculate_component_health(
                component_code=comp.component_code,
                name=comp.name,
                zone=comp.zone,
                telemetry=tel_data,
                component_id=comp.id,
            )
            comp_breakdowns.append(breakdown)

            if update_db:
                comp.health_score = breakdown.health_score
                comp.degradation_percent = breakdown.degradation_percent
                comp.status = breakdown.status

        # Aggregate aircraft health
        result = cls.calculate_aircraft_health(
            aircraft_id=aircraft.id,
            aircraft_type=aircraft.aircraft_type,
            tail_number=aircraft.tail_number,
            components_health=comp_breakdowns,
        )

        if update_db:
            aircraft.health_score = result.health_score
            aircraft.status = result.status
            aircraft.risk_level = result.risk_level

        return result
