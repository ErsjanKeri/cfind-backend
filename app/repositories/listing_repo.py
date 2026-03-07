"""
Listing repository - database operations for listings.

Handles:
- CRUD operations
- Public/private data transformations
- Search and filtering
- Sorting with promotion tier prioritization
- Pagination
- Visibility rules (only show listings from approved agents)
"""

import logging
import uuid
from typing import Optional, List, Tuple, Union
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_, or_, func, case, desc, asc
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.models.listing import Listing, ListingImage
from app.models.user import User, AgentProfile
from app.schemas.listing import (
    ListingCreate,
    ListingUpdate,
    ListingSearchParams,
    ListingPublic,
    ListingPrivate
)

logger = logging.getLogger(__name__)


# ============================================================================
# DATA TRANSFORMATION (PUBLIC VS PRIVATE)
# ============================================================================

def _calculate_roi(monthly_revenue, asking_price) -> Optional[float]:
    """Calculate ROI percentage from monthly revenue and asking price."""
    if monthly_revenue and asking_price:
        return round((float(monthly_revenue) * 12 / float(asking_price)) * 100, 2)
    return None


def _agent_fields(agent: User) -> dict:
    """Extract agent contact fields for listing responses."""
    return {
        "agent_name": agent.name,
        "agent_agency_name": agent.company_name,
        "agent_phone": agent.phone_number,
        "agent_whatsapp": agent.agent_profile.whatsapp_number if agent.agent_profile else None,
        "agent_email": agent.email,
    }


def transform_public_listing(listing: Listing, agent: User) -> ListingPublic:
    """Transform listing to public view — hides real business name, address, coordinates."""
    result = ListingPublic.model_validate(listing)
    return result.model_copy(update=_agent_fields(agent))


def transform_private_listing(listing: Listing, agent: User) -> ListingPrivate:
    """Transform listing to private view — includes all fields. For owner/admin."""
    result = ListingPrivate.model_validate(listing)
    return result.model_copy(update=_agent_fields(agent))


# ============================================================================
# CREATE LISTING
# ============================================================================

async def create_listing(
    db: AsyncSession,
    agent_id: str,
    listing_data: ListingCreate
) -> Listing:
    """
    Create new listing with images.

    Auto-calculates ROI from revenue and price.

    Args:
        db: Database session
        agent_id: Agent UUID (listing owner)
        listing_data: Listing creation schema

    Returns:
        Created listing object with images

    Example:
        >>> listing = await create_listing(db, agent_id="123...", listing_data=data)
        >>> print(listing.id, listing.roi)
    """
    roi = _calculate_roi(listing_data.monthly_revenue_eur, listing_data.asking_price_eur)

    # Create listing
    listing = Listing(
        id=uuid.uuid4(),
        agent_id=agent_id,
        country_code=listing_data.country_code,
        status=listing_data.status or "active",

        # Public info
        public_title_en=listing_data.public_title_en,
        public_description_en=listing_data.public_description_en,
        category=listing_data.category,
        public_location_city_en=listing_data.public_location_city_en,
        public_location_area=listing_data.public_location_area,

        # Private info
        real_business_name=listing_data.real_business_name,
        real_location_address=listing_data.real_location_address,
        real_location_lat=listing_data.real_location_lat,
        real_location_lng=listing_data.real_location_lng,
        real_description_en=listing_data.real_description_en,

        # Financials
        asking_price_eur=listing_data.asking_price_eur,
        monthly_revenue_eur=listing_data.monthly_revenue_eur,
        roi=roi,

        # Business details
        employee_count=listing_data.employee_count,
        years_in_operation=listing_data.years_in_operation,
        is_physically_verified=False  # Only admin can set this
    )

    db.add(listing)
    await db.flush()  # Get listing.id

    # Create images
    for img_data in listing_data.images:
        image = ListingImage(
            id=uuid.uuid4(),
            listing_id=listing.id,
            url=img_data.url,
            order=img_data.order
        )
        db.add(image)

    await db.commit()

    # Re-fetch with images relationship loaded (db.refresh doesn't load relationships)
    result = await db.execute(
        select(Listing)
        .options(selectinload(Listing.images))
        .where(Listing.id == listing.id)
    )
    listing = result.scalar_one()

    logger.info(f"Created listing: {listing.id} by agent {agent_id}")
    return listing


# ============================================================================
# GET LISTING BY ID
# ============================================================================

