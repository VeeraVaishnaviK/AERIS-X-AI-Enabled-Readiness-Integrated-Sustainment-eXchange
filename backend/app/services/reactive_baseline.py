"""
AERIS-X Reactive Maintenance Baseline
Simulates run-to-failure (corrective/reactive) maintenance policy to contrast with
AERIS-X predictive CP-SAT optimization.

In a reactive paradigm:
- Maintenance occurs only AFTER catastrophic or in-service failure.
- In-service failures cause emergency grounding (NMC).
- Secondary damage increases downtime hours by 2.5x - 3.5x.
- Emergency parts logistics incur severe expediting delays and high costs.
- Bay and technician contention results in long maintenance queues.
"""
from typing import Any, Dict, List
from app.schemas.optimization import (
    MaintenanceTaskInput,
    OptimizationResult,
    ReactiveComparisonResult,
)


def simulate_reactive_baseline(
    tasks: List[MaintenanceTaskInput],
    optimized_result: OptimizationResult,
    fleet_size: int = 30,
) -> ReactiveComparisonResult:
    """
    Simulate reactive run-to-failure baseline and generate side-by-side comparison.
    """
    # Under reactive maintenance:
    # 1. High and Critical tasks fail in-service
    # 2. Downtime penalty is 2.8x higher per event due to secondary teardown & inspection
    # 3. Aircraft are grounded unexpectedly
    critical_or_high_tasks = [
        t for t in tasks if t.risk_level.upper() in ["CRITICAL", "HIGH"]
    ]
    medium_tasks = [
        t for t in tasks if t.risk_level.upper() == "MEDIUM"
    ]

    unpredicted_groundings = len(critical_or_high_tasks)

    # Base downtime for predictive
    opt_downtime = optimized_result.total_downtime_hours
    opt_avail = optimized_result.availability_after

    # Reactive downtime calculation
    # Secondary damage multiplier: 2.8x for critical/high, 1.8x for medium
    reactive_downtime = sum(
        t.duration_hours * 2.8 for t in critical_or_high_tasks
    ) + sum(
        t.duration_hours * 1.8 for t in medium_tasks
    )

    # Under reactive baseline, grounded aircraft remain down for prolonged periods
    # Fleet availability drops drastically
    reactive_unavailable_count = unpredicted_groundings + (len(medium_tasks) * 0.5)
    reactive_avail = max(
        35.0,
        round(((fleet_size - reactive_unavailable_count) / fleet_size) * 100.0, 1),
    )

    # Downtime reduction %
    if reactive_downtime > 0:
        downtime_reduction = max(
            0.0,
            round(((reactive_downtime - opt_downtime) / reactive_downtime) * 100.0, 1),
        )
    else:
        downtime_reduction = 0.0

    # Cost savings: INR ₹1,200,000 per avoided emergency grounding + ₹150,000 per hour saved
    hours_saved = max(0.0, reactive_downtime - opt_downtime)
    cost_savings = (unpredicted_groundings * 1_200_000.0) + (hours_saved * 150_000.0)

    summary = (
        f"AERIS-X predictive optimization achieves {opt_avail:.1f}% availability "
        f"vs {reactive_avail:.1f}% under reactive maintenance (+{round(opt_avail - reactive_avail, 1)}% uplift). "
        f"Avoided {unpredicted_groundings} unpredicted combat fleet groundings and reduced downtime by "
        f"{downtime_reduction:.1f}% ({hours_saved:.1f} hours saved)."
    )

    return ReactiveComparisonResult(
        reactive_availability=reactive_avail,
        optimized_availability=opt_avail,
        reactive_downtime_hours=round(reactive_downtime, 1),
        optimized_downtime_hours=round(opt_downtime, 1),
        unpredicted_groundings_avoided=unpredicted_groundings,
        downtime_reduction_pct=downtime_reduction,
        cost_savings_estimate_inr=cost_savings,
        summary=summary,
    )
