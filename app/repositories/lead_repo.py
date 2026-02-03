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
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_
from sqlalchemy.orm import selectinload, joinedload
from fastapi import HTTPException, status
import uuid

from app.models.lead import Lead, SavedListing
from app.models.listing import Listing
from app.models.user import User, AgentProfile

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
    await db.commit()
    await db.refresh(lead)

    logger.info(f"Created lead: buyer={buyer_id}, listing={listing_id}, type={interaction_type}")
    return lead


# ============================================================================
# GET AGENT LEADS
# ============================================================================

async def get_agent_leads(
    db: AsyncSession,
    agent_id: str
) -> List[dict]:
    """
    Get all leads for an agent (all buyers who contacted their listings).

    Returns leads with:
    - Buyer details (name, email, company)
    - Listing details (title, asking price)
    - Interaction type
    - Contact timestamp

    Args:
        db: Database session
        agent_id: Agent UUID

    Returns:
        List of lead dicts with buyer and listing details

    Example:
        >>> leads = await get_agent_leads(db, agent_id="123...")
        >>> for lead in leads:
        ...     print(f"{lead['buyer_name']} contacted via {lead['interaction_type']}")
    """
    result = await db.execute(
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

    leads = result.scalars().all()

    # Transform to dict
    leads_list = []
    for lead in leads:
        leads_list.append({
            "id": str(lead.id),
            "listing_id": str(lead.listing_id),
            "listing_title": lead.listing.public_title_en,
            "listing_asking_price_eur": float(lead.listing.asking_price_eur),
            "buyer_id": str(lead.buyer_id),
            "buyer_name": lead.buyer.name,
            "buyer_email": lead.buyer.email,
            "buyer_company": lead.buyer.company_name if lead.buyer else None,  # buyer_profile removed
            "interaction_type": lead.interaction_type,
            "created_at": lead.created_at
        })

    logger.info(f"Fetched {len(leads_list)} leads for agent {agent_id}")
    return leads_list


# ============================================================================
# GET BUYER LEADS
# ============================================================================

async def get_buyer_leads(
    db: AsyncSession,
    buyer_id: str
) -> List[dict]:
    """
    Get all leads for a buyer (all agents buyer contacted).

    Returns leads with:
    - Agent details (name, agency, phone, WhatsApp, email)
    - Listing details (title, asking price)
    - Interaction type
    - Contact timestamp

    Args:
        db: Database session
        buyer_id: Buyer UUID

    Returns:
        List of lead dicts with agent and listing details

    Example:
        >>> leads = await get_buyer_leads(db, buyer_id="123...")
        >>> for lead in leads:
        ...     print(f"Contacted {lead['agent_name']} via {lead['interaction_type']}")
    """
    result = await db.execute(
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

    leads = result.scalars().all()

    # Transform to dict
    leads_list = []
    for lead in leads:
        agent_profile = lead.agent.agent_profile
        leads_list.append({
            "id": str(lead.id),
            "listing_id": str(lead.listing_id),
            "listing_title": lead.listing.public_title_en,
            "listing_asking_price_eur": float(lead.listing.asking_price_eur),
            "agent_id": str(lead.agent_id),
            "agent_name": lead.agent.name,
            "agent_agency": lead.agent.company_name,  # agency_name removed, use User.company_name
            "agent_email": lead.agent.email,
            "agent_phone": lead.agent.phone_number,  # phone_number removed, use User.phone_number
            "agent_whatsapp": agent_profile.whatsapp_number if agent_profile else None,
            "interaction_type": lead.interaction_type,
            "created_at": lead.created_at
        })

    logger.info(f"Fetched {len(leads_list)} leads for buyer {buyer_id}")
    return leads_list


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
        await db.commit()
        logger.info(f"Unsaved listing {listing_id} for buyer {buyer_id}")
        return False, "Listing removed from saved"
    else:
        # Not saved → Save
        saved = SavedListing(
            buyer_id=buyer_id,
            listing_id=listing_id
        )
        db.add(saved)
        await db.commit()
        logger.info(f"Saved listing {listing_id} for buyer {buyer_id}")
        return True, "Listing saved successfully"


async def get_saved_listings(
    db: AsyncSession,
    buyer_id: str
) -> List[dict]:
    """
    Get all saved listings for a buyer.

    Returns listings with public view (same as search results).

    Args:
        db: Database session
        buyer_id: Buyer UUID

    Returns:
        List of saved listing dicts

    Example:
        >>> saved = await get_saved_listings(db, buyer_id="123...")
        >>> print(f"Buyer has {len(saved)} saved listings")
    """
    result = await db.execute(
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

    rows = result.all()

    # Import transform function
    from app.repositories.listing_repo import transform_public_listing

    # Transform to public view
    listings_list = []
    for saved_listing, listing, agent in rows:
        listing_dict = transform_public_listing(listing, agent)
        listing_dict['saved_at'] = saved_listing.created_at
        listings_list.append(listing_dict)

    logger.info(f"Fetched {len(listings_list)} saved listings for buyer {buyer_id}")
    return listings_list


async def check_listing_is_saved(
    db: AsyncSession,
    buyer_id: str,
    listing_id: str
) -> bool:
    """
    Check if listing is saved by buyer.

    Args:
        db: Database session
        buyer_id: Buyer UUID
        listing_id: Listing UUID

    Returns:
        True if saved, False otherwise
    """
    result = await db.execute(
        select(SavedListing)
        .where(
            and_(
                SavedListing.buyer_id == buyer_id,
                SavedListing.listing_id == listing_id
            )
        )
    )

    return result.scalar_one_or_none() is not None
