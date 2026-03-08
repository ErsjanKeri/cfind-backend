"""
Auth repository - database operations for authentication tokens.

Handles:
- Refresh token storage, validation, and revocation
- Email verification tokens
- Password reset tokens
"""

import uuid
import logging
from typing import Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, func

from app.models.token import RefreshToken, EmailVerificationToken, PasswordResetToken

logger = logging.getLogger(__name__)


async def store_refresh_token(
    db: AsyncSession,
    user_id,
    jti: str,
    session_id,
    expires_at: datetime,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> RefreshToken:
    """Store a new refresh token in the database."""
    record = RefreshToken(
        id=uuid.uuid4(),
        user_id=user_id,
        jti=jti,
        session_id=session_id,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(record)
    await db.flush()
    return record


async def get_valid_refresh_token(
    db: AsyncSession,
    jti: str,
) -> Optional[RefreshToken]:
    """Find a non-revoked, non-expired refresh token by jti."""
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.jti == jti,
            RefreshToken.revoked == False,
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    return result.scalar_one_or_none()


async def revoke_refresh_token(db: AsyncSession, jti: str) -> None:
    """Revoke a single refresh token by jti."""
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.jti == jti)
        .values(revoked=True, revoked_at=datetime.now(timezone.utc))
    )


async def revoke_all_user_refresh_tokens(db: AsyncSession, user_id) -> None:
    """Revoke all active refresh tokens for a user (e.g. on password change)."""
    await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked == False,
        )
        .values(revoked=True, revoked_at=datetime.now(timezone.utc))
    )


async def get_verification_token(
    db: AsyncSession,
    token: str,
) -> Optional[EmailVerificationToken]:
    """Find an email verification token by token string."""
    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token == token
        )
    )
    return result.scalar_one_or_none()


async def create_verification_token(
    db: AsyncSession,
    user_id,
    token: str,
    expires: datetime,
) -> EmailVerificationToken:
    """Create a new email verification token."""
    record = EmailVerificationToken(
        id=uuid.uuid4(),
        user_id=user_id,
        token=token,
        expires=expires,
    )
    db.add(record)
    await db.flush()
    return record


async def delete_user_verification_tokens(db: AsyncSession, user_id) -> None:
    """Delete all verification tokens for a user."""
    await db.execute(
        delete(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user_id
        )
    )


async def get_password_reset_token(
    db: AsyncSession,
    token: str,
) -> Optional[PasswordResetToken]:
    """Find a password reset token by token string."""
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token == token
        )
    )
    return result.scalar_one_or_none()


async def create_password_reset_token(
    db: AsyncSession,
    user_id,
    token: str,
    expires: datetime,
) -> PasswordResetToken:
    """Create a new password reset token."""
    record = PasswordResetToken(
        id=uuid.uuid4(),
        user_id=user_id,
        token=token,
        expires=expires,
        used=False,
    )
    db.add(record)
    await db.flush()
    return record


async def count_recent_password_reset_tokens(
    db: AsyncSession,
    user_id,
    since: datetime,
) -> int:
    """Count password reset tokens created since a given time."""
    result = await db.execute(
        select(func.count())
        .select_from(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.created_at > since,
        )
    )
    return result.scalar()


async def delete_other_password_reset_tokens(
    db: AsyncSession,
    user_id,
    except_id,
) -> None:
    """Delete all password reset tokens for a user except the given one."""
    await db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.id != except_id,
        )
    )
