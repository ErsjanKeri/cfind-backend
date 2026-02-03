"""
Authentication routes.

Endpoints:
- POST /auth/register - Register new user (buyer or agent)
- POST /auth/login - Authenticate user and issue JWT tokens
- POST /auth/refresh - Refresh access token using refresh token
- POST /auth/logout - Revoke refresh token and clear cookies
- GET /auth/verify-email - Verify email address with token
- POST /auth/resend-verification - Resend verification email
- POST /auth/password-reset-request - Request password reset
- POST /auth/password-reset - Reset password with token
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, Response, Request, status
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.db.session import get_db
from app.models.user import User, AgentProfile  # BuyerProfile removed
from app.models.token import EmailVerificationToken, PasswordResetToken, RefreshToken
from app.schemas.auth import (
    RegisterRequest, RegisterResponse,
    LoginRequest, LoginResponse,
    VerifyEmailRequest, VerifyEmailResponse,
    ResendVerificationRequest, ResendVerificationResponse,
    PasswordResetRequestRequest, PasswordResetRequestResponse,
    PasswordResetRequest as PasswordResetSchema, PasswordResetResponse,
    LogoutResponse, RefreshTokenResponse
)
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
    generate_csrf_token, generate_secure_token
)
from app.core.exceptions import (
    EmailNotVerifiedException,
    InvalidCredentialsException,
    TokenExpiredException,
    TokenAlreadyUsedException,
)
from app.services.email_service import (
    send_verification_email,
    send_password_reset_email,
    send_password_changed_email
)
from app.api.deps import get_current_user, verify_csrf_token
from app.config import settings

# Initialize router
router = APIRouter(prefix="/auth", tags=["Authentication"])

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)


# ============================================================================
# REGISTRATION
# ============================================================================

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
    description="Register a new buyer or agent account. Sends email verification link."
)
@limiter.limit("3/hour")
async def register(
    request: Request,
    registration: RegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Register new user (buyer or agent).

    **Buyer registration**: Only requires name, email, password, role="buyer"

    **Agent registration**: Requires additional fields:
    - agency_name
    - license_number
    - phone
    - whatsapp (optional)
    - bio_en (optional)

    After registration:
    1. User created with emailVerified=false
    2. Profile created based on role
    3. Verification token generated (24-hour validity)
    4. Verification email sent

    User must verify email before logging in.
    """
    # Check if email already exists
    existing = await db.execute(
        select(User).where(User.email == registration.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered. Please use a different email or log in."
        )

    # Validate agent-specific fields
    if registration.role == "agent":
        if not registration.company_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Company name is required for agent registration"
            )
        if not registration.license_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="License number is required for agent registration"
            )
        if not registration.phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number is required for agent registration"
            )

    # Hash password
    hashed_password = hash_password(registration.password)

    # Create user
    user = User(
        id=uuid.uuid4(),
        name=registration.name,
        email=registration.email,
        password=hashed_password,
        role=registration.role,
        email_verified=False,
        # Common fields (for both buyers and agents)
        phone_number=registration.phone,
        company_name=registration.company_name,
    )
    db.add(user)
    await db.flush()  # Get user.id before creating profile

    # Create agent profile (if agent)
    if registration.role == "agent":
        agent_profile = AgentProfile(
            user_id=user.id,
            # agency_name REMOVED - using User.company_name
            # phone_number REMOVED - using User.phone_number
            license_number=registration.license_number,
            whatsapp_number=registration.whatsapp,
            bio_en=registration.bio_en,
            verification_status="pending"
        )
        db.add(agent_profile)
    elif registration.role == "buyer":
        # BuyerProfile removed - buyer fields are now in User table
        # No profile creation needed
        pass

    # Generate email verification token (24-hour validity)
    token = generate_secure_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=24)

    verification_token = EmailVerificationToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token=token,
        expires=expires
    )
    db.add(verification_token)

    await db.commit()

    # Send verification email
    await send_verification_email(
        to_email=user.email,
        user_name=user.name,
        verification_token=token
    )

    return RegisterResponse(
        success=True,
        message="Registration successful! Please check your email to verify your account.",
        user_id=str(user.id)
    )


# ============================================================================
# EMAIL VERIFICATION
# ============================================================================

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
    result = await db.execute(
        select(EmailVerificationToken)
        .where(EmailVerificationToken.token == token)
    )
    verification_token = result.scalar_one_or_none()

    if not verification_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid verification token."
        )

    # Check expiration
    if datetime.now(timezone.utc) > verification_token.expires:
        # Clean up expired token
        await db.delete(verification_token)
        await db.commit()
        raise TokenExpiredException("Email verification")

    # Get user
    result = await db.execute(
        select(User).where(User.id == verification_token.user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    # Mark email as verified
    user.email_verified = True

    # Delete verification token
    await db.delete(verification_token)

    await db.commit()

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
@limiter.limit("3/hour")
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
    result = await db.execute(
        select(User).where(User.email == resend_request.email)
    )
    user = result.scalar_one_or_none()

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

    # Delete old verification tokens for this user
    await db.execute(
        delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
    )

    # Generate new token
    token = generate_secure_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=24)

    verification_token = EmailVerificationToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token=token,
        expires=expires
    )
    db.add(verification_token)

    await db.commit()

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

    refresh_token, jti = create_refresh_token(
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
    is_production = settings.ENVIRONMENT == "production"
    cookie_domain = settings.cookie_domain  # .cfind.ai in production, None in dev

    # Access token cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=900,  # 15 minutes
        httponly=True,
        secure=is_production,
        samesite="lax",
        domain=cookie_domain
    )

    # Refresh token cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=int(refresh_expires_delta.total_seconds()),
        httponly=True,
        secure=is_production,
        samesite="lax",  # Changed from strict for cross-subdomain
        path="/api/auth/refresh",  # Only sent to refresh endpoint
        domain=cookie_domain
    )

    # CSRF token cookie (non-HTTPOnly for JavaScript access)
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        max_age=int(refresh_expires_delta.total_seconds()),
        httponly=False,  # JavaScript can read this
        secure=is_production,
        samesite="lax",  # Changed from strict for cross-subdomain
        domain=cookie_domain
    )

    return LoginResponse(
        success=True,
        message="Login successful",
        user={
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "email_verified": user.email_verified
        }
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

        # Set new cookies
        is_production = settings.ENVIRONMENT == "production"
        cookie_domain = settings.cookie_domain

        response.set_cookie(
            key="access_token",
            value=new_access_token,
            max_age=900,
            httponly=True,
            secure=is_production,
            samesite="lax",
            domain=cookie_domain
        )

        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            max_age=604800,  # 7 days
            httponly=False,
            secure=is_production,
            samesite="lax",
            domain=cookie_domain
        )

        return RefreshTokenResponse(
            success=True,
            message="Access token refreshed successfully"
        )

    except Exception as e:
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
        except:
            # Ignore errors during logout
            pass

    # Clear cookies (must specify domain for cross-subdomain)
    cookie_domain = settings.cookie_domain
    response.delete_cookie("access_token", domain=cookie_domain)
    response.delete_cookie("refresh_token", path="/api/auth/refresh", domain=cookie_domain)
    response.delete_cookie("csrf_token", domain=cookie_domain)

    return LogoutResponse(
        success=True,
        message="Logged out successfully"
    )


# ============================================================================
# PASSWORD RESET
# ============================================================================

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
