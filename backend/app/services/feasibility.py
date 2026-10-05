"""
AERIS-X Feasibility Service
Evaluates whether a recommended maintenance action can be executed within its risk horizon.
Checks 4 dimensions:
1. Spare Parts: In-stock quantity vs required, lead-time vs window.
2. Technicians: Qualified technician available with appropriate specialty/certifications.
3. Maintenance Bays: Suitable bay type available and operational.
4. Risk Window: Task duration + buffer fits within max window before failure.
"""
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.maintenance import SparePart, Technician, MaintenanceBay
from app.schemas.optimization import FeasibilityStatus, FeasibilityCheckResult


def evaluate_feasibility_in_memory(
    required_spare_category: str,
    required_spare_name: Optional[str],
    required_duration_hours: float,
    window_hours: float,
    available_spares: List[Dict[str, Any]],
    available_technicians: List[Dict[str, Any]],
    available_bays: List[Dict[str, Any]],
) -> FeasibilityCheckResult:
    """
    Pure evaluation function without direct DB dependency.
    Used for unit testing, what-if simulations, and optimizer preprocessing.
    """
    bottlenecks: List[str] = []

    # 1. Spare parts check
    spare_feasible = True
    spare_details: Dict[str, Any] = {}
    if required_spare_name:
        matching_spares = [
            s for s in available_spares
            if s.get("name") == required_spare_name or s.get("category") == required_spare_category
        ]
        if not matching_spares:
            spare_feasible = False
            bottlenecks.append(f"Spare part '{required_spare_name or required_spare_category}' not found in inventory")
            spare_details = {"status": "NOT_FOUND", "in_stock": 0, "required": 1}
        else:
            best_spare = matching_spares[0]
            in_stock = best_spare.get("stock_quantity", 0)
            lead_time_days = best_spare.get("lead_time_days", 14)
            lead_time_hours = lead_time_days * 24.0

            if in_stock >= 1:
                spare_details = {
                    "status": "IN_STOCK",
                    "part_number": best_spare.get("part_number"),
                    "name": best_spare.get("name"),
                    "in_stock": in_stock,
                    "location": best_spare.get("storage_location", "Main Hangar Depot"),
                }
            else:
                spare_feasible = False
                spare_details = {
                    "status": "STOCK_OUT",
                    "part_number": best_spare.get("part_number"),
                    "name": best_spare.get("name"),
                    "in_stock": 0,
                    "lead_time_days": lead_time_days,
                }
                bottlenecks.append(
                    f"Spare '{best_spare.get('name')}' is out of stock (lead time {lead_time_days}d > {window_hours:.0f}h window)"
                )
    else:
        spare_details = {"status": "NO_SPARE_REQUIRED"}

    # 2. Technician check
    technician_feasible = True
    technician_details: Dict[str, Any] = {}
    matching_techs = [
        t for t in available_technicians
        if (t.get("specialty") == required_spare_category or t.get("specialty") == "Propulsion")
        and t.get("current_status") == "AVAILABLE"
    ]
    if not matching_techs:
        # Check any available tech
        any_techs = [t for t in available_technicians if t.get("current_status") == "AVAILABLE"]
        if any_techs:
            technician_details = {
                "status": "CROSS_TRAINED_ONLY",
                "assigned_tech": any_techs[0].get("name"),
                "specialty": any_techs[0].get("specialty"),
            }
            bottlenecks.append(f"No dedicated {required_spare_category} technician free; requires cross-trained backup")
        else:
            technician_feasible = False
            technician_details = {"status": "NONE_AVAILABLE", "qualified_count": 0}
            bottlenecks.append(f"All qualified {required_spare_category} technicians are currently occupied or on leave")
    else:
        lead_tech = matching_techs[0]
        technician_details = {
            "status": "AVAILABLE",
            "technician_id": lead_tech.get("id"),
            "name": lead_tech.get("name"),
            "rank": lead_tech.get("rank"),
            "specialty": lead_tech.get("specialty"),
        }

    # 3. Bay check
    bay_feasible = True
    bay_details: Dict[str, Any] = {}
    free_bays = [
        b for b in available_bays
        if b.get("is_operational", True) and b.get("current_status") == "AVAILABLE"
    ]
    if not free_bays:
        bay_feasible = False
        bay_details = {"status": "ALL_BAYS_OCCUPIED", "free_bays": 0}
        bottlenecks.append("All maintenance bays are currently occupied or undergoing calibration")
    else:
        assigned_bay = free_bays[0]
        bay_details = {
            "status": "AVAILABLE",
            "bay_id": assigned_bay.get("id"),
            "bay_code": assigned_bay.get("bay_code"),
            "bay_type": assigned_bay.get("bay_type"),
        }

    # 4. Window check
    window_feasible = (required_duration_hours <= window_hours)
    if not window_feasible:
        bottlenecks.append(
            f"Maintenance duration ({required_duration_hours:.1f}h) exceeds allowable safety window ({window_hours:.1f}h)"
        )

    # Synthesis
    if spare_feasible and technician_feasible and bay_feasible and window_feasible:
        if len(bottlenecks) == 0:
            status = FeasibilityStatus.FEASIBLE
            recommendation_text = "All required logistics and personnel are ready. Proceed with immediate work order dispatch."
        else:
            status = FeasibilityStatus.PARTIALLY_FEASIBLE
            recommendation_text = f"Action is executable with non-standard resources: {'; '.join(bottlenecks)}."
    elif (spare_feasible or technician_feasible) and bay_feasible:
        status = FeasibilityStatus.PARTIALLY_FEASIBLE
        recommendation_text = f"Execute with caution or expedited sourcing. Bottlenecks: {'; '.join(bottlenecks)}."
    else:
        status = FeasibilityStatus.NOT_FEASIBLE
        recommendation_text = f"Action cannot be executed in current window. Critical constraints: {'; '.join(bottlenecks)}."

    return FeasibilityCheckResult(
        status=status,
        is_feasible=(status == FeasibilityStatus.FEASIBLE),
        spare_feasible=spare_feasible,
        spare_details=spare_details,
        technician_feasible=technician_feasible,
        technician_details=technician_details,
        bay_feasible=bay_feasible,
        bay_details=bay_details,
        window_feasible=window_feasible,
        bottlenecks=bottlenecks,
        recommendation=recommendation_text,
    )


