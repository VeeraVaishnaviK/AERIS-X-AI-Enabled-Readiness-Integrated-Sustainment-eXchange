"""
AERIS-X Fleet Readiness Engine
Computes fleet availability %, mission-capability rates, risk distribution,
backlog counts, downtime projections, and 7-day availability forecasting.
"""
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.aircraft import Aircraft
from app.db.models.prediction import Prediction
from app.db.models.maintenance import WorkOrder
from app.schemas.readiness import (
    DailyForecast,
    SquadronReadiness,
    TypeReadiness,
    FleetReadinessOverview,
)


def compute_fleet_readiness(
    aircraft_records: List[Dict[str, Any]],
    prediction_records: Optional[List[Dict[str, Any]]] = None,
    work_orders: Optional[List[Dict[str, Any]]] = None,
    base_time: Optional[datetime] = None,
) -> FleetReadinessOverview:
    """
    Computes readiness metrics from aircraft, prediction, and work order records.
    Pure in-memory computation for rapid evaluation and testing.
    """
    base_time = base_time or datetime.now(timezone.utc)
    total_aircraft = len(aircraft_records) or 30

    operational_count = 0
    maintenance_count = 0
    high_risk_count = 0
    grounded_count = 0

    squadron_data: Dict[str, Dict[str, int]] = {}
    type_data: Dict[str, Dict[str, int]] = {}

    for ac in aircraft_records:
        status = ac.get("current_status", "OPERATIONAL").upper()
        sq = ac.get("squadron", "Central Fleet Wing")
        ac_type = ac.get("aircraft_type", "HAL Tejas Mk1A")

        if sq not in squadron_data:
            squadron_data[sq] = {"total": 0, "operational": 0, "maint": 0, "high_risk": 0, "grounded": 0}
        if ac_type not in type_data:
            type_data[ac_type] = {"total": 0, "operational": 0, "maint": 0, "high_risk": 0, "grounded": 0}

        squadron_data[sq]["total"] += 1
        type_data[ac_type]["total"] += 1

        is_high_risk = ac.get("has_high_risk", False) or ac.get("health_score", 100) < 65

        if status == "GROUNDED":
            grounded_count += 1
            squadron_data[sq]["grounded"] += 1
            type_data[ac_type]["grounded"] += 1
        elif status == "MAINTENANCE":
            maintenance_count += 1
            squadron_data[sq]["maint"] += 1
            type_data[ac_type]["maint"] += 1
        elif is_high_risk:
            high_risk_count += 1
            operational_count += 1
            squadron_data[sq]["high_risk"] += 1
            squadron_data[sq]["operational"] += 1
            type_data[ac_type]["high_risk"] += 1
            type_data[ac_type]["operational"] += 1
        else:
            operational_count += 1
            squadron_data[sq]["operational"] += 1
            type_data[ac_type]["operational"] += 1

    # Availability % = (Operational non-grounded / Total) * 100
    avail_pct = round((operational_count / max(1, total_aircraft)) * 100.0, 1)

    # Mission capable rate (Fully Mission Capable = Operational minus High Risk)
    fmc_count = max(0, operational_count - high_risk_count)
    mission_capable_pct = round((fmc_count / max(1, total_aircraft)) * 100.0, 1)

    # Backlog count
    backlog = 0
    if work_orders:
        backlog = sum(1 for wo in work_orders if wo.get("status") in ["SCHEDULED", "IN_PROGRESS", "PENDING"])
    else:
        backlog = high_risk_count + maintenance_count

    # Trend: IMPROVING if maintenance is resolving issues, DEGRADING if high risk is growing
    if high_risk_count > (total_aircraft * 0.25):
        trend = "DEGRADING"
    elif high_risk_count < 3 and operational_count >= (total_aircraft * 0.85):
        trend = "IMPROVING"
    else:
        trend = "STABLE"

    # Predicted downtime over next 7 days (hours)
    # Estimate based on high risk + in-maintenance aircraft
    pred_downtime = (maintenance_count * 16.0) + (high_risk_count * 8.5)

    # Generate 7-day daily forecast
    daily_forecasts: List[DailyForecast] = []
    current_avail = avail_pct
    current_ready = operational_count
    current_maint = maintenance_count
    current_risk = high_risk_count

    for day in range(1, 8):
        f_date = (base_time + timedelta(days=day)).strftime("%Y-%m-%d")

        # Projected resolution trajectory (predictive maintenance repairs high risk fleet)
        if trend == "IMPROVING" or current_maint > 0:
            maint_delta = -max(0, int(round(current_maint * 0.2)))
            risk_delta = -max(0, int(round(current_risk * 0.25)))
        else:
            maint_delta = 1 if (day % 3 == 0) else 0
            risk_delta = 1 if (day % 4 == 0) else -1

        projected_maint = max(1, current_maint + maint_delta)
        projected_risk = max(0, current_risk + risk_delta)
        projected_ready = min(total_aircraft, total_aircraft - projected_maint - grounded_count)
        projected_avail = round((projected_ready / total_aircraft) * 100.0, 1)

        ci_lower = max(0.0, round(projected_avail - (1.5 * day), 1))
        ci_upper = min(100.0, round(projected_avail + (1.2 * day), 1))

        daily_forecasts.append(
            DailyForecast(
                day_offset=day,
                date=f_date,
                predicted_availability_pct=projected_avail,
                predicted_ready_count=projected_ready,
                predicted_maintenance_count=projected_maint,
                predicted_risk_count=projected_risk,
                confidence_interval=[ci_lower, ci_upper],
            )
        )
        current_maint = projected_maint
        current_risk = projected_risk

    # Format Squadron breakdown
    squadron_res: Dict[str, SquadronReadiness] = {}
    for sq_name, s_data in squadron_data.items():
        sq_total = s_data["total"]
        sq_avail = round((s_data["operational"] / max(1, sq_total)) * 100.0, 1)
        sq_fmc = round(((s_data["operational"] - s_data["high_risk"]) / max(1, sq_total)) * 100.0, 1)
        squadron_res[sq_name] = SquadronReadiness(
            squadron_name=sq_name,
            total_aircraft=sq_total,
            operational=s_data["operational"],
            in_maintenance=s_data["maint"],
            high_risk=s_data["high_risk"],
            grounded=s_data["grounded"],
            availability_pct=sq_avail,
            fmc_pct=sq_fmc,
        )

    # Format Aircraft Type breakdown
    type_res: Dict[str, TypeReadiness] = {}
    for t_name, t_data in type_data.items():
        t_total = t_data["total"]
        t_avail = round((t_data["operational"] / max(1, t_total)) * 100.0, 1)
        type_res[t_name] = TypeReadiness(
            aircraft_type=t_name,
            total_aircraft=t_total,
            operational=t_data["operational"],
            in_maintenance=t_data["maint"],
            high_risk=t_data["high_risk"],
            grounded=t_data["grounded"],
            availability_pct=t_avail,
        )

    return FleetReadinessOverview(
        total_aircraft=total_aircraft,
        operational_count=operational_count,
        maintenance_count=maintenance_count,
        high_risk_count=high_risk_count,
        grounded_count=grounded_count,
        availability_percentage=avail_pct,
        mission_capable_percentage=mission_capable_pct,
        trend=trend,
        backlog_count=backlog,
        predicted_downtime_7d_hours=round(pred_downtime, 1),
        seven_day_forecast=daily_forecasts,
        squadron_breakdown=squadron_res,
        aircraft_type_breakdown=type_res,
    )


async def compute_fleet_readiness_db(session: AsyncSession) -> FleetReadinessOverview:
    """Async database-backed fleet readiness computation."""
    # Query all aircraft
    ac_result = await session.execute(select(Aircraft))
    aircraft_models = ac_result.scalars().all()

    # Query active work orders
    wo_result = await session.execute(select(WorkOrder))
    work_orders = [
        {"id": w.id, "aircraft_id": w.aircraft_id, "status": w.status}
        for w in wo_result.scalars().all()
    ]

    # Query recent predictions with high/critical risk
    pred_result = await session.execute(
        select(Prediction.aircraft_id).where(Prediction.risk_level.in_(["HIGH", "CRITICAL"])).distinct()
    )
    high_risk_aircraft_ids = set(pred_result.scalars().all())

    aircraft_records = [
        {
            "id": ac.id,
            "tail_number": ac.tail_number,
            "aircraft_type": ac.aircraft_type,
            "squadron": ac.squadron,
            "current_status": ac.current_status,
            "has_high_risk": (ac.id in high_risk_aircraft_ids),
        }
        for ac in aircraft_models
    ]

    return compute_fleet_readiness(
        aircraft_records=aircraft_records,
        work_orders=work_orders,
    )
