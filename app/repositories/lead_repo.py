"""
Lead repository - database operations for leads and saved listings.

Handles:
- Lead creation with deduplication (buyer + listing + interaction_type)
- Agent lead fetching (all buyers who contacted agent's listings)
- Buyer lead fetching (all agents buyer contacted)
- Saved listings (bookmark toggle)
"""

import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, func
from sqlalchemy.orm import selectinload
import uuid

from app.models.lead import Lead, SavedListing
from app.models.listing import Listing
from app.models.user import User, AgentProfile
from app.models.promotion import PromotionHistory
from app.schemas.lead import AgentLead, BuyerLead, SavedListingItem
from app.repositories.listing_repo import transform_public_listing

logger = logging.getLogger(__name__)


# ============================================================================
# LEAD DEDUPLICATION CHECK
# ============================================================================

async def check_lead_exists(
    db: AsyncSession,
    buyer_id: str,
    listing_id: str,
    interaction_type: str
) -> bool:
    """
    Check if lead already exists for this buyer+listing+interaction_type combination.

    Deduplication rule:
    - One lead per buyer + listing + interaction_type
    - Same buyer can create 3 leads for same listing (WhatsApp, phone, email)

    Args:
        db: Database session
        buyer_id: Buyer UUID
        listing_id: Listing UUID
        interaction_type: "whatsapp" | "phone" | "email"

    Returns:
        True if lead exists, False otherwise

    Example:
        >>> exists = await check_lead_exists(db, buyer_id, listing_id, "whatsapp")
        >>> if exists:
        ...     raise HTTPException(409, "Lead already exists")
    """
    result = await db.execute(
        select(Lead)
        .where(
            and_(
                Lead.buyer_id == buyer_id,
                Lead.listing_id == listing_id,
                Lead.interaction_type == interaction_type
            )
        )
    )

    return result.scalar_one_or_none() is not None


# ============================================================================
# CREATE LEAD
# ============================================================================

async def create_lead(
    db: AsyncSession,
    buyer_id: str,
    listing_id: str,
    agent_id: str,
    interaction_type: str
) -> Lead:
    """
    Create new lead after deduplication check.

    IMPORTANT: Call check_lead_exists() before this function.

    Args:
        db: Database session
        buyer_id: Buyer UUID
        listing_id: Listing UUID
        agent_id: Agent UUID
        interaction_type: "whatsapp" | "phone" | "email"

    Returns:
        Created lead object

    Example:
        >>> if not await check_lead_exists(db, buyer_id, listing_id, "whatsapp"):
        ...     lead = await create_lead(db, buyer_id, listing_id, agent_id, "whatsapp")
    """
    lead = Lead(
        id=uuid.uuid4(),
        buyer_id=buyer_id,
        listing_id=listing_id,
        agent_id=agent_id,
        interaction_type=interaction_type
    )

    db.add(lead)

    # Increment leads_during_promotion if listing has active promotion (no-op if not promoted)
    await db.execute(
        update(PromotionHistory)
        .where(
            PromotionHistory.listing_id == listing_id,
            PromotionHistory.status == "active"
        )
        .values(leads_during_promotion=PromotionHistory.leads_during_promotion + 1)
    )

    await db.flush()

    logger.info(f"Created lead: buyer={buyer_id}, listing={listing_id}, type={interaction_type}")
    return lead


# ============================================================================
# GET AGENT LEADS
# ============================================================================

async def get_agent_leads(
    db: AsyncSession,
    agent_id: str,
    page: int = 1,
    limit: int = 20
) -> tuple[list[AgentLead], int]:
    """
    Get paginated leads for an agent (buyers who contacted their listings).

    Args:
        db: Database session
        agent_id: Agent UUID
        page: Page number (1-based)
        limit: Items per page

    Returns:
        Tuple of (leads_list, total_count)
    """
    base_query = (
        select(Lead)
        .join(Listing, Lead.listing_id == Listing.id)
        .join(User, Lead.buyer_id == User.id)
        .options(
            selectinload(Lead.buyer),
            selectinload(Lead.listing)
        )
        .where(Lead.agent_id == agent_id)
        .order_by(Lead.created_at.desc())
    )

    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * limit
    result = await db.execute(base_query.offset(offset).limit(limit))
    leads = result.scalars().all()

    leads_list = [
        AgentLead(
            id=lead.id, listing_id=lead.listing_id,
            listing_title=lead.listing.public_title_en,
            listing_asking_price_eur=lead.listing.asking_price_eur,
            buyer_id=lead.buyer_id,
            buyer_name=lead.buyer.name, buyer_email=lead.buyer.email,
            buyer_company=lead.buyer.company_name if lead.buyer else None,
            interaction_type=lead.interaction_type, created_at=lead.created_at,
        )
        for lead in leads
    ]

    logger.info(f"Fetched {len(leads_list)} leads for agent {agent_id} (page {page}, total: {total})")
    return leads_list, total


