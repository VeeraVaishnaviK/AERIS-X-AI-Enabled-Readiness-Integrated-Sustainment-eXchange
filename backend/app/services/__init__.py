"""AERIS-X services layer."""
from app.services.audit import log_audit_event
from app.services.data_quality import DataQualityEngine
from app.services.health_index import HealthIndexEngine
from app.services.recommend import generate_recommendation, get_recommended_spare
from app.services.feasibility import evaluate_feasibility_in_memory, check_feasibility_db
from app.services.optimize import MaintenanceOptimizer
from app.services.reactive_baseline import simulate_reactive_baseline
from app.services.simulate import run_maintenance_simulation
from app.services.readiness import compute_fleet_readiness, compute_fleet_readiness_db
from app.services.alerts import (
    evaluate_alert_rules,
    create_alert_db,
    update_alert_status_db,
    get_active_alerts_db,
)
from app.services.monitoring import (
    compute_evaluation_metrics,
    record_evaluation_to_db,
    get_latest_model_evaluations_db,
)
from app.services.telemetry_sim import (
    generate_arc_tick,
    stream_arc_generator,
)

__all__ = [
    "log_audit_event",
    "DataQualityEngine",
    "HealthIndexEngine",
    "generate_recommendation",
    "get_recommended_spare",
    "evaluate_feasibility_in_memory",
    "check_feasibility_db",
    "MaintenanceOptimizer",
    "simulate_reactive_baseline",
    "run_maintenance_simulation",
    "compute_fleet_readiness",
    "compute_fleet_readiness_db",
    "evaluate_alert_rules",
    "create_alert_db",
    "update_alert_status_db",
    "get_active_alerts_db",
    "compute_evaluation_metrics",
    "record_evaluation_to_db",
    "get_latest_model_evaluations_db",
    "generate_arc_tick",
    "stream_arc_generator",
]
