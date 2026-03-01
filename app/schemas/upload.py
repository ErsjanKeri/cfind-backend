"""
Pydantic schemas for file upload operations.

Handles:
- Image uploads (profiles, listings)
- Document uploads (agent verification documents)
- Presigned URL generation
- Direct uploads through server
"""

from pydantic import BaseModel, Field

from app.schemas.base import BaseSchema


# ============================================================================
# PRESIGNED URL REQUESTS
# ============================================================================

class PresignedImageRequest(BaseModel):
    """Request for presigned URL to upload images (profiles, listings)."""

    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., pattern="^image/(jpeg|jpg|png|webp|gif)$")
    folder: str = Field(default="general", pattern="^(general|profiles|listings)$")


class PresignedDocumentRequest(BaseModel):
    """Request for presigned URL to upload agent verification documents."""

    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., pattern="^(application/pdf|image/(jpeg|jpg|png))$")
    document_type: str = Field(..., pattern="^(license|company|id)$")


# ============================================================================
# RESPONSES
# ============================================================================

class PresignedUrlResponse(BaseSchema):
    """Response containing presigned URL for client-side S3 upload."""

    success: bool = True
    message: str = "Presigned URL generated successfully"
    upload_url: str
    fields: dict
    s3_key: str
    public_url: str  # Where file will be accessible after upload


class DirectUploadResponse(BaseSchema):
    """Response for direct server-side uploads."""

    success: bool = True
    message: str = "File uploaded successfully"
    url: str


# ============================================================================
# DOCUMENT CONFIRMATION (PRESIGNED FLOW)
# ============================================================================

class ConfirmDocumentUploadRequest(BaseModel):
    """Confirm that agent document was uploaded to S3 via presigned URL."""

    document_type: str = Field(..., pattern="^(license|company|id)$")
    document_url: str = Field(..., min_length=10)


class ConfirmDocumentUploadResponse(BaseSchema):
    """Response after confirming document upload."""

    success: bool = True
    message: str
    re_verification_triggered: bool
    verification_status: str