async def get_listing_by_id(
    db: AsyncSession,
    listing_id: str,
    mode: str = "public"
) -> Optional[Tuple[Listing, User]]:
    """
    Fetch listing by ID with agent info.

    Args:
        db: Database session
        listing_id: Listing UUID
        mode: "public" or "private" (determines which fields to show)

    Returns:
        Tuple of (listing, agent) or None if not found

    Example:
        >>> result = await get_listing_by_id(db, listing_id, mode="public")
        >>> if result:
        ...     listing, agent = result
        ...     public_data = transform_public_listing(listing, agent)
    """
    result = await db.execute(
        select(Listing, User)
        .join(User, Listing.agent_id == User.id)
        .options(
            selectinload(Listing.images),
            selectinload(User.agent_profile)
        )
        .where(Listing.id == listing_id)
    )

    row = result.first()
    if not row:
        return None

    listing, agent = row
    return listing, agent


# ============================================================================
# GET LISTINGS (SEARCH, FILTER, SORT)
# ============================================================================

async def get_listings(
    db: AsyncSession,
    search_params: ListingSearchParams,
    mode: str = "public"
) -> Tuple[List[Union[ListingPublic, ListingPrivate]], int]:
    """
    Search and filter listings with pagination.

    CRITICAL VISIBILITY RULES (public mode):
    - Only show listings where agent.verification_status = "approved"
    - Only show listings with status = "active"
    - Never show draft, sold, or inactive listings

    Args:
        db: Database session
        search_params: Search and filter parameters
        mode: "public" or "private"

    Returns:
        Tuple of (listings_list, total_count)

    Example:
        >>> params = ListingSearchParams(category="restaurant", city="Tirana", sort_by="price_low")
        >>> listings, total = await get_listings(db, params, mode="public")
        >>> print(f"Found {total} listings, showing page 1")
    """
    # Build base query
    query = (
        select(Listing, User)
        .join(User, Listing.agent_id == User.id)
        .join(AgentProfile, User.id == AgentProfile.user_id)
        .options(
            selectinload(Listing.images),
            selectinload(User.agent_profile)
        )
    )

    # ========================================================================
    # VISIBILITY RULES (public mode)
    # ========================================================================
    # Always filter by country
    query = query.where(Listing.country_code == search_params.country_code)

    if mode == "public":
        query = query.where(
            and_(
                Listing.status == "active",
                AgentProfile.verification_status == "approved"
            )
        )

    # ========================================================================
    # FILTERS
    # ========================================================================

    # Category filter
    if search_params.category:
        query = query.where(Listing.category == search_params.category)

    # City filter
    if search_params.city:
        query = query.where(Listing.public_location_city_en == search_params.city)

    # Area filter
    if search_params.area:
        query = query.where(Listing.public_location_area.ilike(f"%{search_params.area}%"))

    # Price range (EUR)
    if search_params.min_price_eur:
        query = query.where(Listing.asking_price_eur >= search_params.min_price_eur)
    if search_params.max_price_eur:
        query = query.where(Listing.asking_price_eur <= search_params.max_price_eur)

    # ROI range
    if search_params.min_roi:
        query = query.where(Listing.roi >= search_params.min_roi)
    if search_params.max_roi:
        query = query.where(Listing.roi <= search_params.max_roi)

    # ========================================================================
    # FULL-TEXT SEARCH
    # ========================================================================
    if search_params.search:
        search_term = f"%{search_params.search}%"
        query = query.where(
            or_(
                Listing.public_title_en.ilike(search_term),
                Listing.public_description_en.ilike(search_term),
                Listing.category.ilike(search_term),
                Listing.public_location_city_en.ilike(search_term),
                Listing.public_location_area.ilike(search_term)
            )
        )

    # ========================================================================
    # SORTING WITH PROMOTION TIER PRIORITIZATION
    # ========================================================================
    # Promotion tier priority (for tie-breaking within same tier)
    tier_priority = case(
        (Listing.promotion_tier == "premium", 3),
        (Listing.promotion_tier == "featured", 2),
        else_=1
    )

    # Apply sorting: always tier priority first, then secondary sort
    secondary_sort = {
        "newest": desc(Listing.created_at),
        "price_low": asc(Listing.asking_price_eur),
        "price_high": desc(Listing.asking_price_eur),
        "roi_high": desc(Listing.roi.nullslast()),
        "roi_low": asc(Listing.roi.nullsfirst()),
        "most_viewed": desc(Listing.view_count),
    }
    query = query.order_by(
        desc(tier_priority),
        secondary_sort.get(search_params.sort_by, desc(Listing.created_at))
    )

    # ========================================================================
    # COUNT TOTAL (before pagination)
    # ========================================================================
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # ========================================================================
    # PAGINATION
    # ========================================================================
    offset = (search_params.page - 1) * search_params.limit
    query = query.offset(offset).limit(search_params.limit)

    # Execute query
    result = await db.execute(query)
    rows = result.all()

    # Transform to public or private view
    transform = transform_private_listing if mode == "private" else transform_public_listing
    listings_list = [transform(listing, agent) for listing, agent in rows]

    logger.info(f"Fetched {len(listings_list)} listings (page {search_params.page}, total: {total})")
    return listings_list, total


