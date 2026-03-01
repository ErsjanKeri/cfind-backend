"""
Password reset flow.

Endpoints:
- POST /password-reset-request - Request password reset
- POST /password-reset - Reset password with token
"""

import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.db.session import get_db
from app.models.user import User
from app.models.token import PasswordResetToken, RefreshToken
from app.schemas.auth import (
    PasswordResetRequestRequest, PasswordResetRequestResponse,
    PasswordResetRequest as PasswordResetSchema, PasswordResetResponse,
)
from app.core.security import hash_password, generate_secure_token
from app.core.exceptions import TokenExpiredException, TokenAlreadyUsedException
from app.services.email_service import send_password_reset_email, send_password_changed_email

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.post(
    "/password-reset-request",
    response_model=PasswordResetRequestResponse,
    summary="Request password reset",
    description="Send password reset link to user's email"
)
@limiter.limit("3/hour")
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
    result = await db.execute(
        select(User).where(User.email == reset_request.email)
    )
    user = result.scalar_one_or_none()

    # Always return success (security: don't reveal if email exists)
    if not user:
        return PasswordResetRequestResponse(
            success=True,
            message="If an account with that email exists, a password reset link has been sent."
        )

    # Check rate limit (max 3 requests per hour per user)
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    result = await db.execute(
        select(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.created_at > one_hour_ago
        )
    )
    recent_tokens = result.scalars().all()

    if len(recent_tokens) >= 3:
        # Rate limit exceeded, but still return success (security)
        return PasswordResetRequestResponse(
            success=True,
            message="If an account with that email exists, a password reset link has been sent."
        )

    # Generate reset token (1-hour validity)
    token = generate_secure_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=1)

    reset_token = PasswordResetToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token=token,
        expires=expires,
        used=False
    )
    db.add(reset_token)
    await db.commit()

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
    result = await db.execute(
        select(PasswordResetToken)
        .where(PasswordResetToken.token == reset_data.token)
    )
    reset_token = result.scalar_one_or_none()

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid reset token."
        )

    # Check expiration
    if datetime.now(timezone.utc) > reset_token.expires:
        await db.delete(reset_token)
        await db.commit()
        raise TokenExpiredException("Password reset")

    # Check if already used
    if reset_token.used:
        raise TokenAlreadyUsedException()

    # Get user
    result = await db.execute(
        select(User).where(User.id == reset_token.user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    # Hash new password
    hashed_password = hash_password(reset_data.new_password)

    # Update password and mark token used (atomic transaction)
    user.password = hashed_password
    reset_token.used = True
    reset_token.used_at = datetime.now(timezone.utc)

    # Delete other reset tokens for this user
    await db.execute(
        delete(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.id != reset_token.id
        )
    )

    # Revoke all refresh tokens (logout all sessions)
    await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked == False
        )
        .values(revoked=True, revoked_at=datetime.now(timezone.utc))
    )

    await db.commit()

    # Send confirmation email
    await send_password_changed_email(
        to_email=user.email,
        user_name=user.name
    )

    return PasswordResetResponse(
        success=True,
        message="Password reset successfully! You can now log in with your new password."
    )
