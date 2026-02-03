"""
Buyer demand repository - database operations for buyer demands.

Handles:
- Demand CRUD operations
- Active demands browsing (for agents)
- Demand claiming with optimistic locking (exclusive, first-claimer wins)
- Status updates
- Deletion with historical tracking rules
"""

import logging
from typing import Optional, List, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_, desc
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
import uuid

from app.models.demand import BuyerDemand
from app.models.user import User, AgentProfile  # BuyerProfile removed
from app.schemas.demand import DemandCreate, DemandUpdate, DemandSearchParams

logger = logging.getLogger(__name__)


# ============================================================================
# CREATE DEMAND
# ============================================================================

async def create_demand(
    db: AsyncSession,
    buyer_id: str,
    demand_data: DemandCreate
) -> BuyerDemand:
    """
    Create new buyer demand.

    Initial status is "active" (available for agents to claim).

    Args:
        db: Database session
        buyer_id: Buyer UUID
        demand_data: Demand creation schema

    Returns:
        Created demand object

    Example:
        >>> demand = await create_demand(db, buyer_id="123...", demand_data=data)
        >>> print(demand.status)  # "active"
    """
    demand = BuyerDemand(
        id=uuid.uuid4(),
        buyer_id=buyer_id,
        budget_min_eur=demand_data.budget_min_eur,
        budget_max_eur=demand_data.budget_max_eur,
        budget_min_lek=demand_data.budget_min_lek,
        budget_max_lek=demand_data.budget_max_lek,
        category=demand_data.category,
        preferred_city_en=demand_data.preferred_city_en,
        preferred_area=demand_data.preferred_area,
        description=demand_data.description,
        demand_type=demand_data.demand_type,
        status="active"
    )

    db.add(demand)
    await db.commit()
    await db.refresh(demand)

    logger.info(f"Created buyer demand: {demand.id} by buyer {buyer_id}")
    return demand


# ============================================================================
# GET ACTIVE DEMANDS (FOR AGENTS)
# ============================================================================

async def get_active_demands(
    db: AsyncSession,
    search_params: DemandSearchParams
) -> Tuple[List[dict], int]:
    """
    Get active demands for agents to browse.

    Only shows demands with status = "active" (not yet claimed).

    Supports filtering by:
    - Category
    - City
    - Budget range
    - Demand type

    Args:
        db: Database session
        search_params: Search and filter parameters

    Returns:
        Tuple of (demands_list, total_count)

    Example:
        >>> params = DemandSearchParams(category="restaurant", city="Tirana")
        >>> demands, total = await get_active_demands(db, params)
    """
    # Base query - only active demands
    query = (
        select(BuyerDemand, User)
        .join(User, BuyerDemand.buyer_id == User.id)
        # BuyerProfile removed - buyer fields now in User table
        .options(
            selectinload(BuyerDemand.buyer)  # Just load buyer, no profile
        )
        .where(BuyerDemand.status == "active")
    )

    # ========================================================================
    # FILTERS
    # ========================================================================

    # Category filter
    if search_params.category:
        query = query.where(BuyerDemand.category == search_params.category)

    # City filter
    if search_params.city:
        query = query.where(BuyerDemand.preferred_city_en == search_params.city)

    # Budget range (EUR)
    if search_params.min_budget_eur:
        query = query.where(BuyerDemand.budget_max_eur >= search_params.min_budget_eur)
    if search_params.max_budget_eur:
        query = query.where(BuyerDemand.budget_min_eur <= search_params.max_budget_eur)

    # Demand type filter
    if search_params.demand_type:
        query = query.where(BuyerDemand.demand_type == search_params.demand_type)

    # ========================================================================
    # SORTING
    # ========================================================================
    # Sort by newest first
    query = query.order_by(desc(BuyerDemand.created_at))

    # ========================================================================
    # COUNT TOTAL (before pagination)
    # ========================================================================
    from sqlalchemy import func
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

    # Transform to dict
    demands_list = []
    for demand, buyer in rows:
        # buyer_profile removed - access buyer.company_name directly

        demands_list.append({
            "id": str(demand.id),
            "buyer_id": str(demand.buyer_id),
            "buyer_name": buyer.name,
            "buyer_email": buyer.email,
            "buyer_company": buyer.company_name,  # Now in User table
            "budget_min_eur": float(demand.budget_min_eur),
            "budget_max_eur": float(demand.budget_max_eur),
            "budget_min_lek": float(demand.budget_min_lek),
            "budget_max_lek": float(demand.budget_max_lek),
            "category": demand.category,
            "preferred_city_en": demand.preferred_city_en,
            "preferred_area": demand.preferred_area,
            "description": demand.description,
            "status": demand.status,
            "demand_type": demand.demand_type,
            "assigned_agent_id": None,
            "assigned_agent_name": None,
            "assigned_agent_email": None,
            "assigned_agent_phone": None,
            "assigned_agent_whatsapp": None,
            "assigned_at": None,
            "created_at": demand.created_at,
            "updated_at": demand.updated_at
        })

    logger.info(f"Fetched {len(demands_list)} active demands (page {search_params.page}, total: {total})")
    return demands_list, total


