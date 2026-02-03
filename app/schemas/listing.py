"""Pydantic schemas for listing operations."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

from app.schemas.base import BaseSchema


# ============================================================================
# LISTING IMAGE
# ============================================================================

class ListingImageSchema(BaseModel):
    """Listing image schema."""

    id: str
    url: str
    order: int
    created_at: datetime

    model_config = {
        "from_attributes": True
    }


class ListingImageCreate(BaseModel):
    """Schema for creating listing image."""

    url: str
    order: int = 0


# ============================================================================
# LISTING CREATE
# ============================================================================

class ListingCreate(BaseModel):
    """
    Schema for creating a new listing.

    Required:
    - Public information (what buyers see)
    - Private information (real business details)
    - Financials (dual currency: EUR and LEK)
    - At least 1 image

    Optional:
    - Employee count, years in operation
    - Real description, coordinates
    """

    # ========================================================================
    # PRIVATE INFORMATION (owner/admin only)
    # ========================================================================
    real_business_name: str = Field(..., min_length=2, max_length=200)
    real_location_address: str = Field(..., min_length=5, max_length=500)
    real_location_lat: Optional[float] = Field(None, ge=-90, le=90)
    real_location_lng: Optional[float] = Field(None, ge=-180, le=180)
    real_description_en: Optional[str] = Field(None, max_length=5000)

    # ========================================================================
    # PUBLIC INFORMATION (visible to all)
    # ========================================================================
    public_title_en: str = Field(..., min_length=5, max_length=200)
    public_description_en: str = Field(..., min_length=20, max_length=2000)
    category: str = Field(..., min_length=2, max_length=50)
    public_location_city_en: str = Field(..., min_length=2, max_length=100)
    public_location_area: Optional[str] = Field(None, max_length=100)

    # ========================================================================
    # FINANCIALS (dual currency)
    # ========================================================================
    asking_price_eur: Decimal = Field(..., gt=0)
    asking_price_lek: Decimal = Field(..., gt=0)
    monthly_revenue_eur: Optional[Decimal] = Field(None, ge=0)
    monthly_revenue_lek: Optional[Decimal] = Field(None, ge=0)

    # ========================================================================
    # BUSINESS DETAILS
    # ========================================================================
    employee_count: Optional[int] = Field(None, ge=0)
    years_in_operation: Optional[int] = Field(None, ge=0)

    # ========================================================================
    # IMAGES (at least 1 required)
    # ========================================================================
    images: List[ListingImageCreate] = Field(..., min_length=1, max_length=50)

    # ========================================================================
    # ADMIN FIELDS (optional, only for admin creating on behalf of agent)
    # ========================================================================
    agent_id: Optional[str] = None  # Admin can create listing for specific agent
    status: Optional[str] = Field(default="active", pattern="^(draft|active|sold|inactive)$")

    model_config = {
        "json_schema_extra": {
            "example": {
                "real_business_name": "Best Restaurant Tirana",
                "real_location_address": "Rruga Durrësit 123, Tirana",
                "real_location_lat": 41.3275,
                "real_location_lng": 19.8187,
                "public_title_en": "Established Restaurant in Prime Location",
                "public_description_en": "Well-established restaurant with loyal customer base and prime location in Tirana. Fully equipped kitchen and seating for 60 people.",
                "category": "restaurant",
                "public_location_city_en": "Tirana",
                "public_location_area": "City Center",
                "asking_price_eur": 150000,
                "asking_price_lek": 15000000,
                "monthly_revenue_eur": 8000,
                "monthly_revenue_lek": 800000,
                "employee_count": 8,
                "years_in_operation": 5,
                "images": [
                    {"url": "https://s3.amazonaws.com/image1.jpg", "order": 0},
                    {"url": "https://s3.amazonaws.com/image2.jpg", "order": 1}
                ]
            }
        }
    }


# ============================================================================
# LISTING UPDATE
# ============================================================================

class ListingUpdate(BaseModel):
    """
    Schema for updating an existing listing.

    All fields are optional. Only provided fields will be updated.
    """

    # Private information
    real_business_name: Optional[str] = Field(None, min_length=2, max_length=200)
    real_location_address: Optional[str] = Field(None, min_length=5, max_length=500)
    real_location_lat: Optional[float] = Field(None, ge=-90, le=90)
    real_location_lng: Optional[float] = Field(None, ge=-180, le=180)
    real_description_en: Optional[str] = Field(None, max_length=5000)

    # Public information
    public_title_en: Optional[str] = Field(None, min_length=5, max_length=200)
    public_description_en: Optional[str] = Field(None, min_length=20, max_length=2000)
    category: Optional[str] = Field(None, min_length=2, max_length=50)
    public_location_city_en: Optional[str] = Field(None, min_length=2, max_length=100)
    public_location_area: Optional[str] = Field(None, max_length=100)

    # Financials
    asking_price_eur: Optional[Decimal] = Field(None, gt=0)
    asking_price_lek: Optional[Decimal] = Field(None, gt=0)
    monthly_revenue_eur: Optional[Decimal] = Field(None, ge=0)
    monthly_revenue_lek: Optional[Decimal] = Field(None, ge=0)

    # Business details
    employee_count: Optional[int] = Field(None, ge=0)
    years_in_operation: Optional[int] = Field(None, ge=0)

    # Status
    status: Optional[str] = Field(None, pattern="^(draft|active|sold|inactive)$")

    # Images (if provided, replaces all existing images)
    images: Optional[List[ListingImageCreate]] = Field(None, min_length=1, max_length=50)

    # Admin-only field
    is_physically_verified: Optional[bool] = None


# ============================================================================
# LISTING RESPONSE (PUBLIC)
# ============================================================================

class ListingPublic(BaseModel):
    """
    Public listing response - hides sensitive information.

    Hidden fields:
    - real_business_name
    - real_location_address (exact address)
    - real_location_lat, real_location_lng (coordinates)
    - real_description_en

    Shown fields:
    - Public title, description
    - Approximate location (city, area only)
    - Financials (asking price, revenue, ROI)
    - Images, basic stats
    """

    id: str
    agent_id: str
    status: str

    # Promotion
    promotion_tier: str
    promotion_start_date: Optional[datetime] = None
    promotion_end_date: Optional[datetime] = None

    # Public information (sanitized)
    public_title_en: str
    public_description_en: str
    category: str
    public_location_city_en: str
    public_location_area: Optional[str] = None

    # Financials (shown to help buyers assess)
    asking_price_eur: float
    asking_price_lek: float
    monthly_revenue_eur: Optional[float] = None
    monthly_revenue_lek: Optional[float] = None
    roi: Optional[float] = None

    # Business details
    employee_count: Optional[int] = None
    years_in_operation: Optional[int] = None
    is_physically_verified: bool

    # Images
    images: List[ListingImageSchema]

    # Metadata
    view_count: int
    created_at: datetime
    updated_at: datetime

    # Agent info (name and contact - shown immediately)
    agent_name: Optional[str] = None
    agent_agency_name: Optional[str] = None
    agent_phone: Optional[str] = None
    agent_whatsapp: Optional[str] = None
    agent_email: Optional[str] = None

    model_config = {
        "from_attributes": True
    }


# ============================================================================
# LISTING RESPONSE (PRIVATE)
# ============================================================================

class ListingPrivate(BaseModel):
    """
    Private listing response - shows ALL information.

    Visible to:
    - Listing owner (agent)
    - Admin

    Shows everything including:
    - Real business name
    - Exact address and coordinates
    - Private description
    """

    id: str
    agent_id: str
    status: str

    # Promotion
    promotion_tier: str
    promotion_start_date: Optional[datetime] = None
    promotion_end_date: Optional[datetime] = None

    # PUBLIC information
    public_title_en: str
    public_description_en: str
    category: str
    public_location_city_en: str
    public_location_area: Optional[str] = None

    # PRIVATE information (full business details)
    real_business_name: Optional[str] = None
    real_location_address: Optional[str] = None
    real_location_lat: Optional[float] = None
    real_location_lng: Optional[float] = None
    real_description_en: Optional[str] = None

    # Financials
    asking_price_eur: float
    asking_price_lek: float
    monthly_revenue_eur: Optional[float] = None
    monthly_revenue_lek: Optional[float] = None
    roi: Optional[float] = None

    # Business details
    employee_count: Optional[int] = None
    years_in_operation: Optional[int] = None
    is_physically_verified: bool

    # Images
    images: List[ListingImageSchema]

    # Metadata
    view_count: int
    created_at: datetime
    updated_at: datetime

    # Agent info
    agent_name: Optional[str] = None
    agent_agency_name: Optional[str] = None
    agent_phone: Optional[str] = None
    agent_whatsapp: Optional[str] = None
    agent_email: Optional[str] = None

    model_config = {
        "from_attributes": True
    }


# ============================================================================
# LISTING SEARCH & FILTER
# ============================================================================

class ListingSearchParams(BaseModel):
    """Search and filter parameters for listings."""

    # Filters
    category: Optional[str] = None
    city: Optional[str] = None
    area: Optional[str] = None

    # Price range (EUR)
    min_price_eur: Optional[Decimal] = Field(None, ge=0)
    max_price_eur: Optional[Decimal] = Field(None, ge=0)

    # Price range (LEK)
    min_price_lek: Optional[Decimal] = Field(None, ge=0)
    max_price_lek: Optional[Decimal] = Field(None, ge=0)

    # ROI range
    min_roi: Optional[Decimal] = Field(None, ge=0)
    max_roi: Optional[Decimal] = Field(None, ge=0)

    # Full-text search
    search: Optional[str] = Field(None, max_length=200)

    # Sorting
    # Options: "newest", "price_low", "price_high", "roi_high", "roi_low", "most_viewed"
    sort_by: Optional[str] = Field(default="newest", pattern="^(newest|price_low|price_high|roi_high|roi_low|most_viewed)$")

    # Pagination
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)

    # Filter by verified agents only (default: true)
    verified_agents_only: bool = True


class ListingSearchResponse(BaseSchema):
    """Response for listing search."""

    success: bool = True
    total: int
    page: int
    limit: int
    total_pages: int
    listings: List[ListingPublic]


# ============================================================================
# LISTING CRUD RESPONSES
# ============================================================================

class ListingCreateResponse(BaseSchema):
    """Response for listing creation."""

    success: bool = True
    message: str = "Listing created successfully"
    listing: ListingPrivate  # Return private view to creator


class ListingUpdateResponse(BaseSchema):
    """Response for listing update."""

    success: bool = True
    message: str = "Listing updated successfully"
    listing: ListingPrivate  # Return private view to owner


class ListingDeleteResponse(BaseSchema):
    """Response for listing deletion."""

    success: bool = True
    message: str = "Listing deleted successfully"


# ============================================================================
# AGENT LISTINGS
# ============================================================================

class AgentListingsResponse(BaseSchema):
    """Response for agent's listings."""

    success: bool = True
    total: int
    listings: List[ListingPrivate]  # Agent sees private view of their own listings
