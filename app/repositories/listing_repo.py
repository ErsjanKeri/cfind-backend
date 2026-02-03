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
from typing import Optional, List, Tuple
from datetime import datetime
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_, func, case, desc, asc
from sqlalchemy.orm import selectinload, joinedload
from fastapi import HTTPException, status

from app.models.listing import Listing, ListingImage
from app.models.user import User, AgentProfile
from app.schemas.listing import (
    ListingCreate,
    ListingUpdate,
    ListingSearchParams
)

logger = logging.getLogger(__name__)


# ============================================================================
# DATA TRANSFORMATION (PUBLIC VS PRIVATE)
# ============================================================================

def transform_public_listing(listing: Listing, agent: User) -> dict:
    """
    Transform listing to public view - hides sensitive information.

    Hidden fields:
    - real_business_name
    - real_location_address (exact address)
    - real_location_lat, real_location_lng (coordinates)
    - real_description_en

    Args:
        listing: Listing object from database
        agent: Agent user object (for contact info)

    Returns:
        Dict with public fields only

    Example:
        >>> public_listing = transform_public_listing(listing, agent)
        >>> # public_listing contains no real business name or exact address
    """
    # Convert Decimal to float for JSON serialization
    asking_price_eur = float(listing.asking_price_eur) if listing.asking_price_eur else 0
    asking_price_lek = float(listing.asking_price_lek) if listing.asking_price_lek else 0
    monthly_revenue_eur = float(listing.monthly_revenue_eur) if listing.monthly_revenue_eur else None
    monthly_revenue_lek = float(listing.monthly_revenue_lek) if listing.monthly_revenue_lek else None
    roi = float(listing.roi) if listing.roi else None

    return {
        "id": str(listing.id),
        "agent_id": str(listing.agent_id),
        "status": listing.status,

        # Promotion
        "promotion_tier": listing.promotion_tier,
        "promotion_start_date": listing.promotion_start_date,
        "promotion_end_date": listing.promotion_end_date,

        # PUBLIC information only
        "public_title_en": listing.public_title_en,
        "public_description_en": listing.public_description_en,
        "category": listing.category,
        "public_location_city_en": listing.public_location_city_en,
        "public_location_area": listing.public_location_area,

        # Financials (shown to help buyers assess)
        "asking_price_eur": asking_price_eur,
        "asking_price_lek": asking_price_lek,
        "monthly_revenue_eur": monthly_revenue_eur,
        "monthly_revenue_lek": monthly_revenue_lek,
        "roi": roi,

        # Business details
        "employee_count": listing.employee_count,
        "years_in_operation": listing.years_in_operation,
        "is_physically_verified": listing.is_physically_verified,

        # Images
        "images": [
            {
                "id": str(img.id),
                "url": img.url,
                "order": img.order,
                "created_at": img.created_at
            }
            for img in sorted(listing.images, key=lambda x: x.order)
        ],

        # Metadata
        "view_count": listing.view_count,
        "created_at": listing.created_at,
        "updated_at": listing.updated_at,

        # Agent contact info (shown immediately - no lead creation required)
        "agent_name": agent.name,
        "agent_agency_name": agent.company_name,  # agency_name removed from AgentProfile, use User.company_name
        "agent_phone": agent.phone_number,  # phone_number removed from AgentProfile, use User.phone_number
        "agent_whatsapp": agent.agent_profile.whatsapp_number if agent.agent_profile else None,
        "agent_email": agent.email
    }


