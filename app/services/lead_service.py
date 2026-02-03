"""
Lead service - business logic for leads and saved listings.

Handles:
- Lead creation with validation and deduplication
- Saved listings management
- Authorization checks
"""

import logging
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.user import User
from app.repositories import lead_repo
from app.repositories.listing_repo import get_listing_by_id
from app.core.exceptions import LeadAlreadyExistsException

logger = logging.getLogger(__name__)


# ============================================================================
# CREATE LEAD
# ============================================================================

async def create_lead_service(
    db: AsyncSession,
    buyer_id: str,
    listing_id: str,
    interaction_type: str
) -> dict:
    """
    Create lead with validation and deduplication.

    Checks:
    1. Listing exists and is active
    2. Lead doesn't already exist (buyer + listing + type)
    3. Buyer is not contacting their own listing (if agent)

    Args:
        db: Database session
        buyer_id: Buyer UUID
        listing_id: Listing UUID
        interaction_type: "whatsapp" | "phone" | "email"

    Returns:
        Lead dict with details

    Raises:
        HTTPException: If listing not found or not active
        LeadAlreadyExistsException: If lead already exists
    """
    # Validate interaction type
    if interaction_type not in ["whatsapp", "phone", "email"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid interaction type. Must be: whatsapp, phone, or email"
        )

    # Fetch listing
    result = await get_listing_by_id(db, listing_id, mode="public")
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found"
        )

    listing, agent = result

    # Check listing is active
    if listing.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot contact agent for inactive listing"
        )

    # Check deduplication
    exists = await lead_repo.check_lead_exists(
        db,
        buyer_id,
        listing_id,
        interaction_type
    )

    if exists:
        raise LeadAlreadyExistsException()

    # Create lead
    lead = await lead_repo.create_lead(
        db,
        buyer_id,
        listing_id,
        str(listing.agent_id),
        interaction_type
    )

    return {
        "id": str(lead.id),
        "listing_id": str(lead.listing_id),
        "listing_title": listing.public_title_en,
        "agent_id": str(lead.agent_id),
        "agent_name": agent.name,
        "interaction_type": lead.interaction_type,
        "created_at": lead.created_at
    }


# ============================================================================
# GET LEADS
# ============================================================================

async def get_agent_leads_service(
    db: AsyncSession,
    agent_id: str,
    current_user: User
) -> List[dict]:
    """
    Get agent's leads with authorization check.

    Authorization:
    - Agent can view their own leads
    - Admin can view any agent's leads

    Args:
        db: Database session
        agent_id: Agent UUID
        current_user: Current user

    Returns:
        List of leads

    Raises:
        HTTPException: If not authorized
    """
    # Check authorization
    is_owner = str(current_user.id) == agent_id
    is_admin = current_user.role == "admin"

    if not is_owner and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view these leads"
        )

    return await lead_repo.get_agent_leads(db, agent_id)


async def get_buyer_leads_service(
    db: AsyncSession,
    buyer_id: str,
    current_user: User
) -> List[dict]:
    """
    Get buyer's leads with authorization check.

    Authorization:
    - Buyer can view their own leads
    - Admin can view any buyer's leads

    Args:
        db: Database session
        buyer_id: Buyer UUID
        current_user: Current user

    Returns:
        List of leads

    Raises:
        HTTPException: If not authorized
    """
    # Check authorization
    is_owner = str(current_user.id) == buyer_id
    is_admin = current_user.role == "admin"

    if not is_owner and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view these leads"
        )

    return await lead_repo.get_buyer_leads(db, buyer_id)


# ============================================================================
# SAVED LISTINGS
# ============================================================================

async def toggle_saved_listing_service(
    db: AsyncSession,
    buyer_id: str,
    listing_id: str
) -> tuple[bool, str]:
    """
    Toggle saved listing (bookmark).

    Validates listing exists before saving.

    Args:
        db: Database session
        buyer_id: Buyer UUID
        listing_id: Listing UUID

    Returns:
        Tuple of (is_saved, message)

    Raises:
        HTTPException: If listing not found
    """
    # Verify listing exists
    result = await get_listing_by_id(db, listing_id, mode="public")
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found"
        )

    # Toggle saved status
    return await lead_repo.toggle_saved_listing(db, buyer_id, listing_id)


async def get_saved_listings_service(
    db: AsyncSession,
    buyer_id: str
) -> List[dict]:
    """
    Get buyer's saved listings.

    Args:
        db: Database session
        buyer_id: Buyer UUID

    Returns:
        List of saved listing dicts (public view)
    """
    return await lead_repo.get_saved_listings(db, buyer_id)
