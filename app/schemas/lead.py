"""
Pydantic schemas for lead and saved listing operations.

Handles:
- Lead creation (buyer contacts agent via listing)
- Agent and buyer lead views
- Saved listing management
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from app.schemas.base import BaseSchema
from app.schemas.listing import ListingPublic


# ============================================================================
# LEAD CREATION
# ============================================================================

class CreateLeadRequest(BaseModel):
    """Request for buyer to create a lead (contact agent about a listing)."""

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


class LeadCreateDetail(BaseSchema):
    """Detail of a newly created lead."""

    id: str
    listing_id: str
    listing_title: str
    agent_id: str
    agent_name: str
    interaction_type: str
    created_at: datetime


class LeadCreateResponse(BaseSchema):
    """Response after creating a lead."""

    success: bool = True
    message: str = "Lead created successfully. Agent contact information is visible on the listing."
    lead: LeadCreateDetail


# ============================================================================
# AGENT LEAD VIEW
# ============================================================================

class AgentLead(BaseSchema):
    """Agent's perspective of a lead — shows buyer information."""

    id: str
    listing_id: str
    listing_title: str
    listing_asking_price_eur: float
    buyer_id: str
    buyer_name: str
    buyer_email: str
    buyer_company: Optional[str] = None
    interaction_type: str
    created_at: datetime


class AgentLeadsResponse(BaseSchema):
    """Response containing all leads for an agent."""

    success: bool = True
    total: int
    leads: List[AgentLead]


# ============================================================================
# BUYER LEAD VIEW
# ============================================================================

class BuyerLead(BaseSchema):
    """Buyer's perspective of a lead — shows agent information."""

    id: str
    listing_id: str
    listing_title: str
    listing_asking_price_eur: float
    agent_id: str
    agent_name: str
    agent_agency: Optional[str] = None
    agent_email: str
    agent_phone: Optional[str] = None
    agent_whatsapp: Optional[str] = None
    interaction_type: str
    created_at: datetime


class BuyerLeadsResponse(BaseSchema):
    """Response containing all leads for a buyer."""

    success: bool = True
    total: int
    leads: List[BuyerLead]


# ============================================================================
# SAVED LISTINGS
# ============================================================================

class SavedListingToggleResponse(BaseSchema):
    """Response after toggling a saved listing bookmark."""

    success: bool = True
    message: str
    is_saved: bool


class SavedListingItem(ListingPublic):
    """A saved listing — public listing view plus when it was saved."""

    saved_at: datetime


class SavedListingsResponse(BaseSchema):
    """Response containing buyer's saved listings."""

    success: bool = True
    total: int
    listings: List[SavedListingItem]
