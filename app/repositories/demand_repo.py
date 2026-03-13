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
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, desc, func
from sqlalchemy.orm import selectinload
import uuid

from app.models.demand import BuyerDemand
from app.models.user import User, AgentProfile
from app.schemas.demand import DemandCreate, DemandSearchParams, DemandResponse

logger = logging.getLogger(__name__)


def _transform_demand(demand, buyer=None, assigned_agent=None, assigned_agent_profile=None) -> DemandResponse:
    """Transform a demand ORM object to a typed DemandResponse."""
    b = buyer or demand.buyer
    agent = assigned_agent or getattr(demand, 'assigned_agent', None)
    agent_prof = assigned_agent_profile or (agent.agent_profile if agent else None)

    result = DemandResponse.model_validate(demand)
    updates = {
        "buyer_name": b.name,
        "buyer_email": b.email,
        "buyer_company": b.company_name,
    }
    if agent:
        updates.update(
            assigned_agent_name=agent.name,
            assigned_agent_email=agent.email,
            assigned_agent_phone=agent.phone_number,
            assigned_agent_whatsapp=agent_prof.whatsapp_number if agent_prof else None,
        )
    return result.model_copy(update=updates)


# ============================================================================
# CREATE DEMAND
# ============================================================================

async def create_demand(
    db: AsyncSession,
    buyer_id: str,
    demand_data: DemandCreate,
    buyer: User = None
) -> DemandResponse:
    """
    Create new buyer demand.

    Initial status is "active" (available for agents to claim).

    Args:
        db: Database session
        buyer_id: Buyer UUID
        demand_data: Demand creation schema
        buyer: Buyer User object (avoids needing to reload relationship after flush)

    Returns:
        Created demand as DemandResponse
    """
    demand = BuyerDemand(
        id=uuid.uuid4(),
        buyer_id=buyer_id,
        country_code=demand_data.country_code,
        budget_min_eur=demand_data.budget_min_eur,
        budget_max_eur=demand_data.budget_max_eur,
        category=demand_data.category,
        preferred_city_en=demand_data.preferred_city_en,
        preferred_area=demand_data.preferred_area,
        description=demand_data.description,
        demand_type=demand_data.demand_type,
        status="active"
    )

    db.add(demand)
    demand_id = demand.id
    await db.flush()

    # Re-fetch to get server-generated fields (created_at, updated_at)
    result = await db.execute(
        select(BuyerDemand)
        .where(BuyerDemand.id == demand_id)
        .execution_options(populate_existing=True)
    )
    demand = result.scalar_one()

    logger.info(f"Created buyer demand: {demand.id} by buyer {buyer_id}")
    return _transform_demand(demand, buyer=buyer)


# ============================================================================
# GET ACTIVE DEMANDS (FOR AGENTS)
# ============================================================================

