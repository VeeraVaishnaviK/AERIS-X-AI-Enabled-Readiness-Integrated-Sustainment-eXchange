from typing import Callable, List, Optional
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, ForbiddenError
from app.core.security import decode_token
from app.db.models.user import User, UserRole
from app.db.session import get_db

security_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate Bearer JWT token and retrieve active user from DB."""
    if not credentials:
        raise AuthError("Authentication token is missing. Please provide a Bearer token.")

    token = credentials.credentials
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise AuthError("Invalid token type. Expected access token.")
        user_id = payload.get("sub")
        if not user_id:
            raise AuthError("Token payload missing subject.")
    except JWTError as e:
        raise AuthError(f"Invalid or expired token: {str(e)}")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise AuthError("User associated with this token does not exist.")
    if not user.is_active:
        raise ForbiddenError("User account is inactive or disabled.")

    return user


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Retrieve user if token present and valid, otherwise None."""
    if not credentials:
        return None
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        result = await db.execute(select(User).where(User.id == int(user_id)))
        return result.scalar_one_or_none()
    except Exception:
        return None


def require_roles(*allowed_roles: str) -> Callable[[User], User]:
    """Dependency factory that enforces user role authorization."""
    role_values = [r.value if isinstance(r, UserRole) else str(r) for r in allowed_roles]

    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        # Superuser and ADMIN always have global operational override
        if current_user.is_superuser or current_user.role == UserRole.ADMIN.value:
            return current_user

        if current_user.role not in role_values:
            raise ForbiddenError(
                f"Role '{current_user.role}' is not authorized. Required: {', '.join(role_values)}"
            )
        return current_user

    return role_checker


def get_client_info(request: Request) -> dict:
    """Extract client IP and User-Agent from incoming request."""
    ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "Unknown Client")
    return {"ip_address": ip, "user_agent": user_agent}
