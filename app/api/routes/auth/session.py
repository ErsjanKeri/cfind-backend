"""
Session lifecycle.

Endpoints:
- POST /login - Authenticate user and issue JWT tokens
- POST /refresh - Refresh access token using refresh token
- POST /logout - Revoke refresh token and clear cookies
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.db.session import get_db
from app.models.user import User
from app.models.token import RefreshToken
from app.schemas.auth import (
    LoginRequest, LoginResponse,
    LogoutResponse, RefreshTokenResponse,
)
from app.schemas.user import UserResponse
from app.core.security import (
    verify_password,
    create_access_token, create_refresh_token, decode_token,
    generate_csrf_token,
)
from app.core.exceptions import EmailNotVerifiedException, InvalidCredentialsException
from app.api.deps import get_current_user, verify_csrf_token
from app.config import settings

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


# ============================================================================
# COOKIE HELPERS
# ============================================================================

def _set_auth_cookies(
    response: Response,
    access_token: str,
    csrf_token: str,
    refresh_token: str = None,
    refresh_max_age: int = None,
) -> None:
    """Set authentication cookies on the response."""
    is_production = settings.ENVIRONMENT == "production"
    cookie_domain = settings.cookie_domain

    # Access token (15 min, HTTPOnly)
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=900,
        httponly=True,
        secure=is_production,
        samesite="lax",
        domain=cookie_domain,
    )

    # CSRF token (non-HTTPOnly, readable by JavaScript)
    csrf_max_age = refresh_max_age if refresh_max_age else 604800
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        max_age=csrf_max_age,
        httponly=False,
        secure=is_production,
        samesite="lax",
        domain=cookie_domain,
    )

    # Refresh token (only on login, scoped to refresh endpoint)
    if refresh_token and refresh_max_age:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            max_age=refresh_max_age,
            httponly=True,
            secure=is_production,
            samesite="lax",
            path="/api/auth/refresh",
            domain=cookie_domain,
        )


def _clear_auth_cookies(response: Response) -> None:
    """Clear all authentication cookies."""
    cookie_domain = settings.cookie_domain
    response.delete_cookie("access_token", domain=cookie_domain)
    response.delete_cookie("refresh_token", path="/api/auth/refresh", domain=cookie_domain)
    response.delete_cookie("csrf_token", domain=cookie_domain)


# ============================================================================
# LOGIN
# ============================================================================

@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Login user",
    description="Authenticate user and issue JWT access + refresh tokens in HTTPOnly cookies"
)
@limiter.limit("5/minute")
async def login(
    request: Request,
    response: Response,
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate user and issue JWT tokens.

    On success:
    1. Access token set in HTTPOnly cookie (15 min expiry)
    2. Refresh token set in HTTPOnly cookie (7 or 30 days based on remember_me)
    3. CSRF token set in non-HTTPOnly cookie (readable by JavaScript)

    Email verification is strictly enforced.
    """
    # Find user
    result = await db.execute(
        select(User).where(User.email == credentials.email)
    )
    user = result.scalar_one_or_none()

    if not user or not user.password:
        raise InvalidCredentialsException()

    # Verify password
    is_valid, new_hash = verify_password(credentials.password, user.password)
    if not is_valid:
        raise InvalidCredentialsException()

    # Update password hash if parameters changed
    if new_hash:
        user.password = new_hash
        await db.commit()

    # Check email verification
    if not user.email_verified:
        raise EmailNotVerifiedException()

    # Generate tokens
    session_id = str(uuid.uuid4())
    csrf_token = generate_csrf_token()

    # Create access token
    access_token = create_access_token(
        subject=str(user.id),
        additional_claims={
            "email": user.email,
            "role": user.role,
            "name": user.name,
            "csrf": csrf_token
        }
    )

    # Create refresh token
    refresh_expires_delta = timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS_REMEMBER
        if credentials.remember_me
        else settings.REFRESH_TOKEN_EXPIRE_DAYS
    )

    refresh_token_value, jti = create_refresh_token(
        subject=str(user.id),
        session_id=session_id,
        expires_delta=refresh_expires_delta
    )

    # Store refresh token in database
    refresh_record = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        jti=jti,
        session_id=uuid.UUID(session_id),
        expires_at=datetime.now(timezone.utc) + refresh_expires_delta,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent")
    )
    db.add(refresh_record)
    await db.commit()

    # Set cookies
    refresh_max_age = int(refresh_expires_delta.total_seconds())
    _set_auth_cookies(response, access_token, csrf_token, refresh_token_value, refresh_max_age)

    return LoginResponse(
        success=True,
        message="Login successful",
        user=UserResponse.model_validate(user)
    )


# ============================================================================
# REFRESH TOKEN
# ============================================================================

@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
    summary="Refresh access token",
    description="Use refresh token to obtain new access token"
)
@limiter.limit("30/minute")
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh access token using refresh token.

    Validates refresh token from database (checks revocation).
    Issues new access token with fresh user data.
    """
    # Get refresh token from cookie
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing. Please log in again."
        )

    try:
        # Decode refresh token
        payload = decode_token(refresh_token)
        jti = payload.get("jti")
        user_id = payload.get("sub")

        # Verify token in database (check revocation)
        result = await db.execute(
            select(RefreshToken)
            .where(
                RefreshToken.jti == jti,
                RefreshToken.revoked == False,
                RefreshToken.expires_at > datetime.now(timezone.utc)
            )
        )
        token_record = result.scalar_one_or_none()

        if not token_record:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked refresh token. Please log in again."
            )

        # Fetch fresh user data from database
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found."
            )

        # Generate new tokens
        csrf_token = generate_csrf_token()

        new_access_token = create_access_token(
            subject=str(user.id),
            additional_claims={
                "email": user.email,
                "role": user.role,
                "name": user.name,
                "csrf": csrf_token
            }
        )

        # Set new cookies (no refresh token — only access + CSRF)
        _set_auth_cookies(response, new_access_token, csrf_token)

        return RefreshTokenResponse(
            success=True,
            message="Access token refreshed successfully"
        )

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token. Please log in again."
        )


# ============================================================================
# LOGOUT
# ============================================================================

@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="Logout user",
    description="Revoke refresh token and clear authentication cookies"
)
async def logout(
    request: Request,
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Logout user.

    1. Revokes refresh token in database
    2. Clears all authentication cookies
    """
    # Get refresh token from cookie
    refresh_token = request.cookies.get("refresh_token")

    if refresh_token:
        try:
            # Decode token to get jti
            payload = decode_token(refresh_token)
            jti = payload.get("jti")

            # Revoke token in database
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.jti == jti)
                .values(revoked=True, revoked_at=datetime.now(timezone.utc))
            )
            await db.commit()
        except Exception:
            # Ignore errors during logout
            pass

    # Clear cookies
    _clear_auth_cookies(response)

    return LogoutResponse(
        success=True,
        message="Logged out successfully"
    )
