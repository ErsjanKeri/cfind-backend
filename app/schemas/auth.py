"""Pydantic schemas for authentication endpoints."""

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.base import BaseSchema
from app.schemas.user import UserResponse
from app.core.security import validate_password_strength


# ============================================================================
# REGISTRATION
# ============================================================================

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
    user: UserResponse


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
        return validate_password_strength(v)

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
