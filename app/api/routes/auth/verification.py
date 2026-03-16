"""
Email verification.

Endpoints:
- GET /verify-email - Verify email address with token
- POST /resend-verification - Resend verification email
"""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.db.session import get_db
from app.schemas.auth import (
    VerifyEmailResponse,
    ResendVerificationRequest, ResendVerificationResponse,
)
from app.core.security import generate_secure_token
from app.core.exceptions import TokenExpiredException
from app.services.email_service import send_verification_email
from app.repositories.user_repo import get_user_by_email, get_user_by_id
from app.repositories import auth_repo

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.get(
    "/verify-email",
    response_model=VerifyEmailResponse,
    summary="Verify email address",
    description="Verify user's email address using token from email link"
)
async def verify_email(
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify user's email address.

    After verification:
    1. User's emailVerified flag set to true
    2. Verification token deleted
    3. User can now log in
    """
    # Find verification token
    verification_token = await auth_repo.get_verification_token(db, token)
    if not verification_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid verification token."
        )

    # Check expiration
    if datetime.now(timezone.utc) > verification_token.expires:
        await db.delete(verification_token)
        raise TokenExpiredException("Email verification")

    # Get user
    user = await get_user_by_id(db, str(verification_token.user_id), include_profiles=False)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    # Mark email as verified and delete token
    user.email_verified = True
    await db.delete(verification_token)

    return VerifyEmailResponse(
        success=True,
        message="Email verified successfully! You can now log in."
    )


@router.post(
    "/resend-verification",
    response_model=ResendVerificationResponse,
    summary="Resend verification email",
    description="Resend email verification link"
)
@limiter.limit("6/hour")
async def resend_verification(
    request: Request,
    resend_request: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Resend email verification link.

    Rate limited to 3 requests per hour per IP.
    """
    # Find user
    user = await get_user_by_email(db, resend_request.email)

    # Always return success (don't reveal if email exists)
    if not user:
        return ResendVerificationResponse(
            success=True,
            message="If an account with that email exists and is unverified, a verification email has been sent."
        )

    # Check if already verified
    if user.email_verified:
        return ResendVerificationResponse(
            success=True,
            message="Email is already verified. You can log in."
        )

    # Delete old verification tokens and create new one
    await auth_repo.delete_user_verification_tokens(db, user.id)

    token = generate_secure_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    await auth_repo.create_verification_token(db, user.id, token, expires)

    # Send verification email
    await send_verification_email(
        to_email=user.email,
        user_name=user.name,
        verification_token=token
    )

    return ResendVerificationResponse(
        success=True,
        message="Verification email sent! Please check your inbox."
    )
