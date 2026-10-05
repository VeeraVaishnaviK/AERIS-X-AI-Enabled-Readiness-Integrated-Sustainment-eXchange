"""API v1 router registry."""
from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.rbac_test import router as rbac_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["Health & System"])
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication & RBAC"])
api_router.include_router(rbac_router, prefix="/rbac", tags=["RBAC Validation"])
