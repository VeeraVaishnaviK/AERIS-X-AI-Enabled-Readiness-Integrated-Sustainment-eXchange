from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.audit import AuditLog
from app.core.logging import get_logger

logger = get_logger("aeris.audit")


async def log_audit_event(
    session: AsyncSession,
    action: str,
    resource_type: str,
    resource_id: str,
    username: str = "system",
    role: str = "SYSTEM",
    user_id: Optional[int] = None,
    previous_value: Optional[Dict[str, Any]] = None,
    new_value: Optional[Dict[str, Any]] = None,
    ip_address: str = "127.0.0.1",
    user_agent: str = "AERIS-X Client",
) -> AuditLog:
    """Record an immutable audit log entry in the database."""
    entry = AuditLog(
        user_id=user_id,
        username=username,
        role=role,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        previous_value=previous_value or {},
        new_value=new_value or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(entry)
    await session.flush()
    logger.info(f"AUDIT: [{username}:{role}] {action} on {resource_type}:{resource_id}")
    return entry
