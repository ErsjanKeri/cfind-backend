"""Pydantic schemas for admin operations."""

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime

from app.schemas.base import BaseSchema
from app.core.security import validate_password_strength


# ============================================================================
# AGENT VERIFICATION
# ============================================================================

class AgentRejectRequest(BaseModel):
    """Request schema for rejecting agent."""

    rejection_reason: str = Field(..., min_length=10, max_length=500)

    model_config = {
        "json_schema_extra": {
            "example": {
                "rejection_reason": "License document is expired. Please upload a valid license and resubmit."
            }
        }
    }


class AgentVerificationResponse(BaseSchema):
    """Response schema for agent verification actions."""

    success: bool = True
    message: str
    agent_id: str
    verification_status: str


# ============================================================================
# USER MANAGEMENT (CREATE)
# ============================================================================

class AdminCreateAgentRequest(BaseModel):
    """Request schema for admin creating agent."""

    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return validate_password_strength(v)

    # Agent-specific fields
    operating_country: str = Field(..., min_length=2, max_length=2)
    company_name: str = Field(..., min_length=2, max_length=200)
    license_number: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=8, max_length=20)
    whatsapp: Optional[str] = Field(None, min_length=8, max_length=20)
    bio_en: Optional[str] = Field(None, max_length=1000)

    # Admin can pre-verify
    email_verified: bool = Field(default=True, description="Admin can bypass email verification")
    verification_status: str = Field(default="pending", pattern="^(pending|approved)$")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "New Agent",
                "email": "newagent@example.com",
                "password": "SecurePass123",
                "operating_country": "al",
                "company_name": "New Agency",
                "license_number": "LIC-2024-999",
                "phone": "+355691111111",
                "email_verified": True,
                "verification_status": "approved"
            }
        }
    }


class AdminCreateBuyerRequest(BaseModel):
    """Request schema for admin creating buyer."""

    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    company_name: Optional[str] = Field(None, max_length=200)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return validate_password_strength(v)

    # Admin can pre-verify
    email_verified: bool = Field(default=True)

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "New Buyer",
                "email": "newbuyer@example.com",
                "password": "SecurePass123",
                "company_name": "ABC Corp",
                "email_verified": True
            }
        }
    }


class AdminCreateUserResponse(BaseSchema):
    """Response schema for admin user creation."""

    success: bool = True
    message: str
    user_id: str
    email: str
    role: str


# ============================================================================
# USER MANAGEMENT (UPDATE)
# ============================================================================

class AdminToggleEmailVerificationRequest(BaseModel):
    """Request schema for toggling email verification."""

    email_verified: bool


class AdminToggleEmailVerificationResponse(BaseSchema):
    """Response schema for toggling email verification."""

    success: bool = True
    message: str
    user_id: str
    email_verified: bool


# ============================================================================
# PLATFORM STATISTICS
# ============================================================================

class PlatformStats(BaseModel):
    """Platform-wide statistics."""

    # Users
    total_users: int
    total_buyers: int
    total_agents: int
    total_admins: int

    # Agents by status
    agents_pending: int
    agents_approved: int
    agents_rejected: int

    # Listings
    total_listings: int
    active_listings: int
    draft_listings: int
    sold_listings: int
    inactive_listings: int

    # Leads & Demands
    total_leads: int
    total_demands: int
    active_demands: int
    assigned_demands: int
    fulfilled_demands: int

    # Promotions
    active_promotions: int
    total_credit_transactions: int


class PlatformStatsResponse(BaseSchema):
    """Response schema for platform statistics."""

    success: bool = True
    stats: PlatformStats


# ============================================================================
# USER LISTS
# ============================================================================

class UserListItem(BaseSchema):
    """User list item for admin dashboard."""

    id: str
    name: Optional[str] = None
    email: Optional[str] = None
    role: str
    email_verified: bool
    phone_number: Optional[str] = None
    company_name: Optional[str] = None
    image: Optional[str] = None
    created_at: datetime

    # Agent-specific (if role = agent)
    operating_country: Optional[str] = None
    verification_status: Optional[str] = None
    credit_balance: Optional[int] = None
    license_number: Optional[str] = None
    whatsapp_number: Optional[str] = None
    bio_en: Optional[str] = None
    license_document_url: Optional[str] = None
    company_document_url: Optional[str] = None
    id_document_url: Optional[str] = None


class AdminUsersListResponse(BaseSchema):
    """Response schema for admin users list."""

    success: bool = True
    total: int
    users: List[UserListItem]


# ============================================================================
# DELETE RESPONSES
# ============================================================================

class AdminDeleteResponse(BaseSchema):
    """Response schema for admin delete operations."""

    success: bool = True
    message: str
