"""
Admin repository - database operations for admin panel.

Handles:
- Agent verification (approve/reject/suspend)
- User management (create/delete agents/buyers)
- Platform statistics and analytics
- All admin-specific queries
"""

import logging
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
import uuid

from app.models.user import User, AgentProfile  # BuyerProfile removed
from app.models.listing import Listing
from app.models.lead import Lead
from app.models.demand import BuyerDemand
from app.models.promotion import PromotionHistory, CreditTransaction
from app.core.security import hash_password

logger = logging.getLogger(__name__)


# ============================================================================
# AGENT VERIFICATION
# ============================================================================

async def verify_agent(
    db: AsyncSession,
    agent_id: str
) -> AgentProfile:
    """
    Approve agent verification.

    Sets:
    - verification_status = "approved"
    - verified_at = now()
    - Clears rejection data

    Args:
        db: Database session
        agent_id: Agent UUID

    Returns:
        Updated agent profile

    Raises:
        HTTPException: If agent not found
    """
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == agent_id)
    )
    agent_profile = result.scalar_one_or_none()

    if not agent_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent profile not found"
        )

    # Approve agent
    agent_profile.verification_status = "approved"
    agent_profile.verified_at = datetime.now(datetime.now().astimezone().tzinfo)
    agent_profile.rejection_reason = None
    agent_profile.rejected_at = None
    agent_profile.rejected_by = None

    await db.commit()
    await db.refresh(agent_profile)

    logger.info(f"Approved agent: {agent_id}")
    return agent_profile


async def reject_agent(
    db: AsyncSession,
    agent_id: str,
    rejection_reason: str,
    rejected_by: str
) -> AgentProfile:
    """
    Reject agent verification.

    Sets:
    - verification_status = "rejected"
    - rejection_reason = reason
    - rejected_at = now()
    - rejected_by = admin_id

    Args:
        db: Database session
        agent_id: Agent UUID
        rejection_reason: Reason for rejection
        rejected_by: Admin user ID

    Returns:
        Updated agent profile

    Raises:
        HTTPException: If agent not found
    """
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == agent_id)
    )
    agent_profile = result.scalar_one_or_none()

    if not agent_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent profile not found"
        )

    # Reject agent
    agent_profile.verification_status = "rejected"
    agent_profile.rejection_reason = rejection_reason
    agent_profile.rejected_at = datetime.now(datetime.now().astimezone().tzinfo)
    agent_profile.rejected_by = rejected_by
    agent_profile.verified_at = None

    await db.commit()
    await db.refresh(agent_profile)

    logger.info(f"Rejected agent: {agent_id}, reason: {rejection_reason}")
    return agent_profile


# ============================================================================
# PLATFORM STATISTICS
# ============================================================================

