"""
Admin service - business logic for admin operations.

Handles:
- Agent verification with email notifications
- User creation and management
- Platform statistics
- Credit adjustments
"""

import logging
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories import admin_repo
from app.services.email_service import send_agent_rejection_email
from app.services.promotion_service import admin_adjust_credits_service

logger = logging.getLogger(__name__)


# ============================================================================
# AGENT VERIFICATION
# ============================================================================

async def verify_agent_service(
    db: AsyncSession,
    agent_id: str
) -> dict:
    """
    Approve agent verification.

    Agent's listings become visible to public.

    Args:
        db: Database session
        agent_id: Agent UUID

    Returns:
        Agent profile dict
    """
    agent_profile = await admin_repo.verify_agent(db, agent_id)

    return {
        "agent_id": str(agent_profile.user_id),
        "verification_status": agent_profile.verification_status,
        "verified_at": agent_profile.verified_at
    }


async def reject_agent_service(
    db: AsyncSession,
    agent_id: str,
    rejection_reason: str,
    admin_id: str
) -> dict:
    """
    Reject agent verification with email notification.

    Sends email to agent with rejection reason.

    Args:
        db: Database session
        agent_id: Agent UUID
        rejection_reason: Reason for rejection
        admin_id: Admin user ID

    Returns:
        Agent profile dict
    """
    # Reject agent
    agent_profile = await admin_repo.reject_agent(
        db,
        agent_id,
        rejection_reason,
        admin_id
    )

    # Get agent user for email
    from app.repositories.user_repo import get_user_by_id
    agent_user = await get_user_by_id(db, agent_id, include_profiles=True)

    if agent_user and agent_user.email:
        # Send rejection email
        await send_agent_rejection_email(
            to_email=agent_user.email,
            agent_name=agent_user.name or "Agent",
            rejection_reason=rejection_reason
        )

    return {
        "agent_id": str(agent_profile.user_id),
        "verification_status": agent_profile.verification_status,
        "rejection_reason": agent_profile.rejection_reason,
        "rejected_at": agent_profile.rejected_at
    }


# ============================================================================
# PLATFORM STATISTICS
# ============================================================================

async def get_platform_stats_service(db: AsyncSession) -> dict:
    """
    Get platform-wide statistics.

    Args:
        db: Database session

    Returns:
        Platform stats dict
    """
    return await admin_repo.get_platform_stats(db)


# ============================================================================
# USER MANAGEMENT
# ============================================================================

async def get_all_users_service(
    db: AsyncSession,
    role_filter: str = None
) -> List[dict]:
    """
    Get all users with optional role filter.

    Args:
        db: Database session
        role_filter: Optional role filter

    Returns:
        List of user dicts
    """
    return await admin_repo.get_all_users(db, role_filter)


async def create_agent_service(
    db: AsyncSession,
    name: str,
    email: str,
    password: str,
    agency_name: str,
    license_number: str,
    phone: str,
    whatsapp: str,
    bio_en: str,
    email_verified: bool,
    verification_status: str
) -> dict:
    """
    Admin creates agent.

    Args:
        db: Database session
        All agent fields

    Returns:
        Created user dict
    """
    user = await admin_repo.admin_create_agent(
        db, name, email, password, agency_name, license_number,
        phone, whatsapp, bio_en, email_verified, verification_status
    )

    return {
        "user_id": str(user.id),
        "email": user.email,
        "role": user.role,
        "email_verified": user.email_verified
    }


async def create_buyer_service(
    db: AsyncSession,
    name: str,
    email: str,
    password: str,
    company_name: str,
    email_verified: bool
) -> dict:
    """
    Admin creates buyer.

    Args:
        db: Database session
        All buyer fields

    Returns:
        Created user dict
    """
    user = await admin_repo.admin_create_buyer(
        db, name, email, password, company_name, email_verified
    )

    return {
        "user_id": str(user.id),
        "email": user.email,
        "role": user.role,
        "email_verified": user.email_verified
    }


async def delete_user_service(
    db: AsyncSession,
    user_id: str
) -> bool:
    """
    Admin deletes user.

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        True if deleted
    """
    return await admin_repo.admin_delete_user(db, user_id)


async def toggle_email_verification_service(
    db: AsyncSession,
    user_id: str,
    email_verified: bool
) -> dict:
    """
    Admin toggles email verification.

    Args:
        db: Database session
        user_id: User UUID
        email_verified: New status

    Returns:
        Updated user dict
    """
    user = await admin_repo.toggle_email_verification(db, user_id, email_verified)

    return {
        "user_id": str(user.id),
        "email": user.email,
        "email_verified": user.email_verified
    }
