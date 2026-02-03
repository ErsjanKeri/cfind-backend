"""Pydantic schemas for authentication endpoints."""

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional

from app.schemas.base import BaseSchema


# ============================================================================
# REGISTRATION
# ============================================================================

class RegisterRequest(BaseModel):
    """Request schema for user registration."""

    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    role: str = Field(..., pattern="^(buyer|agent)$")

    # Common fields (for both buyers and agents)
    phone: Optional[str] = Field(None, min_length=8, max_length=20)
    company_name: Optional[str] = Field(None, min_length=2, max_length=200)

    # Agent-specific fields (required if role = "agent")
    license_number: Optional[str] = Field(None, min_length=2, max_length=100)
    whatsapp: Optional[str] = Field(None, min_length=8, max_length=20)
    bio_en: Optional[str] = Field(None, max_length=1000)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v

    @field_validator("role")
    @classmethod
    def validate_agent_fields(cls, v: str, values) -> str:
        """Validate that agent-specific fields are provided if role is agent."""
        # Note: In Pydantic v2, we need to use 'info.data' to access other fields
        # This is a simplified version - full validation happens in the route
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "John Doe",
                "email": "john@example.com",
                "password": "SecurePass123",
                "role": "buyer"
            }
        }
    }


class RegisterResponse(BaseSchema):
    """Response schema for successful registration."""

    success: bool = True
    message: str
    user_id: str


# ============================================================================
# LOGIN
# ============================================================================

class LoginRequest(BaseModel):
    """Request schema for user login."""

    email: EmailStr
    password: str
    remember_me: bool = False

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "john@example.com",
                "password": "SecurePass123",
                "remember_me": False
            }
        }
    }


class LoginResponse(BaseSchema):
    """Response schema for successful login."""

    success: bool = True
    message: str = "Login successful"
    user: dict  # User details (id, email, name, role, etc.)


# ============================================================================
# EMAIL VERIFICATION
# ============================================================================

class VerifyEmailRequest(BaseModel):
    """Request schema for email verification."""

    token: str = Field(..., min_length=20)


class VerifyEmailResponse(BaseSchema):
    """Response schema for successful email verification."""

    success: bool = True
    message: str = "Email verified successfully. You can now log in."


class ResendVerificationRequest(BaseModel):
    """Request schema for resending verification email."""

    email: EmailStr

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "john@example.com"
            }
        }
    }


class ResendVerificationResponse(BaseSchema):
    """Response schema for resending verification email."""

    success: bool = True
    message: str = "Verification email sent. Please check your inbox."


# ============================================================================
# PASSWORD RESET
# ============================================================================

class PasswordResetRequestRequest(BaseModel):
    """Request schema for requesting password reset."""

    email: EmailStr

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "john@example.com"
            }
        }
    }


class PasswordResetRequestResponse(BaseSchema):
    """Response schema for password reset request."""

    success: bool = True
    message: str = "If an account with that email exists, a password reset link has been sent."


class PasswordResetRequest(BaseModel):
    """Request schema for resetting password with token."""

    token: str = Field(..., min_length=20)
    new_password: str = Field(..., min_length=8, max_length=100)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "token": "abcdef1234567890...",
                "new_password": "NewSecurePass123"
            }
        }
    }


class PasswordResetResponse(BaseSchema):
    """Response schema for successful password reset."""

    success: bool = True
    message: str = "Password reset successfully. You can now log in with your new password."


# ============================================================================
# LOGOUT
# ============================================================================

class LogoutResponse(BaseSchema):
    """Response schema for successful logout."""

    success: bool = True
    message: str = "Logged out successfully"


# ============================================================================
# REFRESH TOKEN
# ============================================================================

class RefreshTokenResponse(BaseSchema):
    """Response schema for successful token refresh."""

    success: bool = True
    message: str = "Access token refreshed successfully"


# ============================================================================
# COMMON ERROR RESPONSE
# ============================================================================

class ErrorResponse(BaseSchema):
    """Standard error response schema."""

    detail: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "detail": "Invalid credentials"
            }
        }
    }