async def get_platform_stats(db: AsyncSession) -> dict:
    """
    Get platform-wide statistics.

    Aggregates:
    - Total users by role
    - Agents by verification status
    - Listings by status
    - Total leads and demands
    - Active promotions

    Args:
        db: Database session

    Returns:
        Dict with platform statistics

    Example:
        >>> stats = await get_platform_stats(db)
        >>> print(f"Total users: {stats['total_users']}")
    """
    # Users count
    total_users_result = await db.execute(select(func.count(User.id)))
    total_users = total_users_result.scalar()

    buyers_result = await db.execute(select(func.count(User.id)).where(User.role == "buyer"))
    total_buyers = buyers_result.scalar()

    agents_result = await db.execute(select(func.count(User.id)).where(User.role == "agent"))
    total_agents = agents_result.scalar()

    admins_result = await db.execute(select(func.count(User.id)).where(User.role == "admin"))
    total_admins = admins_result.scalar()

    # Agents by verification status
    agents_pending_result = await db.execute(
        select(func.count(AgentProfile.user_id)).where(AgentProfile.verification_status == "pending")
    )
    agents_pending = agents_pending_result.scalar()

    agents_approved_result = await db.execute(
        select(func.count(AgentProfile.user_id)).where(AgentProfile.verification_status == "approved")
    )
    agents_approved = agents_approved_result.scalar()

    agents_rejected_result = await db.execute(
        select(func.count(AgentProfile.user_id)).where(AgentProfile.verification_status == "rejected")
    )
    agents_rejected = agents_rejected_result.scalar()

    # Listings by status
    total_listings_result = await db.execute(select(func.count(Listing.id)))
    total_listings = total_listings_result.scalar()

    active_listings_result = await db.execute(
        select(func.count(Listing.id)).where(Listing.status == "active")
    )
    active_listings = active_listings_result.scalar()

    draft_listings_result = await db.execute(
        select(func.count(Listing.id)).where(Listing.status == "draft")
    )
    draft_listings = draft_listings_result.scalar()

    sold_listings_result = await db.execute(
        select(func.count(Listing.id)).where(Listing.status == "sold")
    )
    sold_listings = sold_listings_result.scalar()

    inactive_listings_result = await db.execute(
        select(func.count(Listing.id)).where(Listing.status == "inactive")
    )
    inactive_listings = inactive_listings_result.scalar()

    # Leads & Demands
    total_leads_result = await db.execute(select(func.count(Lead.id)))
    total_leads = total_leads_result.scalar()

    total_demands_result = await db.execute(select(func.count(BuyerDemand.id)))
    total_demands = total_demands_result.scalar()

    active_demands_result = await db.execute(
        select(func.count(BuyerDemand.id)).where(BuyerDemand.status == "active")
    )
    active_demands = active_demands_result.scalar()

    assigned_demands_result = await db.execute(
        select(func.count(BuyerDemand.id)).where(BuyerDemand.status == "assigned")
    )
    assigned_demands = assigned_demands_result.scalar()

    fulfilled_demands_result = await db.execute(
        select(func.count(BuyerDemand.id)).where(BuyerDemand.status == "fulfilled")
    )
    fulfilled_demands = fulfilled_demands_result.scalar()

    # Promotions
    active_promotions_result = await db.execute(
        select(func.count(PromotionHistory.id)).where(PromotionHistory.status == "active")
    )
    active_promotions = active_promotions_result.scalar()

    total_credit_txns_result = await db.execute(select(func.count(CreditTransaction.id)))
    total_credit_transactions = total_credit_txns_result.scalar()

    return {
        "total_users": total_users,
        "total_buyers": total_buyers,
        "total_agents": total_agents,
        "total_admins": total_admins,
        "agents_pending": agents_pending,
        "agents_approved": agents_approved,
        "agents_rejected": agents_rejected,
        "total_listings": total_listings,
        "active_listings": active_listings,
        "draft_listings": draft_listings,
        "sold_listings": sold_listings,
        "inactive_listings": inactive_listings,
        "total_leads": total_leads,
        "total_demands": total_demands,
        "active_demands": active_demands,
        "assigned_demands": assigned_demands,
        "fulfilled_demands": fulfilled_demands,
        "active_promotions": active_promotions,
        "total_credit_transactions": total_credit_transactions
    }


# ============================================================================
# GET ALL USERS
# ============================================================================

async def get_all_users(
    db: AsyncSession,
    role_filter: Optional[str] = None
) -> List[dict]:
    """
    Get all users with optional role filter.

    Args:
        db: Database session
        role_filter: Optional role filter ("buyer" | "agent" | "admin")

    Returns:
        List of user dicts with profile info

    Example:
        >>> users = await get_all_users(db, role_filter="agent")
        >>> for user in users:
        ...     print(f"{user['name']} - {user['verification_status']}")
    """
    query = (
        select(User)
        .options(
            selectinload(User.agent_profile),
            # # selectinload(User.buyer_profile) # Removed # Removed
        )
    )

    if role_filter:
        query = query.where(User.role == role_filter)

    query = query.order_by(User.created_at.desc())

    result = await db.execute(query)
    users = result.scalars().all()

    # Transform to dict
    users_list = []
    for user in users:
        user_dict = {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "email_verified": user.email_verified,
            "created_at": user.created_at,
            "verification_status": None,
            "agency_name": None,
            "credit_balance": None
        }

        # Add agent-specific fields
        if user.agent_profile:
            user_dict["verification_status"] = user.agent_profile.verification_status
            user_dict["credit_balance"] = user.agent_profile.credit_balance

        # company_name is now in User table (for both buyers and agents)
        user_dict["company_name"] = user.company_name

        users_list.append(user_dict)

    logger.info(f"Fetched {len(users_list)} users (role filter: {role_filter})")
    return users_list


