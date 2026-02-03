"""
File upload routes.

Endpoints:
- POST /upload/presigned/image - Generate presigned URL for image upload
- POST /upload/presigned/document - Generate presigned URL for agent document upload
- POST /upload/direct/image - Direct image upload through server
- POST /upload/direct/document - Direct document upload through server
- POST /upload/document/confirm - Confirm document upload and update agent profile
"""

from typing import Annotated
from fastapi import APIRouter, Depends, UploadFile, File, Query, status
from fastapi.exceptions import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.api.deps import get_current_user, get_verified_user, verify_csrf_token, RoleChecker
from app.services.upload_service import (
    generate_image_upload_url,
    generate_document_upload_url,
    upload_image_direct,
    upload_document_direct
)
from app.services.user_service import upload_agent_document

# Initialize router
router = APIRouter(prefix="/upload", tags=["File Upload"])


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class PresignedImageRequest(BaseModel):
    """Request schema for presigned image URL."""
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., pattern="^image/(jpeg|jpg|png|webp|gif)$")
    folder: str = Field(default="general", pattern="^(general|profiles|listings)$")


class PresignedDocumentRequest(BaseModel):
    """Request schema for presigned document URL."""
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., pattern="^(application/pdf|image/(jpeg|jpg|png))$")
    document_type: str = Field(..., pattern="^(license|company|id)$")


class PresignedUrlResponse(BaseModel):
    """Response schema for presigned URL."""
    success: bool = True
    message: str = "Presigned URL generated successfully"
    upload_url: str
    fields: dict
    s3_key: str
    public_url: str  # Where file will be accessible after upload


class DirectUploadResponse(BaseModel):
    """Response schema for direct upload."""
    success: bool = True
    message: str = "File uploaded successfully"
    url: str


class ConfirmDocumentUploadRequest(BaseModel):
    """Request schema for confirming document upload."""
    document_type: str = Field(..., pattern="^(license|company|id)$")
    document_url: str = Field(..., min_length=10)


class ConfirmDocumentUploadResponse(BaseModel):
    """Response schema for document upload confirmation."""
    success: bool = True
    message: str
    re_verification_triggered: bool
    verification_status: str


# ============================================================================
# PRESIGNED URL GENERATION
# ============================================================================

@router.post(
    "/presigned/image",
    response_model=PresignedUrlResponse,
    summary="Generate presigned URL for image upload",
    description="Get presigned S3 URL for direct client-side image upload"
)
async def get_presigned_image_url(
    request_data: PresignedImageRequest,
    current_user: Annotated[User, Depends(get_verified_user)],
    _: None = Depends(verify_csrf_token)
):
    """
    Generate presigned URL for image upload.

    **Client-side upload flow:**
    1. Client calls this endpoint to get presigned URL
    2. Client uploads image directly to S3 using presigned URL
    3. Client receives public URL where image is accessible
    4. Client sends public URL back to API (e.g., in profile update)

    **Supported image types:**
    - JPEG, JPG, PNG, WebP, GIF

    **Max file size:** 10 MB

    **Folders:**
    - profiles: User profile images
    - listings: Listing images
    - general: Other images
    """
    presigned_data = await generate_image_upload_url(
        filename=request_data.filename,
        content_type=request_data.content_type,
        folder=request_data.folder
    )

    return PresignedUrlResponse(
        success=True,
        message="Presigned URL generated. Upload your file to the provided URL.",
        upload_url=presigned_data["url"],
        fields=presigned_data["fields"],
        s3_key=presigned_data["key"],
        public_url=presigned_data["public_url"]
    )


