"""Pydantic schemas for buyer demand operations."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

from app.schemas.base import BaseSchema
from app.core.constants import VALID_CATEGORIES


# ============================================================================
# BUYER DEMAND CREATE
# ============================================================================

class DemandCreate(BaseModel):
    """
    Schema for creating a buyer demand.

    Required:
    - Budget range (EUR)
    - Category (restaurant, bar, cafe, etc.)
    - Preferred city
    - Description (min 20 characters)

    Optional:
    - Preferred area
    - Demand type (investor or seeking_funding)
    """

    country_code: str = Field(..., min_length=2, max_length=2)

    # Budget (EUR only)
    budget_min_eur: Decimal = Field(..., gt=0, description="Minimum budget in EUR")
    budget_max_eur: Decimal = Field(..., gt=0, description="Maximum budget in EUR")

    # Category (same as Listing.category)
    category: str = Field(..., min_length=2, max_length=50)

    # Location
    preferred_city_en: str = Field(..., min_length=2, max_length=100)
    preferred_area: Optional[str] = Field(None, max_length=100)

    # Description
    description: str = Field(..., min_length=20, max_length=2000)

    # Demand type: "investor" (default) | "seeking_funding"
    demand_type: str = Field(default="investor", pattern="^(investor|seeking_funding)$")

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category. Must be one of: {', '.join(VALID_CATEGORIES)}")
        return v

    @field_validator("budget_max_eur")
    @classmethod
    def validate_max_eur_greater_than_min(cls, v: Decimal, info) -> Decimal:
        """Validate max budget >= min budget."""
        if "budget_min_eur" in info.data and v < info.data["budget_min_eur"]:
            raise ValueError("Maximum budget must be greater than or equal to minimum budget")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "budget_min_eur": 100000,
                "budget_max_eur": 250000,
                "category": "restaurant",
                "preferred_city_en": "Tirana",
                "preferred_area": "Blloku",
                "description": "Looking for a profitable restaurant in Tirana with loyal customer base and growth potential.",
                "demand_type": "investor"
            }
        }
    }


# ============================================================================
# BUYER DEMAND UPDATE
# ============================================================================

class DemandStatusUpdate(BaseModel):
    """Schema for updating demand status."""

    status: str = Field(..., pattern="^(fulfilled|closed)$")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "fulfilled"
            }
        }
    }


# ============================================================================
# BUYER DEMAND RESPONSE
# ============================================================================

class DemandResponse(BaseSchema):
    """Response schema for buyer demand."""

    id: str
    buyer_id: str
    country_code: str
    buyer_name: Optional[str] = None
    buyer_email: Optional[str] = None
    buyer_company: Optional[str] = None

    # Budget
    budget_min_eur: Decimal
    budget_max_eur: Decimal

    # Category & Location
    category: str
    preferred_city_en: str
    preferred_area: Optional[str] = None

    # Description
    description: str

    # Status & Type
    status: str  # "active" | "assigned" | "fulfilled" | "closed"
    demand_type: str  # "investor" | "seeking_funding"

    # Assignment (only populated if status = "assigned")
    assigned_agent_id: Optional[str] = None
    assigned_agent_name: Optional[str] = None
    assigned_agent_email: Optional[str] = None
    assigned_agent_phone: Optional[str] = None
    assigned_agent_whatsapp: Optional[str] = None
    assigned_at: Optional[datetime] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime


# ============================================================================
# DEMAND SEARCH & FILTER
# ============================================================================

class DemandSearchParams(BaseModel):
    """Search and filter parameters for demands."""

    country_code: str = Field(..., min_length=2, max_length=2)

    # Status filter (None = all statuses)
    status: Optional[str] = Field(None, pattern="^(active|assigned|fulfilled|closed)$")

    # Filters
    category: Optional[str] = None
    city: Optional[str] = None

    # Budget range (EUR)
    min_budget_eur: Optional[Decimal] = Field(None, ge=0)
    max_budget_eur: Optional[Decimal] = Field(None, ge=0)

    # Demand type filter
    demand_type: Optional[str] = Field(None, pattern="^(investor|seeking_funding)$")

    # Pagination
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)


# ============================================================================
# DEMAND CRUD RESPONSES
# ============================================================================

class DemandCreateResponse(BaseSchema):
    """Response for demand creation."""

    success: bool = True
    message: str = "Demand created successfully. Verified agents can now view and claim it."
    demand: DemandResponse


class DemandClaimResponse(BaseSchema):
    """Response for demand claiming."""

    success: bool = True
    message: str
    demand: DemandResponse


class DemandStatusUpdateResponse(BaseSchema):
    """Response for demand status update."""

    success: bool = True
    message: str
    demand: DemandResponse


class DemandDeleteResponse(BaseSchema):
    """Response for demand deletion."""

    success: bool = True
    message: str = "Demand deleted successfully"


class DemandsListResponse(BaseSchema):
    """Response for listing demands."""

    success: bool = True
    total: int
    page: int
    limit: int
    total_pages: int
    demands: List[DemandResponse]


class BuyerDemandsResponse(BaseSchema):
    """Response for buyer's demands."""

    success: bool = True
    total: int
    page: int
    limit: int
    total_pages: int
    demands: List[DemandResponse]


class AgentClaimedDemandsResponse(BaseSchema):
    """Response for agent's claimed demands."""

    success: bool = True
    total: int
    page: int
    limit: int
    total_pages: int
    demands: List[DemandResponse]
