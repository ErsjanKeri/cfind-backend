"""Token models for authentication (email verification, password reset, refresh tokens)."""

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base


class EmailVerificationToken(Base):
    """
    Email verification token model.

    Lifetime: 24 hours
    Single-use: Deleted after successful verification
    """

    __tablename__ = "email_verification_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String, unique=True, nullable=False)
    expires = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="email_verification_tokens")

    def __repr__(self):
        return f"<EmailVerificationToken(id={self.id}, user_id={self.user_id}, expires={self.expires})>"


class PasswordResetToken(Base):
    """
    Password reset token model.

    Lifetime: 1 hour
    Single-use: Marked as used after successful reset
    Rate limit: Max 3 requests per hour per user
    """

    __tablename__ = "password_reset_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String, unique=True, nullable=False)
    expires = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="password_reset_tokens")

    def __repr__(self):
        return f"<PasswordResetToken(id={self.id}, user_id={self.user_id}, used={self.used})>"


class RefreshToken(Base):
    """
    JWT refresh token model for FastAPI authentication.

    Purpose:
    - Database-backed refresh tokens for revocation capability
    - Long-lived (7-30 days depending on "remember me")
    - Used to obtain new access tokens
    - Can be revoked (logout, password change, admin action)

    Lifetime:
    - Default: 7 days
    - Remember me: 30 days

    Security:
    - Each token has unique jti (JWT ID) for revocation
    - Session tracking via session_id
    - IP address and user agent logged for security audit
    - All tokens revoked on password change
    """

    __tablename__ = "refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # JWT ID (jti claim) - used for token identification and revocation
    jti = Column(String(255), unique=True, nullable=False, index=True)

    # Session tracking - multiple refresh tokens per user (multi-device support)
    session_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Token lifecycle
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Revocation tracking
    revoked = Column(Boolean, default=False, nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    # Security metadata
    ip_address = Column(String(45), nullable=True)  # IPv6 max length
    user_agent = Column(String, nullable=True)

    def __repr__(self):
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, revoked={self.revoked})>"
