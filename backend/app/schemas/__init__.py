"""Pydantic v2 schemas for AERIS-X."""
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    TokenPayload,
)
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.schemas.quality import (
    SensorQualityDetail,
    DataQualityResult,
    ComponentHealthBreakdown,
    AircraftHealthResult,
)
from app.schemas.optimization import (
    ActionType,
    UrgencyLevel,
    FeasibilityStatus,
    RecommendationResult,
    FeasibilityCheckResult,
    MaintenanceTaskInput,
    ScheduleSlot,
    OptimizationResult,
    ReactiveComparisonResult,
    SimulationScenario,
    SimulationRequest,
    SimulationResult,
)
from app.schemas.readiness import (
    DailyForecast,
    SquadronReadiness,
    TypeReadiness,
    FleetReadinessOverview,
)

__all__ = [
    "LoginRequest",
    "TokenResponse",
    "RefreshTokenRequest",
    "TokenPayload",
    "UserCreate",
    "UserResponse",
    "UserUpdate",
    "SensorQualityDetail",
    "DataQualityResult",
    "ComponentHealthBreakdown",
    "AircraftHealthResult",
    "ActionType",
    "UrgencyLevel",
    "FeasibilityStatus",
    "RecommendationResult",
    "FeasibilityCheckResult",
    "MaintenanceTaskInput",
    "ScheduleSlot",
    "OptimizationResult",
    "ReactiveComparisonResult",
    "SimulationScenario",
    "SimulationRequest",
    "SimulationResult",
    "DailyForecast",
    "SquadronReadiness",
    "TypeReadiness",
    "FleetReadinessOverview",
]