# ============================================================================
# GET BUYER'S DEMANDS
# ============================================================================

async def get_buyer_demands(
    db: AsyncSession,
    buyer_id: str
) -> List[dict]:
    """
    Get all demands for a buyer (all statuses).

    Returns demands with assigned agent details if assigned.

    Args:
        db: Database session
        buyer_id: Buyer UUID

    Returns:
        List of demand dicts

    Example:
        >>> demands = await get_buyer_demands(db, buyer_id="123...")
        >>> for demand in demands:
        ...     print(f"Status: {demand['status']}")
    """
    result = await db.execute(
        select(BuyerDemand)
        .options(
            selectinload(BuyerDemand.buyer),
            selectinload(BuyerDemand.assigned_agent).selectinload(User.agent_profile)
        )
        .where(BuyerDemand.buyer_id == buyer_id)
        .order_by(desc(BuyerDemand.created_at))
    )

    demands = result.scalars().all()

    # Transform to dict
    demands_list = []
    for demand in demands:
        assigned_agent = demand.assigned_agent
        assigned_agent_profile = assigned_agent.agent_profile if assigned_agent else None

        demands_list.append({
            "id": str(demand.id),
            "buyer_id": str(demand.buyer_id),
            "buyer_name": demand.buyer.name,
            "buyer_email": demand.buyer.email,
            "buyer_company": demand.buyer.company_name,  # Now in User table
            "budget_min_eur": float(demand.budget_min_eur),
            "budget_max_eur": float(demand.budget_max_eur),
            "budget_min_lek": float(demand.budget_min_lek),
            "budget_max_lek": float(demand.budget_max_lek),
            "category": demand.category,
            "preferred_city_en": demand.preferred_city_en,
            "preferred_area": demand.preferred_area,
            "description": demand.description,
            "status": demand.status,
            "demand_type": demand.demand_type,
            "assigned_agent_id": str(assigned_agent.id) if assigned_agent else None,
            "assigned_agent_name": assigned_agent.name if assigned_agent else None,
            "assigned_agent_email": assigned_agent.email if assigned_agent else None,
            "assigned_agent_phone": assigned_agent.phone_number if assigned_agent else None,  # phone_number now on User
            "assigned_agent_whatsapp": assigned_agent_profile.whatsapp_number if assigned_agent_profile else None,
            "assigned_at": demand.assigned_at,
            "created_at": demand.created_at,
            "updated_at": demand.updated_at
        })

    logger.info(f"Fetched {len(demands_list)} demands for buyer {buyer_id}")
    return demands_list


# ============================================================================
# GET AGENT'S CLAIMED DEMANDS
# ============================================================================