def transform_private_listing(listing: Listing, agent: User) -> dict:
    """
    Transform listing to private view - shows ALL information.

    Visible to:
    - Listing owner (agent)
    - Admin

    Shows everything including:
    - Real business name
    - Exact address and coordinates
    - Private description

    Args:
        listing: Listing object from database
        agent: Agent user object

    Returns:
        Dict with all fields (public + private)
    """
    # Start with public transformation
    listing_dict = transform_public_listing(listing, agent)

    # Add private fields
    listing_dict.update({
        "real_business_name": listing.real_business_name,
        "real_location_address": listing.real_location_address,
        "real_location_lat": listing.real_location_lat,
        "real_location_lng": listing.real_location_lng,
        "real_description_en": listing.real_description_en
    })

    return listing_dict


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
    # Calculate ROI if revenue provided
    roi = None
    if listing_data.monthly_revenue_eur and listing_data.asking_price_eur:
        annual_revenue = float(listing_data.monthly_revenue_eur) * 12
        roi = (annual_revenue / float(listing_data.asking_price_eur)) * 100
        roi = round(roi, 2)

    # Create listing
    listing = Listing(
        id=uuid.uuid4(),
        agent_id=agent_id,
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
        asking_price_lek=listing_data.asking_price_lek,
        monthly_revenue_eur=listing_data.monthly_revenue_eur,
        monthly_revenue_lek=listing_data.monthly_revenue_lek,
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
    await db.refresh(listing)

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
        .outerjoin(AgentProfile, User.id == AgentProfile.user_id)
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
) -> Tuple[List[dict], int]:
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
    if mode == "public":
        query = query.where(
            and_(
                Listing.status == "active",  # Only active listings
                AgentProfile.verification_status == "approved"  # Only from verified agents
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

    # Price range (LEK)
    if search_params.min_price_lek:
        query = query.where(Listing.asking_price_lek >= search_params.min_price_lek)
    if search_params.max_price_lek:
        query = query.where(Listing.asking_price_lek <= search_params.max_price_lek)

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

    # Apply sorting
    if search_params.sort_by == "newest":
        # Premium > Featured > Standard, then newest first within each tier
        query = query.order_by(
            desc(tier_priority),
            desc(Listing.created_at)
        )

    elif search_params.sort_by == "price_low":
        # Premium > Featured > Standard, then price low to high within each tier
        query = query.order_by(
            desc(tier_priority),
            asc(Listing.asking_price_eur)
        )

    elif search_params.sort_by == "price_high":
        # Premium > Featured > Standard, then price high to low within each tier
        query = query.order_by(
            desc(tier_priority),
            desc(Listing.asking_price_eur)
        )

    elif search_params.sort_by == "roi_high":
        # Premium > Featured > Standard, then ROI high to low within each tier
        query = query.order_by(
            desc(tier_priority),
            desc(Listing.roi.nullslast())  # NULL ROI values last
        )

    elif search_params.sort_by == "roi_low":
        # Premium > Featured > Standard, then ROI low to high within each tier
        query = query.order_by(
            desc(tier_priority),
            asc(Listing.roi.nullsfirst())  # NULL ROI values first
        )

    elif search_params.sort_by == "most_viewed":
        # Premium > Featured > Standard, then most viewed within each tier
        query = query.order_by(
            desc(tier_priority),
            desc(Listing.view_count)
        )

    else:
        # Default: newest with tier priority
        query = query.order_by(
            desc(tier_priority),
            desc(Listing.created_at)
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
    listings_list = []
    for listing, agent in rows:
        if mode == "public":
            listing_dict = transform_public_listing(listing, agent)
        else:
            listing_dict = transform_private_listing(listing, agent)

        listings_list.append(listing_dict)

    logger.info(f"Fetched {len(listings_list)} listings (page {search_params.page}, total: {total})")
    return listings_list, total


# ============================================================================
# GET AGENT'S LISTINGS
# ============================================================================

async def get_agent_listings(
    db: AsyncSession,
    agent_id: str
) -> List[dict]:
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

    # Transform to private view
    listings_list = []
    for listing, agent in rows:
        listing_dict = transform_private_listing(listing, agent)
        listings_list.append(listing_dict)

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

    # Track if ROI needs recalculation
    recalculate_roi = False

    # Update fields
    if update_data.real_business_name is not None:
        listing.real_business_name = update_data.real_business_name

    if update_data.real_location_address is not None:
        listing.real_location_address = update_data.real_location_address

    if update_data.real_location_lat is not None:
        listing.real_location_lat = update_data.real_location_lat

    if update_data.real_location_lng is not None:
        listing.real_location_lng = update_data.real_location_lng

    if update_data.real_description_en is not None:
        listing.real_description_en = update_data.real_description_en

    if update_data.public_title_en is not None:
        listing.public_title_en = update_data.public_title_en

    if update_data.public_description_en is not None:
        listing.public_description_en = update_data.public_description_en

    if update_data.category is not None:
        listing.category = update_data.category

    if update_data.public_location_city_en is not None:
        listing.public_location_city_en = update_data.public_location_city_en

    if update_data.public_location_area is not None:
        listing.public_location_area = update_data.public_location_area

    if update_data.asking_price_eur is not None:
        listing.asking_price_eur = update_data.asking_price_eur
        recalculate_roi = True

    if update_data.asking_price_lek is not None:
        listing.asking_price_lek = update_data.asking_price_lek

    if update_data.monthly_revenue_eur is not None:
        listing.monthly_revenue_eur = update_data.monthly_revenue_eur
        recalculate_roi = True

    if update_data.monthly_revenue_lek is not None:
        listing.monthly_revenue_lek = update_data.monthly_revenue_lek

    if update_data.employee_count is not None:
        listing.employee_count = update_data.employee_count

    if update_data.years_in_operation is not None:
        listing.years_in_operation = update_data.years_in_operation

    if update_data.status is not None:
        listing.status = update_data.status

    # Admin-only field
    if update_data.is_physically_verified is not None:
        listing.is_physically_verified = update_data.is_physically_verified

    # Recalculate ROI if needed
    if recalculate_roi and listing.monthly_revenue_eur and listing.asking_price_eur:
        annual_revenue = float(listing.monthly_revenue_eur) * 12
        roi = (annual_revenue / float(listing.asking_price_eur)) * 100
        listing.roi = round(roi, 2)

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

    listing.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(listing)

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
