"""
User profile management routes.

Endpoints:
- GET /users/me - Get current user profile
- PUT /users/me - Update basic user info (name, email)
- POST /users/me/image - Upload profile image
- PUT /users/me/agent-profile - Update agent profile (triggers re-verification)
- PUT /users/me/buyer-profile - Update buyer profile
- GET /users/me/verification-status - Get agent verification status
- GET /users/me/documents - Get agent document upload status
"""

import logging
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, status
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.user import (
    UserResponse,
    UserProfileUpdate, UserProfileUpdateResponse,
    AgentProfileResponse, AgentProfileUpdate, AgentProfileUpdateResponse,
    ImageUploadResponse,
    DocumentUploadStatus, DocumentUploadStatusResponse,
    VerificationStatusResponse,
)
from app.api.deps import (
    get_current_user,
    get_verified_user,
    verify_csrf_token,
    RoleChecker
)
from app.repositories import user_repo
from app.services.upload_service import upload_image_direct, upload_document_direct, delete_old_image

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/users", tags=["Users"])


# ============================================================================
# CURRENT USER PROFILE
# ============================================================================

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
    description="Get authenticated user's complete profile including role-specific data"
)
async def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's complete profile.

    Returns:
    - Basic user info (id, name, email, role)
    - Agent profile (if role = agent)
    - Buyer profile (if role = buyer)
    """
    user = await user_repo.get_user_by_id(db, str(current_user.id), include_profiles=True)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.put(
    "/me",
    response_model=UserProfileUpdateResponse,
    summary="Update user profile",
    description="Update basic user information (name, email, image)"
)
async def update_user_profile(
    update_data: UserProfileUpdate,
    current_user: Annotated[User, Depends(get_verified_user)],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Update user's basic information.

    If email is changed:
    - Email verification is reset to false
    - User must re-verify email
    - New verification email is sent
    """
    updated_user = await user_repo.update_user_basic_info(db, str(current_user.id), update_data)

    return UserProfileUpdateResponse(
        success=True,
        message="Profile updated successfully",
        user=updated_user
    )


# ============================================================================
# PROFILE IMAGE UPLOAD
# ============================================================================