async def get_agent_claimed_demands(
    db: AsyncSession,
    agent_id: str
) -> List[dict]:
    """
    Get all demands claimed by an agent.

    Returns demands with buyer details.

    Args:
        db: Database session
        agent_id: Agent UUID

    Returns:
        List of claimed demand dicts

    Example:
        >>> demands = await get_agent_claimed_demands(db, agent_id="123...")
        >>> print(f"Agent has claimed {len(demands)} demands")
    """
    result = await db.execute(
        select(BuyerDemand)
        .options(
            selectinload(BuyerDemand.buyer),
            selectinload(BuyerDemand.assigned_agent).selectinload(User.agent_profile)
        )
        .where(BuyerDemand.assigned_agent_id == agent_id)
        .order_by(desc(BuyerDemand.assigned_at))
    )

    demands = result.scalars().all()

    # Transform to dict (same as get_buyer_demands)
    demands_list = []
    for demand in demands:
        assigned_agent_profile = demand.assigned_agent.agent_profile

        demands_list.append({
            "id": str(demand.id),
            "buyer_id": str(demand.buyer_id),
            "buyer_name": demand.buyer.name,
            "buyer_email": demand.buyer.email,
            "buyer_company": demand.buyer.company_name,  # Now in User table
            "budget_min_eur": float(demand.budget_min_eur),
            "budget_max_eur": float(demand.budget_max_eur),
            "budget_min_lek": float(demand.budget_min_lek),
            "budget_max_lek": float(demand.budget_max_lek),
            "category": demand.category,
            "preferred_city_en": demand.preferred_city_en,
            "preferred_area": demand.preferred_area,
            "description": demand.description,
            "status": demand.status,
            "demand_type": demand.demand_type,
            "assigned_agent_id": str(demand.assigned_agent.id),
            "assigned_agent_name": demand.assigned_agent.name,
            "assigned_agent_email": demand.assigned_agent.email,
            "assigned_agent_phone": demand.assigned_agent.phone_number,  # phone_number now on User
            "assigned_agent_whatsapp": assigned_agent_profile.whatsapp_number if assigned_agent_profile else None,
            "assigned_at": demand.assigned_at,
            "created_at": demand.created_at,
            "updated_at": demand.updated_at
        })

    logger.info(f"Fetched {len(demands_list)} claimed demands for agent {agent_id}")
    return demands_list


# ============================================================================
# CLAIM DEMAND (WITH OPTIMISTIC LOCKING)
# ============================================================================

async def claim_demand(
    db: AsyncSession,
    demand_id: str,
    agent_id: str
) -> Optional[BuyerDemand]:
    """
    Claim demand with optimistic locking (first-claimer wins).

    CRITICAL: Uses database-level locking to prevent race conditions.
    Two agents claiming simultaneously → only first succeeds.

    Args:
        db: Database session
        demand_id: Demand UUID
        agent_id: Agent UUID

    Returns:
        Claimed demand object if successful, None if already claimed

    Example:
        >>> demand = await claim_demand(db, demand_id, agent_id)
        >>> if demand:
        ...     print("Claimed successfully!")
        ... else:
        ...     print("Already claimed by another agent")
    """
    # Update demand with optimistic lock
    # WHERE status = 'active' ensures only active demands can be claimed
    result = await db.execute(
        update(BuyerDemand)
        .where(
            and_(
                BuyerDemand.id == demand_id,
                BuyerDemand.status == "active"  # Optimistic lock condition
            )
        )
        .values(
            status="assigned",
            assigned_agent_id=agent_id,
            assigned_at=datetime.now(datetime.now().astimezone().tzinfo),
            updated_at=datetime.now(datetime.now().astimezone().tzinfo)
        )
    )

    # Check if update succeeded
    if result.rowcount == 0:
        # Demand was already claimed or doesn't exist
        logger.warning(f"Failed to claim demand {demand_id} - already claimed or not found")
        return None

    await db.commit()

    # Fetch updated demand with buyer info
    result = await db.execute(
        select(BuyerDemand)
        .options(
            selectinload(BuyerDemand.buyer),
            selectinload(BuyerDemand.assigned_agent).selectinload(User.agent_profile)
        )
        .where(BuyerDemand.id == demand_id)
    )

    demand = result.scalar_one()

    logger.info(f"Agent {agent_id} successfully claimed demand {demand_id}")
    return demand


# ============================================================================
# UPDATE DEMAND STATUS
# ============================================================================

async def update_demand_status(
    db: AsyncSession,
    demand_id: str,
    new_status: str
) -> BuyerDemand:
    """
    Update demand status.

    Valid transitions:
    - active → assigned (via claim_demand, not this function)
    - assigned → fulfilled (buyer marks complete)
    - assigned → closed (buyer cancels)
    - active → closed (buyer cancels before assignment)

    Args:
        db: Database session
        demand_id: Demand UUID
        new_status: New status value

    Returns:
        Updated demand object

    Raises:
        HTTPException: If demand not found
    """
    # Fetch demand
    result = await db.execute(
        select(BuyerDemand)
        .options(
            selectinload(BuyerDemand.buyer),
            selectinload(BuyerDemand.assigned_agent).selectinload(User.agent_profile)
        )
        .where(BuyerDemand.id == demand_id)
    )
    demand = result.scalar_one_or_none()

    if not demand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demand not found"
        )

    # Update status
    demand.status = new_status
    demand.updated_at = datetime.now(datetime.now().astimezone().tzinfo)

    await db.commit()
    await db.refresh(demand)

    logger.info(f"Updated demand {demand_id} status to {new_status}")
    return demand