# ============================================================================
# CREATE AGENT (ADMIN)
# ============================================================================

async def admin_create_agent(
    db: AsyncSession,
    name: str,
    email: str,
    password: str,
    agency_name: str,
    license_number: str,
    phone: str,
    whatsapp: Optional[str],
    bio_en: Optional[str],
    email_verified: bool,
    verification_status: str
) -> User:
    """
    Admin creates agent with pre-verified email.

    Args:
        db: Database session
        name, email, password: User fields
        agency_name, license_number, etc: Agent profile fields
        email_verified: Admin can bypass email verification
        verification_status: Admin can pre-approve

    Returns:
        Created user object

    Raises:
        HTTPException: If email already exists
    """
    # Check email doesn't exist
    existing = await db.execute(
        select(User).where(User.email == email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Hash password
    hashed_password = hash_password(password)

    # Create user (with common fields)
    user = User(
        id=uuid.uuid4(),
        name=name,
        email=email,
        password=hashed_password,
        role="agent",
        email_verified=email_verified,
        # Common fields (now on User, not AgentProfile)
        company_name=agency_name,
        phone_number=phone
    )
    db.add(user)
    await db.flush()

    # Create agent profile (agent-specific fields only)
    agent_profile = AgentProfile(
        user_id=user.id,
        license_number=license_number,
        whatsapp_number=whatsapp,
        bio_en=bio_en,
        verification_status=verification_status,
        verified_at=datetime.now(datetime.now().astimezone().tzinfo) if verification_status == "approved" else None
    )
    db.add(agent_profile)

    await db.commit()
    await db.refresh(user)

    logger.info(f"Admin created agent: {user.id} ({email})")
    return user


# ============================================================================
# CREATE BUYER (ADMIN)
# ============================================================================

async def admin_create_buyer(
    db: AsyncSession,
    name: str,
    email: str,
    password: str,
    company_name: Optional[str],
    email_verified: bool
) -> User:
    """
    Admin creates buyer with pre-verified email.

    Args:
        db: Database session
        name, email, password: User fields
        company_name: Buyer profile field
        email_verified: Admin can bypass email verification

    Returns:
        Created user object

    Raises:
        HTTPException: If email already exists
    """
    # Check email doesn't exist
    existing = await db.execute(
        select(User).where(User.email == email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Hash password
    hashed_password = hash_password(password)

    # Create user
    user = User(
        id=uuid.uuid4(),
        name=name,
        email=email,
        password=hashed_password,
        role="buyer",
        email_verified=email_verified
    )
    db.add(user)
    await db.flush()

    # BuyerProfile removed - company_name is already set in User table above
    # No separate profile creation needed

    await db.commit()
    await db.refresh(user)

    logger.info(f"Admin created buyer: {user.id} ({email})")
    return user


# ============================================================================
# DELETE USER
# ============================================================================

async def admin_delete_user(
    db: AsyncSession,
    user_id: str
) -> bool:
    """
    Delete user (cascade deletes profile, listings, leads, etc.).

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        True if deleted successfully

    Raises:
        HTTPException: If user not found or is admin
    """
    # Fetch user
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Prevent deleting admins
    if user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete admin users"
        )

    # Delete user (cascade handles profiles, listings, etc.)
    await db.delete(user)
    await db.commit()

    logger.info(f"Admin deleted user: {user_id}")
    return True


# ============================================================================
# TOGGLE EMAIL VERIFICATION
# ============================================================================

async def toggle_email_verification(
    db: AsyncSession,
    user_id: str,
    email_verified: bool
) -> User:
    """
    Toggle user's email verification status.

    Args:
        db: Database session
        user_id: User UUID
        email_verified: New verification status

    Returns:
        Updated user object

    Raises:
        HTTPException: If user not found
    """
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user.email_verified = email_verified

    await db.commit()
    await db.refresh(user)

    logger.info(f"Admin toggled email verification for user {user_id}: {email_verified}")
    return user
