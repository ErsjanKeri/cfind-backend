"""
Lead and saved listing routes.

Endpoints:
- POST /leads - Create new lead (buyer contacts agent via listing)
- GET /leads/agent/{agent_id} - Get all leads for agent
- GET /leads/buyer/{buyer_id} - Get all leads for buyer
- POST /saved/{listing_id} - Toggle save/unsave listing
- GET /saved - Get all saved listings for current buyer
"""

from typing import Annotated, List
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.api.deps import (
    get_verified_user,
    verify_csrf_token,
    RoleChecker
)
from app.services import lead_service

# Initialize router
router = APIRouter(prefix="/leads", tags=["Leads"])


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class LeadCreate(BaseModel):
    """Request schema for creating lead."""

    listing_id: str = Field(..., min_length=36, max_length=36)
    interaction_type: str = Field(..., pattern="^(whatsapp|phone|email)$")

    model_config = {
        "json_schema_extra": {
            "example": {
                "listing_id": "123e4567-e89b-12d3-a456-426614174000",
                "interaction_type": "whatsapp"
            }
        }
    }


class LeadResponse(BaseModel):
    """Response schema for lead."""

    id: str
    listing_id: str
    listing_title: str
    agent_id: str
    agent_name: str
    interaction_type: str
    created_at: str


class LeadCreateResponse(BaseModel):
    """Response schema for lead creation."""

    success: bool = True
    message: str = "Lead created successfully. Agent contact information is visible on the listing."
    lead: dict


class AgentLeadsResponse(BaseModel):
    """Response schema for agent's leads."""

    success: bool = True
    total: int
    leads: List[dict]


class BuyerLeadsResponse(BaseModel):
    """Response schema for buyer's leads."""

    success: bool = True
    total: int
    leads: List[dict]


class SavedListingToggleResponse(BaseModel):
    """Response schema for toggling saved listing."""

    success: bool = True
    message: str
    is_saved: bool


class SavedListingsResponse(BaseModel):
    """Response schema for saved listings."""

    success: bool = True
    total: int
    listings: List[dict]


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
    lead_data: LeadCreate,
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
    lead_dict = await lead_service.create_lead_service(
        db,
        str(current_user.id),
        lead_data.listing_id,
        lead_data.interaction_type
    )

    return LeadCreateResponse(
        success=True,
        message="Lead created successfully. Agent contact information is visible on the listing.",
        lead=lead_dict
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
    db: AsyncSession = Depends(get_db)
):
    """
    Get all leads for an agent.

    **Authorization:**
    - Agent can view their own leads
    - Admin can view any agent's leads

    **Returns:**
    - Buyer details (name, email, company)
    - Listing details (title, price)
    - Interaction type (whatsapp, phone, email)
    - Contact timestamp

    Useful for agents to:
    - See who's interested in their listings
    - Track buyer engagement
    - Follow up with potential buyers
    """
    leads = await lead_service.get_agent_leads_service(
        db,
        agent_id,
        current_user
    )

    return AgentLeadsResponse(
        success=True,
        total=len(leads),
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
    db: AsyncSession = Depends(get_db)
):
    """
    Get all leads for a buyer.

    **Authorization:**
    - Buyer can view their own leads
    - Admin can view any buyer's leads

    **Returns:**
    - Agent details (name, agency, phone, WhatsApp, email)
    - Listing details (title, price)
    - Interaction type
    - Contact timestamp

    Useful for buyers to:
    - Track which agents they've contacted
    - Review contact history
    - Follow up on inquiries
    """
    leads = await lead_service.get_buyer_leads_service(
        db,
        buyer_id,
        current_user
    )

    return BuyerLeadsResponse(
        success=True,
        total=len(leads),
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
    is_saved, message = await lead_service.toggle_saved_listing_service(
        db,
        str(current_user.id),
        listing_id
    )

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
    db: AsyncSession = Depends(get_db)
):
    """
    Get all saved listings for current buyer.

    **Returns:**
    - Listings (public view)
    - Saved timestamp
    - Sorted by save date (newest first)

    **Note:**
    If a listing becomes invisible (agent loses verification, status changes),
    it's soft-deleted from saved listings (won't appear in results).
    """
    saved_listings = await lead_service.get_saved_listings_service(
        db,
        str(current_user.id)
    )

    return SavedListingsResponse(
        success=True,
        total=len(saved_listings),
        listings=saved_listings
    )