async def get_active_demands(
    db: AsyncSession,
    search_params: DemandSearchParams
) -> Tuple[List[DemandResponse], int]:
    """
    Get demands for agents/admins to browse.

    Filters by status when provided (agents default to "active" at the route layer).

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
    # Base query
    query = (
        select(BuyerDemand, User)
        .join(User, BuyerDemand.buyer_id == User.id)
        .options(
            selectinload(BuyerDemand.buyer),
            selectinload(BuyerDemand.assigned_agent).selectinload(User.agent_profile)
        )
        .where(BuyerDemand.country_code == search_params.country_code)
    )

    # Status filter (if provided); otherwise return all statuses
    if search_params.status:
        query = query.where(BuyerDemand.status == search_params.status)

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

    demands_list = [_transform_demand(demand, buyer=buyer) for demand, buyer in rows]

    logger.info(f"Fetched {len(demands_list)} demands (status={search_params.status or 'all'}, page {search_params.page}, total: {total})")
    return demands_list, total


# ============================================================================
# GET BUYER'S DEMANDS
# ============================================================================

async def get_buyer_demands(
    db: AsyncSession,
    buyer_id: str,
    page: int = 1,
    limit: int = 20
) -> Tuple[List[DemandResponse], int]:
    """
    Get paginated demands for a buyer (all statuses).

    Args:
        db: Database session
        buyer_id: Buyer UUID
        page: Page number (1-based)
        limit: Items per page

    Returns:
        Tuple of (demands_list, total_count)
    """
    base_query = (
        select(BuyerDemand)
        .options(
            selectinload(BuyerDemand.buyer),
            selectinload(BuyerDemand.assigned_agent).selectinload(User.agent_profile)
        )
        .where(BuyerDemand.buyer_id == buyer_id)
        .order_by(desc(BuyerDemand.created_at))
    )

    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * limit
    result = await db.execute(base_query.offset(offset).limit(limit))
    demands = result.scalars().all()

    demands_list = [_transform_demand(demand) for demand in demands]

    logger.info(f"Fetched {len(demands_list)} demands for buyer {buyer_id} (page {page}, total: {total})")
    return demands_list, total


# ============================================================================
# GET AGENT'S CLAIMED DEMANDS
# ============================================================================

async def get_agent_claimed_demands(
    db: AsyncSession,
    agent_id: str,
    page: int = 1,
    limit: int = 20
) -> Tuple[List[DemandResponse], int]:
    """
    Get paginated demands claimed by an agent.

    Args:
        db: Database session
        agent_id: Agent UUID
        page: Page number (1-based)
        limit: Items per page

    Returns:
        Tuple of (demands_list, total_count)
    """
    base_query = (
        select(BuyerDemand)
        .options(
            selectinload(BuyerDemand.buyer),
            selectinload(BuyerDemand.assigned_agent).selectinload(User.agent_profile)
        )
        .where(BuyerDemand.assigned_agent_id == agent_id)
        .order_by(desc(BuyerDemand.assigned_at))
    )

    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * limit
    result = await db.execute(base_query.offset(offset).limit(limit))
    demands = result.scalars().all()

    demands_list = [_transform_demand(demand) for demand in demands]

    logger.info(f"Fetched {len(demands_list)} claimed demands for agent {agent_id} (page {page}, total: {total})")
    return demands_list, total


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
            assigned_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
    )

    # Check if update succeeded
    if result.rowcount == 0:
        # Demand was already claimed or doesn't exist
        logger.warning(f"Failed to claim demand {demand_id} - already claimed or not found")
        return None

    await db.flush()

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
) -> DemandResponse:
    """
    Update demand status.

    Valid transitions:
    - active → assigned (via claim_demand, not this function)
    - assigned → fulfilled (buyer marks complete)
    - assigned → closed (buyer cancels)
    - active → closed (buyer cancels before assignment)
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

    valid_transitions = {
        "active": ["closed"],
        "assigned": ["fulfilled", "closed"],
    }
    allowed = valid_transitions.get(demand.status, [])
    if new_status not in allowed:
        raise ValueError(f"Cannot transition from '{demand.status}' to '{new_status}'")

    demand.status = new_status
    demand.updated_at = datetime.now(timezone.utc)

    # Increment agent's deals_completed when demand is fulfilled
    if new_status == "fulfilled" and demand.assigned_agent_id:
        await db.execute(
            update(AgentProfile)
            .where(AgentProfile.user_id == demand.assigned_agent_id)
            .values(deals_completed=AgentProfile.deals_completed + 1)
        )

    await db.flush()

    logger.info(f"Updated demand {demand_id} status to {new_status}")
    return _transform_demand(demand)


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
        return False

    # Check deletion rules
    if demand.status in ["assigned", "fulfilled", "closed"]:
        raise ValueError(
            f"Cannot delete {demand.status} demand. Only active demands can be deleted. "
            f"Assigned, fulfilled, and closed demands are kept for historical tracking."
        )

    # Delete demand (status = "active")
    await db.execute(
        delete(BuyerDemand).where(BuyerDemand.id == demand_id)
    )

    await db.flush()

    logger.info(f"Deleted demand: {demand_id}")
    return True


# ============================================================================
# GET DEMAND BY ID
# ============================================================================

async def get_demand_by_id(
    db: AsyncSession,
    demand_id: str
) -> Optional[DemandResponse]:
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

    return _transform_demand(demand)
