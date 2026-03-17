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
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_
from sqlalchemy.orm import selectinload
import uuid

from app.models.user import User, AgentProfile
from app.models.listing import Listing
from app.models.lead import Lead
from app.models.demand import BuyerDemand
from app.models.promotion import PromotionHistory, CreditTransaction
from app.core.security import hash_password
from app.schemas.admin import PlatformStats, UserListItem

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
        Updated agent profile, or None if not found.
    """
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == agent_id)
    )
    agent_profile = result.scalar_one_or_none()

    if not agent_profile:
        return None

    # Approve agent
    agent_profile.verification_status = "approved"
    agent_profile.verified_at = datetime.now(timezone.utc)
    agent_profile.rejection_reason = None
    agent_profile.rejected_at = None
    agent_profile.rejected_by = None

    await db.flush()

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
        Updated agent profile, or None if not found.
    """
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.user_id == agent_id)
    )
    agent_profile = result.scalar_one_or_none()

    if not agent_profile:
        return None

    # Reject agent
    agent_profile.verification_status = "rejected"
    agent_profile.rejection_reason = rejection_reason
    agent_profile.rejected_at = datetime.now(timezone.utc)
    agent_profile.rejected_by = rejected_by
    agent_profile.verified_at = None

    await db.flush()

    logger.info(f"Rejected agent: {agent_id}, reason: {rejection_reason}")
    return agent_profile


# ============================================================================
# PLATFORM STATISTICS
# ============================================================================

async def get_platform_stats(db: AsyncSession) -> PlatformStats:
    """Get platform-wide statistics using batched queries (5 queries instead of 18)."""

    # Query 1: Users by role
    user_counts = await db.execute(
        select(User.role, func.count(User.id)).group_by(User.role)
    )
    user_map = dict(user_counts.all())
    total_buyers = user_map.get("buyer", 0)
    total_agents = user_map.get("agent", 0)
    total_admins = user_map.get("admin", 0)

    # Query 2: Agents by verification status
    agent_counts = await db.execute(
        select(AgentProfile.verification_status, func.count(AgentProfile.user_id))
        .group_by(AgentProfile.verification_status)
    )
    agent_map = dict(agent_counts.all())

    # Query 3: Listings by status
    listing_counts = await db.execute(
        select(Listing.status, func.count(Listing.id)).group_by(Listing.status)
    )
    listing_map = dict(listing_counts.all())

    # Query 4: Demands by status + total leads
    demand_counts = await db.execute(
        select(BuyerDemand.status, func.count(BuyerDemand.id)).group_by(BuyerDemand.status)
    )
    demand_map = dict(demand_counts.all())

    total_leads_result = await db.execute(select(func.count(Lead.id)))
    total_leads = total_leads_result.scalar()

    # Query 5: Promotions
    active_promotions_result = await db.execute(
        select(func.count(PromotionHistory.id)).where(PromotionHistory.status == "active")
    )
    active_promotions = active_promotions_result.scalar()

    total_credit_txns_result = await db.execute(select(func.count(CreditTransaction.id)))
    total_credit_transactions = total_credit_txns_result.scalar()

    return PlatformStats(
        total_users=total_buyers + total_agents + total_admins,
        total_buyers=total_buyers,
        total_agents=total_agents,
        total_admins=total_admins,
        agents_pending=agent_map.get("pending", 0),
        agents_approved=agent_map.get("approved", 0),
        agents_rejected=agent_map.get("rejected", 0),
        total_listings=sum(listing_map.values()),
        active_listings=listing_map.get("active", 0),
        draft_listings=listing_map.get("draft", 0),
        sold_listings=listing_map.get("sold", 0),
        inactive_listings=listing_map.get("inactive", 0),
        total_leads=total_leads,
        total_demands=sum(demand_map.values()),
        active_demands=demand_map.get("active", 0),
        assigned_demands=demand_map.get("assigned", 0),
        fulfilled_demands=demand_map.get("fulfilled", 0),
        active_promotions=active_promotions,
        total_credit_transactions=total_credit_transactions
    )


# ============================================================================
# GET ALL USERS
# ============================================================================

