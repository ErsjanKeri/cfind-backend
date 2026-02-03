"""
User service - business logic for user and profile management.

Orchestrates:
- Repository calls
- File uploads
- Email notifications
- Re-verification triggers
"""

import logging
from typing import Optional
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import (
    UserProfileUpdate,
    AgentProfileUpdate
    # BuyerProfileUpdate REMOVED
)
from app.repositories import user_repo
from app.services.upload_service import (
    upload_image_direct,
    delete_old_image
)
from app.services.email_service import send_verification_email
from app.core.security import generate_secure_token
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ============================================================================
# USER PROFILE MANAGEMENT
# ============================================================================

async def get_current_user_profile(
    db: AsyncSession,
    user_id: str
) -> User:
    """
    Get current user's complete profile.

    Includes role-specific profile (agent or buyer).

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        User object with profiles loaded

    Raises:
        HTTPException: If user not found
    """
    user = await user_repo.get_user_by_id(db, user_id, include_profiles=True)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user


async def update_user_profile(
    db: AsyncSession,
    user_id: str,
    update_data: UserProfileUpdate
) -> User:
    """
    Update user's basic profile information.

    If email is changed, user must re-verify email.

    Args:
        db: Database session
        user_id: User UUID
        update_data: Update schema

    Returns:
        Updated user object

    Raises:
        HTTPException: If update fails
    """
    user = await user_repo.update_user_basic_info(db, user_id, update_data)

    # If email changed, send new verification email
    if update_data.email and update_data.email != user.email:
        # TODO: Generate verification token and send email
        # This requires creating a new EmailVerificationToken
        logger.info(f"Email changed for user {user_id}, verification email needed")

    return user


async def upload_user_profile_image(
    db: AsyncSession,
    user_id: str,
    file: UploadFile
) -> str:
    """
    Upload user's profile image.

    Uploads to S3, updates user record, deletes old image.

    Args:
        db: Database session
        user_id: User UUID
        file: Image file

    Returns:
        Public URL of uploaded image

    Raises:
        HTTPException: If upload fails
    """
    # Fetch user
    user = await user_repo.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Upload new image
    image_url = await upload_image_direct(file, folder="profiles")

    # Delete old image if exists
    if user.image:
        await delete_old_image(user.image)

    # Update user record
    await user_repo.update_user_basic_info(
        db,
        user_id,
        UserProfileUpdate(image=image_url)
    )

    logger.info(f"Profile image uploaded for user {user_id}")
    return image_url


# ============================================================================
# AGENT PROFILE MANAGEMENT
# ============================================================================

async def update_agent_profile_service(
    db: AsyncSession,
    user_id: str,
    update_data: AgentProfileUpdate
) -> tuple[dict, bool]:
    """
    Update agent profile with re-verification logic.

    CRITICAL: Re-verification is triggered when:
    - license_number changes
    - agency_name changes
    - Any new document is uploaded

    When re-verification is triggered:
    - Status → "pending"
    - Listings become invisible
    - Agent cannot create new listings

    Args:
        db: Database session
        user_id: User UUID
        update_data: Update schema

    Returns:
        Tuple of (agent_profile_dict, re_verification_triggered)

    Raises:
        HTTPException: If agent profile not found
    """
    agent_profile, re_verification_triggered = await user_repo.update_agent_profile(
        db,
        user_id,
        update_data
    )

    # If re-verification triggered, log it
    if re_verification_triggered:
        logger.warning(
            f"Re-verification triggered for agent {user_id}. "
            f"Status changed to 'pending'. Listings are now hidden from public."
        )

        # TODO: Send email notification to agent about re-verification
        # Inform them their profile is pending review and listings are hidden

    # Convert to dict for response
    profile_dict = {
        "user_id": str(agent_profile.user_id),
        "agency_name": agent_profile.agency_name,
        "license_number": agent_profile.license_number,
        "phone_number": agent_profile.phone_number,
        "whatsapp_number": agent_profile.whatsapp_number,
        "bio_en": agent_profile.bio_en,
        "license_document_url": agent_profile.license_document_url,
        "company_document_url": agent_profile.company_document_url,
        "id_document_url": agent_profile.id_document_url,
        "verification_status": agent_profile.verification_status,
        "verified_at": agent_profile.verified_at,
        "rejection_reason": agent_profile.rejection_reason,
        "rejected_at": agent_profile.rejected_at,
        "submitted_at": agent_profile.submitted_at,
        "listings_count": agent_profile.listings_count,
        "deals_completed": agent_profile.deals_completed,
        "credit_balance": agent_profile.credit_balance
    }

    return profile_dict, re_verification_triggered


async def upload_agent_document(
    db: AsyncSession,
    user_id: str,
    document_type: str,
    document_url: str
) -> tuple[dict, bool]:
    """
    Update agent document URL after client uploads to S3.

    This is called after client completes presigned URL upload.
    Triggers re-verification.

    Args:
        db: Database session
        user_id: User UUID
        document_type: "license" | "company" | "id"
        document_url: Public URL of uploaded document

    Returns:
        Tuple of (agent_profile_dict, re_verification_triggered)

    Raises:
        HTTPException: If document type invalid or agent not found
    """
    # Validate document type
    if document_type not in ["license", "company", "id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document type. Must be: license, company, or id"
        )

    # Create update data
    update_data = AgentProfileUpdate()

    if document_type == "license":
        update_data.license_document_url = document_url
    elif document_type == "company":
        update_data.company_document_url = document_url
    elif document_type == "id":
        update_data.id_document_url = document_url

    # Update agent profile (triggers re-verification)
    return await update_agent_profile_service(db, user_id, update_data)


async def get_agent_documents_status(
    db: AsyncSession,
    user_id: str
) -> dict:
    """
    Get status of agent's document uploads.

    Shows which documents are uploaded and which are missing.

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        Dict with document status

    Example:
        >>> status = await get_agent_documents_status(db, user_id)
        >>> print(status)
        {
            "license_document": True,
            "company_document": False,
            "id_document": True,
            "all_complete": False,
            "missing": ["company"]
        }
    """
    complete, status_dict = await user_repo.check_agent_documents_complete(db, user_id)

    # Get agent profile for URLs
    agent_profile = await user_repo.get_user_by_id(db, user_id, include_profiles=True)
    if not agent_profile or not agent_profile.agent_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent profile not found"
        )

    ap = agent_profile.agent_profile

    # Build missing list
    missing = []
    if not ap.license_document_url:
        missing.append("license")
    if not ap.company_document_url:
        missing.append("company")
    if not ap.id_document_url:
        missing.append("id")

    return {
        "license_document_uploaded": bool(ap.license_document_url),
        "company_document_uploaded": bool(ap.company_document_url),
        "id_document_uploaded": bool(ap.id_document_url),
        "license_document_url": ap.license_document_url,
        "company_document_url": ap.company_document_url,
        "id_document_url": ap.id_document_url,
        "all_complete": complete,
        "missing": missing
    }



# ============================================================================
# VERIFICATION STATUS
# ============================================================================

async def get_verification_status(
    db: AsyncSession,
    user_id: str
) -> dict:
    """
    Get comprehensive verification status for agent.

    Shows:
    - Current verification status
    - Document upload status
    - Whether agent can create listings
    - Rejection reason (if rejected)

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        Dict with verification details

    Raises:
        HTTPException: If user is not an agent
    """
    user = await user_repo.get_user_by_id(db, user_id, include_profiles=True)

    if not user or user.role != "agent":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not an agent"
        )

    return await user_repo.get_agent_verification_status(db, user_id)