# ============================================================================
# DELETE DEMAND (WITH HISTORICAL TRACKING)
# ============================================================================

async def delete_demand(
    db: AsyncSession,
    demand_id: str
) -> bool:
    """
    Delete demand with historical tracking rules.

    CRITICAL DELETION RULES:
    - status = "active": Can be deleted ✅
    - status = "assigned": Cannot be deleted ❌ (agent has committed)
    - status = "fulfilled": Cannot be deleted ❌ (historical tracking)
    - status = "closed": Cannot be deleted ❌ (historical tracking)

    Args:
        db: Database session
        demand_id: Demand UUID

    Returns:
        True if deleted successfully

    Raises:
        HTTPException: If demand not found
        HTTPException: If demand cannot be deleted (assigned/fulfilled/closed)

    Example:
        >>> try:
        ...     await delete_demand(db, demand_id)
        ... except HTTPException as e:
        ...     print(e.detail)  # "Cannot delete assigned demand..."
    """
    # Fetch demand
    result = await db.execute(
        select(BuyerDemand).where(BuyerDemand.id == demand_id)
    )
    demand = result.scalar_one_or_none()

    if not demand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demand not found"
        )

    # Check deletion rules
    if demand.status in ["assigned", "fulfilled", "closed"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete {demand.status} demand. Only active demands can be deleted. "
                   f"Assigned, fulfilled, and closed demands are kept for historical tracking."
        )

    # Delete demand (status = "active")
    await db.execute(
        delete(BuyerDemand).where(BuyerDemand.id == demand_id)
    )

    await db.commit()

    logger.info(f"Deleted demand: {demand_id}")
    return True


# ============================================================================
# GET DEMAND BY ID
# ============================================================================

async def get_demand_by_id(
    db: AsyncSession,
    demand_id: str
) -> Optional[dict]:
    """
    Get single demand by ID with buyer and agent details.

    Args:
        db: Database session
        demand_id: Demand UUID

    Returns:
        Demand dict or None if not found

    Example:
        >>> demand = await get_demand_by_id(db, demand_id="123...")
        >>> if demand:
        ...     print(demand['description'])
    """
    result = await db.execute(
        select(BuyerDemand)
        .options(
            selectinload(BuyerDemand.buyer),
            selectinload(BuyerDemand.assigned_agent).selectinload(User.agent_profile)
        )
        .where(BuyerDemand.id == demand_id)
    )

    demand = result.scalar_one_or_none()

    if not demand:
        return None

    # Transform to dict
    assigned_agent = demand.assigned_agent
    assigned_agent_profile = assigned_agent.agent_profile if assigned_agent else None

    return {
        "id": str(demand.id),
        "buyer_id": str(demand.buyer_id),
        "buyer_name": demand.buyer.name,
        "buyer_email": demand.buyer.email,
        "buyer_company": demand.buyer.company_name,  # Now in User table
        "budget_min_eur": float(demand.budget_min_eur),
        "budget_max_eur": float(demand.budget_max_eur),
        "budget_min_lek": float(demand.budget_min_lek),
        "budget_max_lek": float(demand.budget_max_lek),
        "category": demand.category,
        "preferred_city_en": demand.preferred_city_en,
        "preferred_area": demand.preferred_area,
        "description": demand.description,
        "status": demand.status,
        "demand_type": demand.demand_type,
        "assigned_agent_id": str(assigned_agent.id) if assigned_agent else None,
        "assigned_agent_name": assigned_agent.name if assigned_agent else None,
        "assigned_agent_email": assigned_agent.email if assigned_agent else None,
        "assigned_agent_phone": assigned_agent.phone_number if assigned_agent else None,  # phone_number now on User
        "assigned_agent_whatsapp": assigned_agent_profile.whatsapp_number if assigned_agent_profile else None,
        "assigned_at": demand.assigned_at,
        "created_at": demand.created_at,
        "updated_at": demand.updated_at
    }