# ============================================================================
# GET AGENT'S LISTINGS
# ============================================================================

async def get_agent_listings(
    db: AsyncSession,
    agent_id: str
) -> List[ListingPrivate]:
    """
    Get all listings for a specific agent (private view).

    Shows ALL listings regardless of status or verification
    (draft, active, sold, inactive).

    Args:
        db: Database session
        agent_id: Agent UUID

    Returns:
        List of listings (private view)

    Example:
        >>> listings = await get_agent_listings(db, agent_id="123...")
        >>> # Agent sees their own listings with full details
    """
    result = await db.execute(
        select(Listing, User)
        .join(User, Listing.agent_id == User.id)
        .options(
            selectinload(Listing.images),
            selectinload(User.agent_profile)
        )
        .where(Listing.agent_id == agent_id)
        .order_by(desc(Listing.created_at))
    )

    rows = result.all()

    listings_list = [transform_private_listing(listing, agent) for listing, agent in rows]

    logger.info(f"Fetched {len(listings_list)} listings for agent {agent_id}")
    return listings_list


# ============================================================================
# UPDATE LISTING
# ============================================================================

async def update_listing(
    db: AsyncSession,
    listing_id: str,
    update_data: ListingUpdate
) -> Listing:
    """
    Update listing fields.

    Recalculates ROI if revenue or price changes.

    Args:
        db: Database session
        listing_id: Listing UUID
        update_data: Update schema

    Returns:
        Updated listing object

    Raises:
        HTTPException: If listing not found
    """
    # Fetch listing with images
    result = await db.execute(
        select(Listing)
        .options(selectinload(Listing.images))
        .where(Listing.id == listing_id)
    )
    listing = result.scalar_one_or_none()

    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found"
        )

    # Apply all provided fields (images handled separately below)
    roi_fields = {"asking_price_eur", "monthly_revenue_eur"}
    recalculate_roi = False

    for field, value in update_data.model_dump(exclude_unset=True).items():
        if field == "images":
            continue
        setattr(listing, field, value)
        if field in roi_fields:
            recalculate_roi = True

    if recalculate_roi:
        listing.roi = _calculate_roi(listing.monthly_revenue_eur, listing.asking_price_eur)

    # Update images if provided
    if update_data.images is not None:
        # Delete old images
        await db.execute(
            delete(ListingImage).where(ListingImage.listing_id == listing_id)
        )

        # Create new images
        for img_data in update_data.images:
            image = ListingImage(
                id=uuid.uuid4(),
                listing_id=listing.id,
                url=img_data.url,
                order=img_data.order
            )
            db.add(image)

    listing.updated_at = datetime.now(timezone.utc)

    await db.commit()

    # Re-fetch with images relationship loaded (db.refresh doesn't load relationships)
    result = await db.execute(
        select(Listing)
        .options(selectinload(Listing.images))
        .where(Listing.id == listing.id)
    )
    listing = result.scalar_one()

    logger.info(f"Updated listing: {listing_id}")
    return listing


# ============================================================================
# DELETE LISTING
# ============================================================================

async def delete_listing(
    db: AsyncSession,
    listing_id: str
) -> bool:
    """
    Delete listing and all associated data (images, leads, etc.).

    Cascade delete handles:
    - ListingImages
    - Leads
    - SavedListings
    - PromotionHistory

    Args:
        db: Database session
        listing_id: Listing UUID

    Returns:
        True if deleted successfully

    Raises:
        HTTPException: If listing not found
    """
    result = await db.execute(
        delete(Listing).where(Listing.id == listing_id)
    )

    if result.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found"
        )

    await db.commit()
    logger.info(f"Deleted listing: {listing_id}")
    return True
