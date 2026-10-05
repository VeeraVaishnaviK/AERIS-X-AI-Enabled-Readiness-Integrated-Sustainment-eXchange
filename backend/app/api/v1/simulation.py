"""
AERIS-X Simulation API Router
Provides live telemetry simulation control and scenario triggering.
"""
from fastapi import APIRouter, HTTPException, status
from app.schemas.simulation_stream import LiveSimulationStartRequest, TelemetryTick
from app.services.telemetry_sim import generate_arc_tick

router = APIRouter()


@router.post("/live/start", response_model=dict, status_code=status.HTTP_200_OK)
async def start_live_simulation(request: LiveSimulationStartRequest):
    """
    Initiates a live operational simulation arc for an aircraft.
    Emits initial tick and confirms streaming readiness via /ws/telemetry.
    """
    initial_tick = generate_arc_tick(
        tick_number=1,
        aircraft_id=request.aircraft_id,
        total_ticks=request.total_ticks,
    )
    return {
        "status": "STARTED",
        "aircraft_id": request.aircraft_id,
        "websocket_endpoint": "/ws/telemetry",
        "total_ticks": request.total_ticks,
        "interval_ms": request.tick_interval_ms,
        "initial_tick": initial_tick.model_dump(mode="json"),
    }