@router.post(
    "/presigned/document",
    response_model=PresignedUrlResponse,
    summary="Generate presigned URL for document upload",
    description="Get presigned S3 URL for agent document upload"
)
async def get_presigned_document_url(
    request_data: PresignedDocumentRequest,
    current_user: Annotated[User, Depends(RoleChecker(["agent"]))],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate presigned URL for agent document upload.

    **Document types:**
    - license: Business license document
    - company: Company registration document
    - id: ID card or passport

    **Supported file types:**
    - PDF, JPEG, JPG, PNG

    **Max file size:** 15 MB

    **Important:**
    After uploading the document to S3, call POST /upload/document/confirm
    to update your agent profile and trigger re-verification if needed.
    """
    presigned_data = await generate_document_upload_url(
        user_id=str(current_user.id),
        document_type=request_data.document_type,
        filename=request_data.filename,
        content_type=request_data.content_type
    )

    return PresignedUrlResponse(
        success=True,
        message=f"Presigned URL generated for {request_data.document_type} document. Upload your file, then call /upload/document/confirm.",
        upload_url=presigned_data["url"],
        fields=presigned_data["fields"],
        s3_key=presigned_data["key"],
        public_url=presigned_data["public_url"]
    )


# ============================================================================
# DIRECT FILE UPLOAD (SERVER-SIDE)
# ============================================================================

@router.post(
    "/direct/image",
    response_model=DirectUploadResponse,
    summary="Direct image upload",
    description="Upload image directly through server (alternative to presigned URLs)"
)
async def upload_image_directly(
    current_user: Annotated[User, Depends(get_verified_user)],
    file: UploadFile = File(...),
    folder: str = Query(default="general", pattern="^(general|profiles|listings)$"),
    _: None = Depends(verify_csrf_token)
):
    """
    Upload image directly through server to S3.

    **Use cases:**
    - Simple uploads without presigned URL complexity
    - Small files
    - Server-side processing needed (resize, compress)

    **For large files or multiple uploads, prefer presigned URLs.**

    **Supported types:** JPEG, PNG, WebP, GIF
    **Max size:** 10 MB
    """
    image_url = await upload_image_direct(file, folder=folder)

    return DirectUploadResponse(
        success=True,
        message="Image uploaded successfully",
        url=image_url
    )


@router.post(
    "/direct/document",
    response_model=DirectUploadResponse,
    summary="Direct document upload",
    description="Upload agent document directly through server"
)
async def upload_document_directly(
    current_user: Annotated[User, Depends(RoleChecker(["agent"]))],
    file: UploadFile = File(...),
    document_type: str = Query(..., pattern="^(license|company|id)$"),
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload agent document directly through server to S3.

    **Document types:**
    - license: Business license
    - company: Company registration
    - id: ID card or passport

    **Supported types:** PDF, JPEG, PNG
    **Max size:** 15 MB

    **Note:** This endpoint automatically updates your agent profile
    and triggers re-verification if needed.
    """
    document_url = await upload_document_direct(
        file=file,
        user_id=str(current_user.id),
        document_type=document_type
    )

    # Update agent profile with document URL (triggers re-verification)
    _, re_verification_triggered = await upload_agent_document(
        db,
        str(current_user.id),
        document_type,
        document_url
    )

    message = f"{document_type.capitalize()} document uploaded successfully"
    if re_verification_triggered:
        message += ". Your profile is now pending re-verification."

    return DirectUploadResponse(
        success=True,
        message=message,
        url=document_url
    )


# ============================================================================
# CONFIRM DOCUMENT UPLOAD (PRESIGNED URL FLOW)
# ============================================================================

@router.post(
    "/document/confirm",
    response_model=ConfirmDocumentUploadResponse,
    summary="Confirm document upload",
    description="Confirm document was uploaded to S3 and update agent profile"
)
async def confirm_document_upload(
    confirm_data: ConfirmDocumentUploadRequest,
    current_user: Annotated[User, Depends(RoleChecker(["agent"]))],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Confirm document upload after client uploads via presigned URL.

    **Flow:**
    1. Client calls POST /upload/presigned/document → gets presigned URL
    2. Client uploads file directly to S3 using presigned URL
    3. Client calls this endpoint with document_url (from presigned response)
    4. Backend updates agent profile → triggers re-verification

    **Triggers re-verification** (status → "pending", listings hidden).
    """
    agent_profile_dict, re_verification_triggered = await upload_agent_document(
        db,
        str(current_user.id),
        confirm_data.document_type,
        confirm_data.document_url
    )

    message = f"{confirm_data.document_type.capitalize()} document confirmed"
    if re_verification_triggered:
        message += ". Your profile is now pending re-verification."

    return ConfirmDocumentUploadResponse(
        success=True,
        message=message,
        re_verification_triggered=re_verification_triggered,
        verification_status=agent_profile_dict["verification_status"]
    )


# ============================================================================
# GENERIC PRESIGNED URL (Phase 5 - Frontend Compatibility)
# ============================================================================

@router.post(
    "/presigned-post",
    response_model=PresignedUrlResponse,
    summary="Generate presigned URL (generic)",
    description="Generic presigned URL endpoint for any file type"
)
async def get_presigned_url_generic(
    file_name: str,
    file_type: str,
    category: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    """
    Generate presigned URL for file upload (generic endpoint).

    **Categories:**
    - avatar: Profile images
    - listing: Listing images
    - document: Agent documents

    This endpoint routes to the appropriate upload type based on category.
    """
    from app.services.upload_service import generate_image_upload_url, generate_document_upload_url

    if category == "avatar" or category == "listing":
        # Use image upload
        presigned_data = await generate_image_upload_url(
            user_id=str(current_user.id),
            category=category,
            filename=file_name,
            content_type=file_type
        )
    elif category == "document":
        # Use document upload
        presigned_data = await generate_document_upload_url(
            user_id=str(current_user.id),
            document_type="license",  # Default, will be overridden
            filename=file_name,
            content_type=file_type
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid category")

    return PresignedUrlResponse(
        upload_url=presigned_data["url"],
        fields=presigned_data["fields"],
        s3_key=presigned_data["key"],
        public_url=presigned_data["public_url"]
    )
