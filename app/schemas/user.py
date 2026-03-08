"""Pydantic schemas for user profile operations."""

from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime

from app.schemas.base import BaseSchema


# ============================================================================
# USER RESPONSE
# ============================================================================

class AgentProfileResponse(BaseSchema):
    """Agent profile response schema."""

    user_id: str
    operating_country: Optional[str] = None
    license_number: Optional[str] = None
    whatsapp_number: Optional[str] = None
    bio_en: Optional[str] = None

    # Documents
    license_document_url: Optional[str] = None
    company_document_url: Optional[str] = None
    id_document_url: Optional[str] = None

    # Verification
    verification_status: str  # "pending" | "approved" | "rejected"
    verified_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    rejected_at: Optional[datetime] = None
    rejected_by: Optional[str] = None
    submitted_at: Optional[datetime] = None

    # Stats
    listings_count: int = 0
    deals_completed: int = 0
    credit_balance: int = 0

    # ✅ UUID serialization handled by BaseSchema - no manual serializer needed!



class UserResponse(BaseSchema):
    """User response schema (includes role-specific profile)."""

    id: str
    name: Optional[str] = None
    email: Optional[str] = None
    email_verified: bool
    image: Optional[str] = None
    role: str  # "buyer" | "agent" | "admin"
    country_preference: Optional[str] = None

    # Common fields (for both buyers and agents)
    phone_number: Optional[str] = None
    company_name: Optional[str] = None
    website: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    # Agent profile (only for agents)
    agent_profile: Optional[AgentProfileResponse] = None

    # ✅ UUID serialization handled by BaseSchema - no manual serializer needed!


# ============================================================================
# USER PROFILE UPDATE
# ============================================================================

class UserProfileUpdate(BaseModel):
    """Update basic user information (common fields for all users)."""

    name: Optional[str] = Field(None, min_length=2, max_length=100)
    email: Optional[EmailStr] = None
    image: Optional[str] = None  # URL to profile image
    country_preference: Optional[str] = Field(None, min_length=2, max_length=2)

    # Common fields for both buyers and agents
    phone_number: Optional[str] = Field(None, min_length=8, max_length=20)
    company_name: Optional[str] = Field(None, max_length=200)
    website: Optional[str] = Field(None, max_length=200)

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "John Doe Updated",
                "email": "john.updated@example.com",
                "country_preference": "al",
                "phone_number": "+355691234567",
                "company_name": "My Business Ltd",
                "website": "https://mybusiness.com"
            }
        }
    }


class UserProfileUpdateResponse(BaseSchema):
    """Response for user profile update."""

    success: bool = True
    message: str = "Profile updated successfully"
    user: UserResponse


# ============================================================================
# AGENT PROFILE UPDATE
# ============================================================================

class AgentProfileUpdate(BaseModel):
    """Update agent-specific information."""

    license_number: Optional[str] = Field(None, min_length=2, max_length=100)
    whatsapp_number: Optional[str] = Field(None, min_length=8, max_length=20)
    bio_en: Optional[str] = Field(None, max_length=1000)

    # Document URLs (set after upload)
    license_document_url: Optional[str] = None
    company_document_url: Optional[str] = None
    id_document_url: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "license_number": "LIC123456",
                "whatsapp_number": "+355691234567",
                "bio_en": "Experienced real estate agent with 10+ years in Albania"
            }
        }
    }


class AgentProfileUpdateResponse(BaseSchema):
    """Response for agent profile update."""

    success: bool = True
    message: str
    agent_profile: AgentProfileResponse
    re_verification_triggered: bool = False


# ============================================================================
# IMAGE UPLOAD
# ============================================================================

class ImageUploadResponse(BaseSchema):
    """Response for image upload."""

    success: bool = True
    message: str = "Image uploaded successfully"
    image_url: str


# ============================================================================
# DOCUMENT UPLOAD STATUS
# ============================================================================

class DocumentUploadStatus(BaseModel):
    """Status of agent document uploads."""

    license_document_uploaded: bool
    company_document_uploaded: bool
    id_document_uploaded: bool
    all_documents_uploaded: bool

    license_document_url: Optional[str] = None
    company_document_url: Optional[str] = None
    id_document_url: Optional[str] = None

    missing: List[str] = []


class DocumentUploadStatusResponse(BaseSchema):
    """Response for document upload status."""

    success: bool = True
    status: DocumentUploadStatus
    message: str


# ============================================================================
# AGENT VERIFICATION STATUS
# ============================================================================

class DocumentsCompletionStatus(BaseModel):
    """Per-document completion status."""

    license_document: bool
    company_document: bool
    id_document: bool


class AgentVerificationStatus(BaseModel):
    """Comprehensive agent verification status."""

    verification_status: str  # "pending" | "approved" | "rejected"
    verified_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    documents_complete: bool
    documents_status: DocumentsCompletionStatus
    can_create_listings: bool
    rejection_reason: Optional[str] = None
    rejected_at: Optional[datetime] = None
    rejected_by: Optional[str] = None


class VerificationStatusResponse(BaseSchema):
    """Response for agent verification status."""

    success: bool = True
    status: AgentVerificationStatus
