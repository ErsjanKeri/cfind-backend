"""
User repository - database operations for users and profiles.

Handles:
- User CRUD operations
- Profile fetching and updates
- Agent re-verification triggers
- Document management
"""

import logging
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.models.user import User, AgentProfile
from app.schemas.user import (
    UserProfileUpdate, AgentProfileUpdate,
    AgentVerificationStatus, DocumentsCompletionStatus,
)

logger = logging.getLogger(__name__)


# ============================================================================
# USER FETCHING
# ============================================================================

async def get_user_by_id(
    db: AsyncSession,
    user_id: str,
    include_profiles: bool = True
) -> Optional[User]:
    """
    Fetch user by ID with optional profile loading.

    Args:
        db: Database session
        user_id: User UUID
        include_profiles: Load agent/buyer profiles

    Returns:
        User object or None if not found

    Example:
        >>> user = await get_user_by_id(db, user_id="123e4567...")
        >>> if user.role == "agent":
        ...     print(user.agent_profile.agency_name)
    """
    query = select(User).where(User.id == user_id)

    if include_profiles:
        query = query.options(
            selectinload(User.agent_profile),
        )

    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_user_by_email(
    db: AsyncSession,
    email: str,
    include_profiles: bool = False
) -> Optional[User]:
    """
    Fetch user by email.

    Args:
        db: Database session
        email: User email address
        include_profiles: Load agent/buyer profiles

    Returns:
        User object or None if not found
    """
    query = select(User).where(User.email == email)

    if include_profiles:
        query = query.options(
            selectinload(User.agent_profile),
        )

    result = await db.execute(query)
    return result.scalar_one_or_none()


# ============================================================================
# USER PROFILE UPDATES
# ============================================================================

async def update_user_basic_info(
    db: AsyncSession,
    user_id: str,
    update_data: UserProfileUpdate
) -> User:
    """
    Update user's basic information (name, email, image).

    Args:
        db: Database session
        user_id: User UUID
        update_data: Update schema

    Returns:
        Updated user object

    Raises:
        HTTPException: If user not found or email already exists
    """
    # Fetch user
    user = await get_user_by_id(db, user_id, include_profiles=True)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Check if email is being changed and already exists
    if update_data.email and update_data.email != user.email:
        existing = await get_user_by_email(db, update_data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use by another account"
            )

        # Email changed - reset verification
        user.email = update_data.email
        user.email_verified = False
        # TODO: Send new verification email

    # Update fields
    if update_data.name is not None:
        user.name = update_data.name

    if update_data.image is not None:
        user.image = update_data.image

    # Update common fields (for both buyers and agents)
    if update_data.phone_number is not None:
        user.phone_number = update_data.phone_number

    if update_data.company_name is not None:
        user.company_name = update_data.company_name

    if update_data.website is not None:
        user.website = update_data.website

    user.updated_at = datetime.now(timezone.utc)

    await db.commit()

    # Re-fetch with agent_profile loaded (db.refresh doesn't load relationships)
    result = await db.execute(
        select(User)
        .options(selectinload(User.agent_profile))
        .where(User.id == user_id)
    )
    user = result.scalar_one()

    logger.info(f"Updated user basic info: {user_id}")
    return user


# ============================================================================
# AGENT PROFILE UPDATES
# ============================================================================

async def update_agent_profile(
    db: AsyncSession,
    user_id: str,
    update_data: AgentProfileUpdate
) -> tuple[AgentProfile, bool]:
    """
    Update agent profile with re-verification trigger logic.

    CRITICAL RE-VERIFICATION TRIGGERS:
    - Changing license_number
    - Uploading new documents (license, company, or ID)

    Note: agency_name and phone_number are now on User model, not AgentProfile

    When triggered:
    - verification_status → "pending"
    - Agent's listings become invisible to public
    - Agent cannot create new listings until re-approved

    Args:
        db: Database session
        user_id: User UUID
        update_data: Update schema

    Returns:
        Tuple of (updated_profile, re_verification_triggered)

    Raises:
        HTTPException: If agent profile not found
    """
    # Fetch agent profile
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user_id)
    )
    agent_profile = result.scalar_one_or_none()

    if not agent_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent profile not found"
        )

    # Apply updates and detect re-verification triggers
    re_verify_fields = {"license_number", "license_document_url", "company_document_url", "id_document_url"}
    re_verification_triggered = False

    for field, value in update_data.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if field in re_verify_fields and value != getattr(agent_profile, field):
            logger.info(f"Agent {user_id} changed {field} - triggering re-verification")
            re_verification_triggered = True
        setattr(agent_profile, field, value)

    # Trigger re-verification if needed
    if re_verification_triggered:
        agent_profile.verification_status = "pending"
        agent_profile.submitted_at = datetime.now(timezone.utc)
        # Clear previous rejection data
        agent_profile.rejection_reason = None
        agent_profile.rejected_at = None
        agent_profile.rejected_by = None
        agent_profile.verified_at = None

    await db.commit()
    await db.refresh(agent_profile)

    logger.info(f"Updated agent profile: {user_id}, re_verification_triggered: {re_verification_triggered}")
    return agent_profile, re_verification_triggered


async def check_agent_documents_complete(
    db: AsyncSession,
    user_id: str
) -> tuple[bool, dict]:
    """
    Check if agent has uploaded all required documents.

    Required documents:
    1. License document
    2. Company registration document
    3. ID/passport document

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        Tuple of (all_complete, status_dict)

    Example:
        >>> complete, status = await check_agent_documents_complete(db, user_id)
        >>> if complete:
        ...     print("All documents uploaded!")
        >>> else:
        ...     print(f"Missing: {[k for k, v in status.items() if not v]}")
    """
    # Fetch agent profile
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user_id)
    )
    agent_profile = result.scalar_one_or_none()

    if not agent_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent profile not found"
        )

    # Check each document
    status_dict = {
        "license_document": bool(agent_profile.license_document_url),
        "company_document": bool(agent_profile.company_document_url),
        "id_document": bool(agent_profile.id_document_url)
    }

    all_complete = all(status_dict.values())

    return all_complete, status_dict


# ============================================================================
# AGENT VERIFICATION HELPERS
# ============================================================================

async def get_agent_verification_status(
    db: AsyncSession,
    user_id: str
) -> AgentVerificationStatus:
    """
    Get comprehensive agent verification status.

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        AgentVerificationStatus model
    """
    # Fetch agent profile
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == user_id)
    )
    agent_profile = result.scalar_one_or_none()

    if not agent_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent profile not found"
        )

    # Check documents
    documents_complete, documents_status = await check_agent_documents_complete(db, user_id)

    # Determine if agent can create listings
    can_create_listings = (
        agent_profile.verification_status == "approved" and
        documents_complete
    )

    return AgentVerificationStatus(
        verification_status=agent_profile.verification_status,
        verified_at=agent_profile.verified_at,
        submitted_at=agent_profile.submitted_at,
        documents_complete=documents_complete,
        documents_status=DocumentsCompletionStatus(**documents_status),
        can_create_listings=can_create_listings,
        rejection_reason=agent_profile.rejection_reason,
        rejected_at=agent_profile.rejected_at,
        rejected_by=str(agent_profile.rejected_by) if agent_profile.rejected_by else None
    )
