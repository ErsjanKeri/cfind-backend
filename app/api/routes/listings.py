"""
Listing routes.

Endpoints:
- GET /listings - Search and filter public listings
- GET /listings/{id} - Get single listing (public or private based on auth)
- POST /listings - Create new listing (verified agent or admin)
- PUT /listings/{id} - Update listing (owner or admin)
- DELETE /listings/{id} - Delete listing (owner or admin)
- GET /listings/agent/{agent_id} - Get agent's listings (owner or admin)
"""

from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.listing import (
    ListingCreate, ListingCreateResponse,
    ListingUpdate, ListingUpdateResponse,
    ListingDeleteResponse,
    ListingPublic, ListingPrivate,
    ListingSearchParams, ListingSearchResponse,
    ListingGetResponse,
    AgentListingsResponse
)
from app.api.deps import (
    get_current_user_optional,
    get_verified_agent,
    verify_csrf_token,
    RoleChecker,
    ensure_owner_or_admin
)
from app.repositories import listing_repo
from app.repositories.user_repo import get_user_by_id
from app.core.constants import VALID_COUNTRY_CODES

# Initialize router
router = APIRouter(prefix="/listings", tags=["Listings"])


# ============================================================================
# SEARCH LISTINGS (PUBLIC)
# ============================================================================

@router.get(
    "",
    response_model=ListingSearchResponse,
    summary="Search listings",
    description="Search and filter public listings with pagination"
)
async def search_listings(
    # Country (required)
    country_code: str = Query(..., min_length=2, max_length=2, description="Country code (e.g. al, ae)"),

    # Filters
    category: Optional[str] = Query(None, description="Business category"),
    city: Optional[str] = Query(None, description="City name"),
    area: Optional[str] = Query(None, description="Area/neighborhood"),

    # Price range (EUR)
    min_price_eur: Optional[float] = Query(None, ge=0, description="Minimum price in EUR"),
    max_price_eur: Optional[float] = Query(None, ge=0, description="Maximum price in EUR"),

    # ROI range
    min_roi: Optional[float] = Query(None, ge=0, description="Minimum ROI percentage"),
    max_roi: Optional[float] = Query(None, ge=0, description="Maximum ROI percentage"),

    # Search
    search: Optional[str] = Query(None, max_length=200, description="Full-text search across title, description, category, city, area"),

    # Sorting
    sort_by: str = Query(
        default="newest",
        pattern="^(newest|price_low|price_high|roi_high|roi_low|most_viewed)$",
        description="Sort order: newest, price_low, price_high, roi_high, roi_low, most_viewed"
    ),

    # Pagination
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page"),

    # Database
    db: AsyncSession = Depends(get_db)
):
    """
    Search and filter public listings.

    **Public visibility rules:**
    - Only shows listings with status = "active"
    - Only shows listings from verified agents
    - Hides real business name and exact address
    - Shows public information only

    **Promotion tier sorting:**
    - Premium listings appear first
    - Then Featured listings
    - Then Standard listings
    - Within each tier, secondary sort applied (newest, price, etc.)

    **Full-text search:**
    - Searches across: public_title_en, public_description_en, category, city, area

    **Returns:**
    - Listings (public view)
    - Total count
    - Pagination info
    """
    # Build search params
    search_params = ListingSearchParams(
        country_code=country_code,
        category=category,
        city=city,
        area=area,
        min_price_eur=min_price_eur,
        max_price_eur=max_price_eur,
        min_roi=min_roi,
        max_roi=max_roi,
        search=search,
        sort_by=sort_by,
        page=page,
        limit=limit,
        verified_agents_only=True
    )

    # Execute search
    listings, total = await listing_repo.get_listings(db, search_params, mode="public")
    total_pages = (total + limit - 1) // limit

    return ListingSearchResponse(
        success=True,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
        listings=listings
    )


# ============================================================================
# GET SINGLE LISTING
# ============================================================================