# ============================================================================
# GET BUYER LEADS
# ============================================================================

async def get_buyer_leads(
    db: AsyncSession,
    buyer_id: str,
    page: int = 1,
    limit: int = 20
) -> tuple[list[BuyerLead], int]:
    """
    Get paginated leads for a buyer (agents buyer contacted).

    Args:
        db: Database session
        buyer_id: Buyer UUID
        page: Page number (1-based)
        limit: Items per page

    Returns:
        Tuple of (leads_list, total_count)
    """
    base_query = (
        select(Lead)
        .join(Listing, Lead.listing_id == Listing.id)
        .join(User, Lead.agent_id == User.id)
        .options(
            selectinload(Lead.agent).selectinload(User.agent_profile),
            selectinload(Lead.listing)
        )
        .where(Lead.buyer_id == buyer_id)
        .order_by(Lead.created_at.desc())
    )

    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * limit
    result = await db.execute(base_query.offset(offset).limit(limit))
    leads = result.scalars().all()

    leads_list = [
        BuyerLead(
            id=lead.id, listing_id=lead.listing_id,
            listing_title=lead.listing.public_title_en,
            listing_asking_price_eur=lead.listing.asking_price_eur,
            agent_id=lead.agent_id,
            agent_name=lead.agent.name,
            agent_agency_name=lead.agent.company_name,
            agent_email=lead.agent.email,
            agent_phone=lead.agent.phone_number,
            agent_whatsapp=lead.agent.agent_profile.whatsapp_number if lead.agent.agent_profile else None,
            interaction_type=lead.interaction_type, created_at=lead.created_at,
        )
        for lead in leads
    ]

    logger.info(f"Fetched {len(leads_list)} leads for buyer {buyer_id} (page {page}, total: {total})")
    return leads_list, total


# ============================================================================
# SAVED LISTINGS (BOOKMARKS)
# ============================================================================

async def toggle_saved_listing(
    db: AsyncSession,
    buyer_id: str,
    listing_id: str
) -> tuple[bool, str]:
    """
    Toggle saved listing (bookmark).

    If saved: Unsave (delete)
    If not saved: Save (create)

    Args:
        db: Database session
        buyer_id: Buyer UUID
        listing_id: Listing UUID

    Returns:
        Tuple of (is_saved_now, message)

    Example:
        >>> is_saved, message = await toggle_saved_listing(db, buyer_id, listing_id)
        >>> print(message)  # "Listing saved" or "Listing unsaved"
    """
    # Check if already saved
    result = await db.execute(
        select(SavedListing)
        .where(
            and_(
                SavedListing.buyer_id == buyer_id,
                SavedListing.listing_id == listing_id
            )
        )
    )
    saved = result.scalar_one_or_none()

    if saved:
        # Already saved → Unsave
        await db.delete(saved)
        await db.flush()
        logger.info(f"Unsaved listing {listing_id} for buyer {buyer_id}")
        return False, "Listing removed from saved"
    else:
        # Not saved → Save
        saved = SavedListing(
            buyer_id=buyer_id,
            listing_id=listing_id
        )
        db.add(saved)
        await db.flush()
        logger.info(f"Saved listing {listing_id} for buyer {buyer_id}")
        return True, "Listing saved successfully"


async def get_saved_listings(
    db: AsyncSession,
    buyer_id: str,
    page: int = 1,
    limit: int = 20
) -> tuple[list[SavedListingItem], int]:
    """
    Get paginated saved listings for a buyer.

    Args:
        db: Database session
        buyer_id: Buyer UUID
        page: Page number (1-based)
        limit: Items per page

    Returns:
        Tuple of (listings_list, total_count)
    """
    base_query = (
        select(SavedListing, Listing, User)
        .join(Listing, SavedListing.listing_id == Listing.id)
        .join(User, Listing.agent_id == User.id)
        .options(
            selectinload(Listing.images),
            selectinload(User.agent_profile)
        )
        .where(SavedListing.buyer_id == buyer_id)
        .order_by(SavedListing.created_at.desc())
    )

    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * limit
    result = await db.execute(base_query.offset(offset).limit(limit))
    rows = result.all()

    listings_list = []
    for saved_listing, listing, agent in rows:
        public = transform_public_listing(listing, agent)
        saved_item = SavedListingItem(
            **public.model_dump(),
            saved_at=saved_listing.created_at
        )
        listings_list.append(saved_item)

    logger.info(f"Fetched {len(listings_list)} saved listings for buyer {buyer_id} (page {page}, total: {total})")
    return listings_list, total
