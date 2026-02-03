"""
Listing service - business logic for listing operations.

Handles:
- Listing creation with verification checks
- Listing updates with ownership validation
- Listing deletion with ownership validation
- Visibility mode determination
- ROI auto-calculation
"""

import logging
from typing import Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.user import User
from app.schemas.listing import ListingCreate, ListingUpdate, ListingSearchParams
from app.repositories import listing_repo
from app.repositories.user_repo import get_user_by_id

logger = logging.getLogger(__name__)


# ============================================================================
# CREATE LISTING
# ============================================================================

async def create_listing_service(
    db: AsyncSession,
    user: User,
    listing_data: ListingCreate
) -> dict:
    """
    Create new listing with business logic checks.

    Checks:
    1. User is agent or admin
    2. If agent: must be verified with all documents
    3. At least 1 image required
    4. Auto-calculates ROI

    Args:
        db: Database session
        user: Current user (authenticated)
        listing_data: Listing creation schema

    Returns:
        Private listing dict (creator sees full details)

    Raises:
        HTTPException: If validation fails
    """
    # Determine agent_id
    # If admin creating listing for another agent
    if user.role == "admin" and listing_data.agent_id:
        agent_id = listing_data.agent_id

        # Verify target agent exists and is verified
        target_agent = await get_user_by_id(db, agent_id, include_profiles=True)
        if not target_agent or target_agent.role != "agent":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid agent ID"
            )

        # Note: Admin can create listings even for unverified agents
        # This is an admin privilege

    else:
        # Regular agent creating their own listing
        if user.role != "agent":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only agents can create listings"
            )

        # Agent verification check already done by get_verified_agent dependency
        # But we re-check here for safety
        if not user.agent_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent profile not found"
            )

        if user.agent_profile.verification_status != "approved":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account must be verified before creating listings"
            )

        # Check all documents uploaded
        if not all([
            user.agent_profile.license_document_url,
            user.agent_profile.company_document_url,
            user.agent_profile.id_document_url
        ]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Please upload all required documents before creating listings"
            )

        agent_id = str(user.id)

    # Validate images
    if not listing_data.images or len(listing_data.images) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one image is required"
        )

    # Create listing
    listing = await listing_repo.create_listing(db, agent_id, listing_data)

    # Fetch agent for transformation
    agent = await get_user_by_id(db, agent_id, include_profiles=True)

    # Return private view (creator sees full details)
    return listing_repo.transform_private_listing(listing, agent)


# ============================================================================
# UPDATE LISTING
# ============================================================================

async def update_listing_service(
    db: AsyncSession,
    user: User,
    listing_id: str,
    update_data: ListingUpdate
) -> dict:
    """
    Update listing with ownership check.

    Ownership rules:
    - Listing owner (agent) can update their own listings
    - Admin can update any listing

    Args:
        db: Database session
        user: Current user
        listing_id: Listing UUID
        update_data: Update schema

    Returns:
        Updated listing dict (private view)

    Raises:
        HTTPException: If not authorized or listing not found
    """
    # Fetch listing
    result = await listing_repo.get_listing_by_id(db, listing_id, mode="private")
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found"
        )

    listing, agent = result

    # Check ownership (owner or admin)
    if str(listing.agent_id) != str(user.id) and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to update this listing"
        )

    # Admin-only field validation
    if update_data.is_physically_verified is not None and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can set physical verification status"
        )

    # Update listing
    updated_listing = await listing_repo.update_listing(db, listing_id, update_data)

    # Return private view
    agent_refreshed = await get_user_by_id(db, str(updated_listing.agent_id), include_profiles=True)
    return listing_repo.transform_private_listing(updated_listing, agent_refreshed)


# ============================================================================
# DELETE LISTING
# ============================================================================

async def delete_listing_service(
    db: AsyncSession,
    user: User,
    listing_id: str
) -> bool:
    """
    Delete listing with ownership check.

    Ownership rules:
    - Listing owner (agent) can delete their own listings
    - Admin can delete any listing

    Args:
        db: Database session
        user: Current user
        listing_id: Listing UUID

    Returns:
        True if deleted successfully

    Raises:
        HTTPException: If not authorized or listing not found
    """
    # Fetch listing
    result = await listing_repo.get_listing_by_id(db, listing_id, mode="private")
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found"
        )

    listing, agent = result

    # Check ownership (owner or admin)
    if str(listing.agent_id) != str(user.id) and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to delete this listing"
        )

    # Delete listing
    return await listing_repo.delete_listing(db, listing_id)


# ============================================================================
# GET LISTING DETAIL
# ============================================================================

async def get_listing_detail(
    db: AsyncSession,
    listing_id: str,
    current_user: Optional[User] = None
) -> dict:
    """
    Get listing detail with appropriate visibility mode.

    Visibility logic:
    - If user is owner or admin: Show private view (full details)
    - Otherwise: Show public view (hide real business name, exact address)

    Args:
        db: Database session
        listing_id: Listing UUID
        current_user: Current user (None if anonymous)

    Returns:
        Listing dict (public or private view based on permissions)

    Raises:
        HTTPException: If listing not found
    """
    # Fetch listing
    result = await listing_repo.get_listing_by_id(db, listing_id, mode="public")
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found"
        )

    listing, agent = result

    # Determine visibility mode
    if current_user:
        # Check if user is owner or admin
        is_owner = str(listing.agent_id) == str(current_user.id)
        is_admin = current_user.role == "admin"

        if is_owner or is_admin:
            return listing_repo.transform_private_listing(listing, agent)

    # Default: public view
    return listing_repo.transform_public_listing(listing, agent)


# ============================================================================
# SEARCH LISTINGS
# ============================================================================

async def search_listings(
    db: AsyncSession,
    search_params: ListingSearchParams
) -> Tuple[List[dict], int, int]:
    """
    Search and filter listings with pagination.

    Returns public view (hides sensitive information).
    Only shows listings from approved agents.

    Args:
        db: Database session
        search_params: Search and filter parameters

    Returns:
        Tuple of (listings_list, total_count, total_pages)

    Example:
        >>> params = ListingSearchParams(category="restaurant", sort_by="price_low")
        >>> listings, total, pages = await search_listings(db, params)
    """
    listings_list, total = await listing_repo.get_listings(
        db,
        search_params,
        mode="public"
    )

    # Calculate total pages
    total_pages = (total + search_params.limit - 1) // search_params.limit  # Ceiling division

    return listings_list, total, total_pages


# ============================================================================
# GET AGENT LISTINGS
# ============================================================================

async def get_agent_listings_service(
    db: AsyncSession,
    agent_id: str,
    current_user: User
) -> List[dict]:
    """
    Get agent's listings with authorization check.

    Authorization:
    - Agent can view their own listings (private view)
    - Admin can view any agent's listings (private view)
    - Others: Not authorized

    Args:
        db: Database session
        agent_id: Agent UUID
        current_user: Current user

    Returns:
        List of listings (private view)

    Raises:
        HTTPException: If not authorized
    """
    # Check authorization
    is_owner = str(current_user.id) == agent_id
    is_admin = current_user.role == "admin"

    if not is_owner and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view these listings"
        )

    # Fetch listings (private view)
    return await listing_repo.get_agent_listings(db, agent_id)
