from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request
from jose import JWTError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_client_info, get_current_user
from app.core.errors import AuthError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RefreshTokenRequest, TokenResponse
from app.schemas.user import UserResponse
from app.services.audit import log_audit_event

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate user with username or email, issue JWT tokens, and log audit event."""
    client_info = get_client_info(request)

    # Find user by username or email
    query = select(User).where(
        or_(
            User.username == payload.username_or_email,
            User.email == payload.username_or_email,
        )
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        await log_audit_event(
            session=db,
            action="LOGIN_FAILED",
            resource_type="auth",
            resource_id=payload.username_or_email,
            username=payload.username_or_email,
            role="ANONYMOUS",
            ip_address=client_info["ip_address"],
            user_agent=client_info["user_agent"],
            new_value={"reason": "Invalid credentials"},
        )
        await db.commit()
        raise AuthError("Invalid username/email or password.")

    if not user.is_active:
        raise AuthError("User account is inactive.")

    # Update last login
    user.last_login = datetime.now(timezone.utc)
    access_token = create_access_token(subject=user.id, role=user.role)
    refresh_token = create_refresh_token(subject=user.id, role=user.role)

    await log_audit_event(
        session=db,
        action="LOGIN_SUCCESS",
        resource_type="auth",
        resource_id=str(user.id),
        username=user.username,
        role=user.role,
        user_id=user.id,
        ip_address=client_info["ip_address"],
        user_agent=client_info["user_agent"],
    )
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user_id=user.id,
        username=user.username,
        role=user.role,
        full_name=user.full_name,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Issue a new access token using a valid refresh token."""
    try:
        decoded = decode_token(payload.refresh_token)
        if decoded.get("type") != "refresh":
            raise AuthError("Invalid token type. Expected refresh token.")
        user_id = decoded.get("sub")
        if not user_id:
            raise AuthError("Token missing subject.")
    except JWTError as e:
        raise AuthError(f"Invalid refresh token: {str(e)}")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise AuthError("User does not exist or is inactive.")

    new_access_token = create_access_token(subject=user.id, role=user.role)
    new_refresh_token = create_refresh_token(subject=user.id, role=user.role)

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        user_id=user.id,
        username=user.username,
        role=user.role,
        full_name=user.full_name,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Retrieve the currently authenticated user's profile and active role."""
    return UserResponse.model_validate(current_user)


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Log user sign-out in audit logs."""
    client_info = get_client_info(request)
    await log_audit_event(
        session=db,
        action="LOGOUT",
        resource_type="auth",
        resource_id=str(current_user.id),
        username=current_user.username,
        role=current_user.role,
        user_id=current_user.id,
        ip_address=client_info["ip_address"],
        user_agent=client_info["user_agent"],
    )
    await db.commit()
    return {"message": "Successfully logged out.", "status": "ok"}