@router.post(
    "/me/image",
    response_model=ImageUploadResponse,
    summary="Upload profile image",
    description="Upload user's profile image to S3"
)
async def upload_profile_image(
    current_user: Annotated[User, Depends(get_verified_user)],
    file: UploadFile = File(...),
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload user's profile image.

    - Uploads to S3 (folder: images/profiles/)
    - Deletes old profile image if exists
    - Updates user.image field
    - Supports: JPEG, PNG, WebP, GIF
    - Max size: 10 MB
    """
    # Upload new image to S3
    image_url = await upload_image_direct(file, folder="profiles")

    # Delete old image if exists
    if current_user.image:
        await delete_old_image(current_user.image)

    # Update user record
    await user_repo.update_user_basic_info(db, str(current_user.id), UserProfileUpdate(image=image_url))

    return ImageUploadResponse(
        success=True,
        message="Profile image uploaded successfully",
        image_url=image_url
    )


# ============================================================================
# AGENT PROFILE MANAGEMENT
# ============================================================================

@router.put(
    "/me/agent-profile",
    response_model=AgentProfileUpdateResponse,
    summary="Update agent profile",
    description="Update agent-specific information with optional document uploads"
)
async def update_agent_profile(
    current_user: Annotated[User, Depends(RoleChecker(["agent"]))],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db),
    # Text fields (Form data)
    license_number: Optional[str] = Form(None),
    whatsapp_number: Optional[str] = Form(None),
    bio_en: Optional[str] = Form(None),
    # Optional file uploads
    license_document: Optional[UploadFile] = File(None),
    company_document: Optional[UploadFile] = File(None),
    id_document: Optional[UploadFile] = File(None),
):
    """
    Update agent profile with text fields and optional document uploads.

    Accepts multipart/form-data with:
    - Text fields: license_number, whatsapp_number, bio_en
    - File fields (optional): license_document, company_document, id_document

    Documents are automatically uploaded to S3 if provided.
    """
    # Upload documents to S3 if provided
    document_urls = {}
    if license_document:
        document_urls['license_document_url'] = await upload_document_direct(
            license_document,
            str(current_user.id),
            'license'
        )

    if company_document:
        document_urls['company_document_url'] = await upload_document_direct(
            company_document,
            str(current_user.id),
            'company'
        )

    if id_document:
        document_urls['id_document_url'] = await upload_document_direct(
            id_document,
            str(current_user.id),
            'id'
        )

    # Convert empty strings to None to avoid validation errors
    # This ensures that empty form fields don't fail min_length validation
    def normalize_field(value: Optional[str]) -> Optional[str]:
        """Convert empty strings to None, strip whitespace from non-empty strings."""
        if value is None:
            return None
        stripped = value.strip()
        return stripped if stripped else None

    # Create update object with text fields + document URLs
    from app.schemas.user import AgentProfileUpdate
    update_data = AgentProfileUpdate(
        license_number=normalize_field(license_number),
        whatsapp_number=normalize_field(whatsapp_number),
        bio_en=normalize_field(bio_en),
        **document_urls  # Add uploaded document URLs
    )

    # Update profile (repo handles re-verification triggers)
    agent_profile, re_verification_triggered = await user_repo.update_agent_profile(
        db, str(current_user.id), update_data
    )

    message = "Agent profile updated successfully"
    if re_verification_triggered:
        message += ". Your profile is now pending re-verification."

    return AgentProfileUpdateResponse(
        success=True,
        message=message,
        agent_profile=AgentProfileResponse.model_validate(agent_profile),
        re_verification_triggered=re_verification_triggered
    )


@router.get(
    "/me/verification-status",
    response_model=VerificationStatusResponse,
    summary="Get agent verification status",
    description="Get comprehensive verification status for current agent"
)
async def get_verification_status(
    current_user: Annotated[User, Depends(RoleChecker(["agent"]))],
    db: AsyncSession = Depends(get_db)
):
    """
    Get agent's verification status.

    Returns:
    - verification_status: "pending" | "approved" | "rejected"
    - documents_complete: All 3 documents uploaded
    - documents_status: Individual document status
    - can_create_listings: Verified + all documents uploaded
    - rejection_reason: If rejected
    """
    verification = await user_repo.get_agent_verification_status(db, str(current_user.id))

    return VerificationStatusResponse(
        success=True,
        status=verification
    )


@router.get(
    "/me/documents",
    response_model=DocumentUploadStatusResponse,
    summary="Get document upload status",
    description="Get status of agent's required document uploads"
)
async def get_document_status(
    current_user: Annotated[User, Depends(RoleChecker(["agent"]))],
    db: AsyncSession = Depends(get_db)
):
    """
    Get agent's document upload status.

    Shows which documents are uploaded and which are missing.
    """
    complete, status_dict = await user_repo.check_agent_documents_complete(db, str(current_user.id))
    user = await user_repo.get_user_by_id(db, str(current_user.id), include_profiles=True)
    if not user or not user.agent_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent profile not found")

    ap = user.agent_profile
    missing = []
    if not ap.license_document_url:
        missing.append("license")
    if not ap.company_document_url:
        missing.append("company")
    if not ap.id_document_url:
        missing.append("id")

    doc_status = {
        "license_document_uploaded": bool(ap.license_document_url),
        "company_document_uploaded": bool(ap.company_document_url),
        "id_document_uploaded": bool(ap.id_document_url),
        "license_document_url": ap.license_document_url,
        "company_document_url": ap.company_document_url,
        "id_document_url": ap.id_document_url,
        "all_documents_uploaded": complete,
        "missing": missing
    }

    return DocumentUploadStatusResponse(
        success=True,
        status=DocumentUploadStatus(**doc_status),
        message=f"Documents complete: {complete}"
    )