async def get_all_users(
    db: AsyncSession,
    role_filter: Optional[str] = None,
    page: int = 1,
    limit: int = 20
) -> tuple[List[UserListItem], int]:
    """
    Get paginated users with optional role filter.

    Returns:
        Tuple of (users_list, total_count)
    """
    base_query = (
        select(User)
        .options(
            selectinload(User.agent_profile),
        )
    )

    if role_filter:
        base_query = base_query.where(User.role == role_filter)

    base_query = base_query.order_by(User.created_at.desc())

    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * limit
    result = await db.execute(base_query.offset(offset).limit(limit))
    users = result.scalars().all()

    users_list = []
    for user in users:
        item = UserListItem.model_validate(user)
        if user.agent_profile:
            item = item.model_copy(update={
                "operating_country": user.agent_profile.operating_country,
                "verification_status": user.agent_profile.verification_status,
                "credit_balance": user.agent_profile.credit_balance,
                "license_number": user.agent_profile.license_number,
                "whatsapp_number": user.agent_profile.whatsapp_number,
                "bio_en": user.agent_profile.bio_en,
                "license_document_url": user.agent_profile.license_document_url,
                "company_document_url": user.agent_profile.company_document_url,
                "id_document_url": user.agent_profile.id_document_url,
            })
        users_list.append(item)

    logger.info(f"Fetched {len(users_list)} users (role filter: {role_filter}, page {page}, total: {total})")
    return users_list, total


# ============================================================================
# CREATE AGENT (ADMIN)
# ============================================================================

async def admin_create_agent(
    db: AsyncSession,
    name: str,
    email: str,
    password: str,
    operating_country: str,
    company_name: str,
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
        company_name, license_number, etc: Agent profile fields
        email_verified: Admin can bypass email verification
        verification_status: Admin can pre-approve

    Returns:
        Created user object.

    Raises:
        ValueError: If email already exists.
    """
    # Check email doesn't exist
    existing = await db.execute(
        select(User).where(User.email == email)
    )
    if existing.scalar_one_or_none():
        raise ValueError("Email already registered")

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
        company_name=company_name,
        phone_number=phone
    )
    db.add(user)
    await db.flush()

    # Create agent profile (agent-specific fields only)
    agent_profile = AgentProfile(
        user_id=user.id,
        operating_country=operating_country,
        license_number=license_number,
        whatsapp_number=whatsapp,
        bio_en=bio_en,
        verification_status=verification_status,
        verified_at=datetime.now(timezone.utc) if verification_status == "approved" else None
    )
    db.add(agent_profile)

    await db.flush()

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
        Created user object.

    Raises:
        ValueError: If email already exists.
    """
    # Check email doesn't exist
    existing = await db.execute(
        select(User).where(User.email == email)
    )
    if existing.scalar_one_or_none():
        raise ValueError("Email already registered")

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
        True if deleted, False if not found.

    Raises:
        ValueError: If user is admin.
    """
    # Fetch user
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return False

    # Prevent deleting admins
    if user.role == "admin":
        raise ValueError("Cannot delete admin users")

    # Delete user (cascade handles profiles, listings, etc.)
    await db.delete(user)
    await db.flush()

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
        Updated user object, or None if not found.
    """
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return None

    user.email_verified = email_verified

    await db.flush()

    logger.info(f"Admin toggled email verification for user {user_id}: {email_verified}")
    return user


async def get_pending_listings(
    db: AsyncSession,
    page: int = 1,
    limit: int = 20
):
    """Get listings pending admin verification."""
    query = (
        select(Listing, User)
        .join(User, Listing.agent_id == User.id)
        .options(selectinload(Listing.images), selectinload(User.agent_profile))
        .where(Listing.status == "pending")
        .order_by(Listing.created_at.asc())
    )

    count_query = select(func.count()).select_from(
        select(Listing.id).where(Listing.status == "pending").subquery()
    )
    total = (await db.execute(count_query)).scalar()

    offset = (page - 1) * limit
    result = await db.execute(query.offset(offset).limit(limit))
    return result.all(), total


async def approve_listing(db: AsyncSession, listing_id: str) -> Optional[Listing]:
    """Approve a pending listing — sets status to active."""
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    listing = result.scalar_one_or_none()
    if not listing or listing.status != "pending":
        return None

    listing.status = "active"
    listing.rejection_reason = None
    listing.rejected_at = None
    await db.flush()

    logger.info(f"Admin approved listing {listing_id}")
    return listing


async def reject_listing(
    db: AsyncSession,
    listing_id: str,
    reason: str
) -> Optional[Listing]:
    """Reject a pending listing with reason."""
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    listing = result.scalar_one_or_none()
    if not listing or listing.status != "pending":
        return None

    listing.status = "rejected"
    listing.rejection_reason = reason
    listing.rejected_at = datetime.now(timezone.utc)
    await db.flush()

    logger.info(f"Admin rejected listing {listing_id}: {reason}")
    return listing
