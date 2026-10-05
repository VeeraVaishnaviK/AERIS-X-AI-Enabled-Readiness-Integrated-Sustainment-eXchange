from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()


@router.get("/ping")
async def ping() -> Dict[str, Any]:
    """Lightweight ping endpoint for liveness probes and phase gate validation."""
    return {
        "status": "ok",
        "service": "aeris-x-api",
        "version": settings.VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "synthetic_banner": settings.SYNTHETIC_DATA_BANNER,
    }


@router.get("/")
@router.get("/status")
async def system_status() -> Dict[str, Any]:
    """System health annunciator status for DATA LINK, AI ENGINE, DATABASE."""
    return {
        "status": "healthy",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "annunciators": {
            "data_link": {"status": "OPERATIONAL", "active": True},
            "ai_engine": {"status": "READY", "active": True},
            "database": {"status": "CONNECTED", "active": True},
        },
        "synthetic_data_banner": settings.SYNTHETIC_DATA_BANNER,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
