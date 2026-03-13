"""
Lead and saved listing routes.

Endpoints:
- POST /leads - Create new lead (buyer contacts agent via listing)
- GET /leads/agent/{agent_id} - Get all leads for agent
- GET /leads/buyer/{buyer_id} - Get all leads for buyer
- POST /saved/{listing_id} - Toggle save/unsave listing
- GET /saved - Get all saved listings for current buyer
"""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.models.user import User
from app.api.deps import (
    get_verified_user,
    verify_csrf_token,
    RoleChecker,
    ensure_owner_or_admin
)
from app.schemas.lead import (
    CreateLeadRequest,
    LeadCreateDetail, LeadCreateResponse,
    AgentLeadsResponse,
    BuyerLeadsResponse,
    SavedListingToggleResponse,
    SavedListingsResponse,
)
from app.repositories import lead_repo
from app.repositories.listing_repo import get_listing_by_id
from app.core.exceptions import LeadAlreadyExistsException

# Initialize router
router = APIRouter(prefix="/leads", tags=["Leads"])


# ============================================================================
# CREATE LEAD
# ============================================================================

@router.post(
    "",
    response_model=LeadCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create lead",
    description="Track buyer-agent interaction (buyer contacts agent via listing)"
)
async def create_lead(
    lead_data: CreateLeadRequest,
    current_user: Annotated[User, Depends(get_verified_user)],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Create lead (track buyer-agent contact).

    **Deduplication:**
    - One lead per buyer + listing + interaction_type
    - Buyer can create 3 leads for same listing (WhatsApp, phone, email)
    - Duplicate attempts return 409 Conflict

    **Validation:**
    - Listing must exist and be active
    - Cannot contact same listing via same method twice

    **Note:**
    Agent contact information (phone, WhatsApp, email) is visible
    immediately on listing cards. Lead creation is just for tracking.
    """
    # Validate listing exists and is active
    result = await get_listing_by_id(db, lead_data.listing_id, mode="public")
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")

    listing, agent = result
    if listing.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot contact agent for inactive listing")

    # Check deduplication (fast path)
    buyer_id = str(current_user.id)
    exists = await lead_repo.check_lead_exists(db, buyer_id, lead_data.listing_id, lead_data.interaction_type)
    if exists:
        raise LeadAlreadyExistsException()

    # Create lead (IntegrityError catches race condition if two requests pass the check simultaneously)
    try:
        lead = await lead_repo.create_lead(db, buyer_id, lead_data.listing_id, str(listing.agent_id), lead_data.interaction_type)
    except IntegrityError:
        raise LeadAlreadyExistsException()

    return LeadCreateResponse(
        success=True,
        message="Lead created successfully. Agent contact information is visible on the listing.",
        lead=LeadCreateDetail(
            id=lead.id, listing_id=lead.listing_id,
            listing_title=listing.public_title_en,
            agent_id=lead.agent_id, agent_name=agent.name,
            interaction_type=lead.interaction_type, created_at=lead.created_at,
        )
    )


# ============================================================================
# GET AGENT LEADS
# ============================================================================

@router.get(
    "/agent/{agent_id}",
    response_model=AgentLeadsResponse,
    summary="Get agent's leads",
    description="Get all buyers who contacted this agent's listings"
)
async def get_agent_leads(
    agent_id: str,
    current_user: Annotated[User, Depends(RoleChecker(["agent", "admin"]))],
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get leads for an agent with pagination.

    **Authorization:**
    - Agent can view their own leads
    - Admin can view any agent's leads

    **Returns:**
    - Buyer details (name, email, company)
    - Listing details (title, price)
    - Interaction type (whatsapp, phone, email)
    - Contact timestamp
    """
    ensure_owner_or_admin(agent_id, current_user, "You are not authorized to view these leads")

    leads, total = await lead_repo.get_agent_leads(db, agent_id, page=page, limit=limit)
    total_pages = (total + limit - 1) // limit

    return AgentLeadsResponse(
        success=True,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
        leads=leads
    )


# ============================================================================
# GET BUYER LEADS
# ============================================================================

@router.get(
    "/buyer/{buyer_id}",
    response_model=BuyerLeadsResponse,
    summary="Get buyer's leads",
    description="Get all agents this buyer has contacted"
)
async def get_buyer_leads(
    buyer_id: str,
    current_user: Annotated[User, Depends(RoleChecker(["buyer", "admin"]))],
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get leads for a buyer with pagination.

    **Authorization:**
    - Buyer can view their own leads
    - Admin can view any buyer's leads

    **Returns:**
    - Agent details (name, agency, phone, WhatsApp, email)
    - Listing details (title, price)
    - Interaction type
    - Contact timestamp
    """
    ensure_owner_or_admin(buyer_id, current_user, "You are not authorized to view these leads")

    leads, total = await lead_repo.get_buyer_leads(db, buyer_id, page=page, limit=limit)
    total_pages = (total + limit - 1) // limit

    return BuyerLeadsResponse(
        success=True,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
        leads=leads
    )


# ============================================================================
# SAVED LISTINGS (BOOKMARKS)
# ============================================================================

@router.post(
    "/saved/{listing_id}",
    response_model=SavedListingToggleResponse,
    summary="Toggle saved listing",
    description="Save or unsave a listing (bookmark)"
)
async def toggle_saved_listing(
    listing_id: str,
    current_user: Annotated[User, Depends(RoleChecker(["buyer"]))],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Toggle saved listing (bookmark).

    **Buyer-only feature.**

    If listing is saved: Unsaves it
    If listing is not saved: Saves it

    **Returns:**
    - is_saved: Current save status after toggle
    - message: Action performed
    """
    # Verify listing exists
    result = await get_listing_by_id(db, listing_id, mode="public")
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")

    is_saved, message = await lead_repo.toggle_saved_listing(db, str(current_user.id), listing_id)

    return SavedListingToggleResponse(
        success=True,
        message=message,
        is_saved=is_saved
    )


@router.get(
    "/saved",
    response_model=SavedListingsResponse,
    summary="Get saved listings",
    description="Get all saved listings for current buyer"
)
async def get_saved_listings(
    current_user: Annotated[User, Depends(RoleChecker(["buyer"]))],
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get saved listings for current buyer with pagination.

    **Returns:**
    - Listings (public view)
    - Saved timestamp
    - Sorted by save date (newest first)
    """
    saved_listings, total = await lead_repo.get_saved_listings(
        db,
        str(current_user.id),
        page=page,
        limit=limit
    )
    total_pages = (total + limit - 1) // limit

    return SavedListingsResponse(
        success=True,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
        listings=saved_listings
    )
