from typing import Dict
from fastapi import APIRouter, Depends

from app.core.deps import require_roles
from app.db.models.user import User, UserRole

router = APIRouter()


@router.get("/admin-only")
async def admin_endpoint(user: User = Depends(require_roles(UserRole.ADMIN))) -> Dict[str, str]:
    return {"access": "granted", "role": user.role, "endpoint": "admin"}


@router.get("/commander-only")
async def commander_endpoint(user: User = Depends(require_roles(UserRole.COMMANDER))) -> Dict[str, str]:
    return {"access": "granted", "role": user.role, "endpoint": "commander"}


@router.get("/engineer-only")
async def engineer_endpoint(user: User = Depends(require_roles(UserRole.MAINTENANCE_ENGINEER))) -> Dict[str, str]:
    return {"access": "granted", "role": user.role, "endpoint": "engineer"}


@router.get("/logistics-only")
async def logistics_endpoint(user: User = Depends(require_roles(UserRole.LOGISTICS_OFFICER))) -> Dict[str, str]:
    return {"access": "granted", "role": user.role, "endpoint": "logistics"}


@router.get("/technician-only")
async def technician_endpoint(user: User = Depends(require_roles(UserRole.TECHNICIAN))) -> Dict[str, str]:
    return {"access": "granted", "role": user.role, "endpoint": "technician"}


@router.get("/auditor-only")
async def auditor_endpoint(user: User = Depends(require_roles(UserRole.AUDITOR))) -> Dict[str, str]:
    return {"access": "granted", "role": user.role, "endpoint": "auditor"}