@router.get(
    "/{listing_id}",
    response_model=ListingGetResponse,
    summary="Get listing by ID",
    description="Get single listing (public view for anonymous, private view for owner/admin)"
)
async def get_listing(
    listing_id: str,
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get single listing by ID.

    **Visibility:**
    - Anonymous users: Public view (no real business name, no exact address)
    - Authenticated users: Public view
    - Listing owner: Private view (full details)
    - Admin: Private view (full details)

    **Note:** This endpoint does NOT require authentication.
    Public listings are accessible to everyone.
    """
    result = await listing_repo.get_listing_by_id(db, listing_id, mode="public")
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")

    listing, agent = result

    # Owner or admin sees private view, everyone else sees public
    if current_user and (str(listing.agent_id) == str(current_user.id) or current_user.role == "admin"):
        listing_dict = listing_repo.transform_private_listing(listing, agent)
    else:
        listing_dict = listing_repo.transform_public_listing(listing, agent)

    return ListingGetResponse(
        success=True,
        listing=listing_dict
    )


# ============================================================================
# CREATE LISTING
# ============================================================================

@router.post(
    "",
    response_model=ListingCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create listing",
    description="Create new business listing (verified agent or admin only)"
)
async def create_listing(
    listing_data: ListingCreate,
    current_user: Annotated[User, Depends(get_verified_agent)],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Create new business listing.

    **Requirements:**
    - User must be verified agent with all documents uploaded
    - OR user is admin (can create on behalf of agents)
    - At least 1 image required
    - Dual currency (EUR + LEK) required

    **Auto-calculated fields:**
    - ROI: (monthly_revenue * 12) / asking_price * 100
    - Created timestamp

    **Default status:** "active" (published immediately)

    **Returns:** Private view (creator sees full details including real business name)
    """
    # Determine agent_id (admin can create on behalf of another agent)
    # Note: get_verified_agent already ensures user is a verified agent OR admin
    if current_user.role == "admin" and listing_data.agent_id:
        agent_id = listing_data.agent_id
        target_agent = await get_user_by_id(db, agent_id, include_profiles=True)
        if not target_agent or target_agent.role != "agent":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid agent ID")
    else:
        agent_id = str(current_user.id)

    # Validate country matches agent's operating country (skip for admins)
    if current_user.role != "admin":
        agent_profile = current_user.agent_profile
        if agent_profile and agent_profile.operating_country and listing_data.country_code != agent_profile.operating_country:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Listing country must match your operating country ({agent_profile.operating_country})"
            )

    # Validate country code
    if listing_data.country_code not in VALID_COUNTRY_CODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid country code. Must be one of: {', '.join(VALID_COUNTRY_CODES)}"
        )

    # Validate images
    if not listing_data.images or len(listing_data.images) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one image is required")

    # Create listing and return private view
    listing = await listing_repo.create_listing(db, agent_id, listing_data)
    # Use target_agent if admin created on behalf, otherwise current_user already has agent_profile
    agent_for_response = target_agent if (current_user.role == "admin" and listing_data.agent_id) else current_user
    listing_dict = listing_repo.transform_private_listing(listing, agent_for_response)

    return ListingCreateResponse(
        success=True,
        message="Listing created successfully",
        listing=listing_dict
    )


# ============================================================================
# UPDATE LISTING
# ============================================================================

@router.put(
    "/{listing_id}",
    response_model=ListingUpdateResponse,
    summary="Update listing",
    description="Update listing (owner or admin only)"
)
async def update_listing(
    listing_id: str,
    update_data: ListingUpdate,
    current_user: Annotated[User, Depends(get_verified_agent)],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Update existing listing.

    **Authorization:**
    - Listing owner (agent) can update their own listings
    - Admin can update any listing

    **Admin-only fields:**
    - is_physically_verified (set after on-site visit)

    **Auto-recalculated:**
    - ROI (if revenue or price changes)

    **Returns:** Private view (owner sees full details)
    """
    # Fetch listing
    result = await listing_repo.get_listing_by_id(db, listing_id, mode="private")
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")

    listing, agent = result

    ensure_owner_or_admin(listing.agent_id, current_user, "You are not authorized to update this listing")

    # Update and return private view (reuse agent from initial fetch)
    updated_listing = await listing_repo.update_listing(db, listing_id, update_data)
    listing_dict = listing_repo.transform_private_listing(updated_listing, agent)

    return ListingUpdateResponse(
        success=True,
        message="Listing updated successfully",
        listing=listing_dict
    )


# ============================================================================
# DELETE LISTING
# ============================================================================

@router.delete(
    "/{listing_id}",
    response_model=ListingDeleteResponse,
    summary="Delete listing",
    description="Delete listing (owner or admin only)"
)
async def delete_listing(
    listing_id: str,
    current_user: Annotated[User, Depends(get_verified_agent)],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete listing.

    **Authorization:**
    - Listing owner (agent) can delete their own listings
    - Admin can delete any listing

    **Cascade deletion:**
    - All listing images
    - All leads for this listing
    - All saved listings bookmarks
    - All promotion history
    """
    # Fetch listing
    result = await listing_repo.get_listing_by_id(db, listing_id, mode="private")
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")

    listing, agent = result

    ensure_owner_or_admin(listing.agent_id, current_user, "You are not authorized to delete this listing")

    await listing_repo.delete_listing(db, listing_id)

    return ListingDeleteResponse(
        success=True,
        message="Listing deleted successfully"
    )


# ============================================================================
# GET AGENT'S LISTINGS
# ============================================================================

@router.get(
    "/agent/{agent_id}",
    response_model=AgentListingsResponse,
    summary="Get agent's listings",
    description="Get all listings for a specific agent (owner or admin only)"
)
async def get_agent_listings(
    agent_id: str,
    current_user: Annotated[User, Depends(RoleChecker(["agent", "admin"]))],
    db: AsyncSession = Depends(get_db)
):
    """
    Get all listings for a specific agent.

    **Authorization:**
    - Agent can view their own listings (private view)
    - Admin can view any agent's listings (private view)

    **Returns:**
    - ALL listings (draft, active, sold, inactive)
    - Private view (full details including real business name)
    - Sorted by creation date (newest first)
    """
    ensure_owner_or_admin(agent_id, current_user, "You are not authorized to view these listings")

    listings = await listing_repo.get_agent_listings(db, agent_id)

    return AgentListingsResponse(
        success=True,
        total=len(listings),
        listings=listings
    )