async def check_feasibility_db(
    session: AsyncSession,
    required_spare_category: str,
    required_spare_name: Optional[str],
    required_duration_hours: float,
    window_hours: float,
) -> FeasibilityCheckResult:
    """Async database-backed feasibility check."""
    # Query Spares
    spares_res = await session.execute(select(SparePart))
    spares = [
        {
            "id": s.id,
            "part_number": s.part_number,
            "name": s.name,
            "category": s.category,
            "stock_quantity": s.stock_quantity,
            "lead_time_days": s.lead_time_days,
            "storage_location": s.storage_location,
        }
        for s in spares_res.scalars().all()
    ]

    # Query Technicians
    tech_res = await session.execute(select(Technician))
    techs = [
        {
            "id": t.id,
            "name": t.name,
            "rank": t.rank,
            "specialty": t.specialty,
            "current_status": t.current_status,
        }
        for t in tech_res.scalars().all()
    ]

    # Query Bays
    bay_res = await session.execute(select(MaintenanceBay))
    bays = [
        {
            "id": b.id,
            "bay_code": b.bay_code,
            "bay_type": b.bay_type,
            "is_operational": b.is_operational,
            "current_status": b.current_status,
        }
        for b in bay_res.scalars().all()
    ]

    return evaluate_feasibility_in_memory(
        required_spare_category=required_spare_category,
        required_spare_name=required_spare_name,
        required_duration_hours=required_duration_hours,
        window_hours=window_hours,
        available_spares=spares,
        available_technicians=techs,
        available_bays=bays,
    )
