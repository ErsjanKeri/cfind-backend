"""
Password reset flow.

Endpoints:
- POST /password-reset-request - Request password reset
- POST /password-reset - Reset password with token
"""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.db.session import get_db
from app.schemas.auth import (
    PasswordResetRequestRequest, PasswordResetRequestResponse,
    PasswordResetRequest as PasswordResetSchema, PasswordResetResponse,
)
from app.core.security import hash_password, generate_secure_token
from app.core.exceptions import TokenExpiredException, TokenAlreadyUsedException
from app.services.email_service import send_password_reset_email, send_password_changed_email
from app.repositories.user_repo import get_user_by_email, get_user_by_id
from app.repositories import auth_repo

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.post(
    "/password-reset-request",
    response_model=PasswordResetRequestResponse,
    summary="Request password reset",
    description="Send password reset link to user's email"
)
@limiter.limit("6/hour")
async def password_reset_request(
    request: Request,
    reset_request: PasswordResetRequestRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Request password reset.

    Rate limited to 3 requests per hour per IP.
    Rate limited to 3 requests per hour per user (database check).

    Always returns success (don't reveal if email exists).
    """
    # Find user
    user = await get_user_by_email(db, reset_request.email)

    # Always return success (security: don't reveal if email exists)
    if not user:
        return PasswordResetRequestResponse(
            success=True,
            message="If an account with that email exists, a password reset link has been sent."
        )

    # Check rate limit (max 3 requests per hour per user)
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent_count = await auth_repo.count_recent_password_reset_tokens(db, user.id, one_hour_ago)

    if recent_count >= 3:
        return PasswordResetRequestResponse(
            success=True,
            message="If an account with that email exists, a password reset link has been sent."
        )

    # Generate reset token (1-hour validity)
    token = generate_secure_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    await auth_repo.create_password_reset_token(db, user.id, token, expires)

    # Send reset email
    await send_password_reset_email(
        to_email=user.email,
        user_name=user.name,
        reset_token=token
    )

    return PasswordResetRequestResponse(
        success=True,
        message="If an account with that email exists, a password reset link has been sent."
    )


@router.post(
    "/password-reset",
    response_model=PasswordResetResponse,
    summary="Reset password",
    description="Reset user password using token from email"
)
async def password_reset(
    reset_data: PasswordResetSchema,
    db: AsyncSession = Depends(get_db)
):
    """
    Reset user password.

    After reset:
    1. Password updated with new hash
    2. Token marked as used
    3. Other reset tokens for user deleted
    4. All refresh tokens revoked (logout all sessions)
    5. Confirmation email sent
    """
    # Find reset token
    reset_token = await auth_repo.get_password_reset_token(db, reset_data.token)
    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid reset token."
        )

    # Check expiration
    if datetime.now(timezone.utc) > reset_token.expires:
        await db.delete(reset_token)
        raise TokenExpiredException("Password reset")

    # Check if already used
    if reset_token.used:
        raise TokenAlreadyUsedException()

    # Get user
    user = await get_user_by_id(db, str(reset_token.user_id), include_profiles=False)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    # Update password and mark token used
    user.password = hash_password(reset_data.new_password)
    reset_token.used = True
    reset_token.used_at = datetime.now(timezone.utc)

    # Delete other reset tokens and revoke all refresh tokens (logout all sessions)
    await auth_repo.delete_other_password_reset_tokens(db, user.id, reset_token.id)
    await auth_repo.revoke_all_user_refresh_tokens(db, user.id)

    # Send confirmation email
    await send_password_changed_email(
        to_email=user.email,
        user_name=user.name
    )

    return PasswordResetResponse(
        success=True,
        message="Password reset successfully! You can now log in with your new password."
    )
