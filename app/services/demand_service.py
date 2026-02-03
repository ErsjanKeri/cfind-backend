"""
Buyer demand service - business logic for buyer demands.

Handles:
- Demand creation and validation
- Agent claiming with email notifications
- Status updates with authorization
- Deletion with historical tracking rules
"""

import logging
from typing import List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.user import User
from app.schemas.demand import DemandCreate, DemandUpdate, DemandSearchParams
from app.repositories import demand_repo
from app.services.email_service import send_demand_claimed_email
from app.core.exceptions import DemandAlreadyClaimedException

logger = logging.getLogger(__name__)


# ============================================================================
# CREATE DEMAND
# ============================================================================

async def create_demand_service(
    db: AsyncSession,
    buyer_id: str,
    demand_data: DemandCreate
) -> dict:
    """
    Create new buyer demand with validation.

    Validates:
    - Budget max >= budget min (both EUR and LEK)
    - Valid category and city

    Args:
        db: Database session
        buyer_id: Buyer UUID
        demand_data: Demand creation schema

    Returns:
        Created demand dict

    Example:
        >>> demand = await create_demand_service(db, buyer_id, demand_data)
        >>> print(demand['status'])  # "active"
    """
    # Create demand
    demand = await demand_repo.create_demand(db, buyer_id, demand_data)

    # Get demand details
    demand_dict = await demand_repo.get_demand_by_id(db, str(demand.id))

    return demand_dict


# ============================================================================
# CLAIM DEMAND
# ============================================================================

async def claim_demand_service(
    db: AsyncSession,
    demand_id: str,
    agent: User
) -> dict:
    """
    Agent claims a buyer demand.

    CRITICAL: Uses optimistic locking - only first agent succeeds.
    Second agent attempting to claim will get 409 Conflict.

    After claiming:
    1. Status changes to "assigned"
    2. assigned_agent_id and assigned_at set
    3. Email sent to buyer with agent contact details

    Args:
        db: Database session
        demand_id: Demand UUID
        agent: Agent user object (with agent_profile loaded)

    Returns:
        Claimed demand dict

    Raises:
        DemandAlreadyClaimedException: If demand already claimed
        HTTPException: If demand not found

    Example:
        >>> demand = await claim_demand_service(db, demand_id, agent)
        >>> # Email sent to buyer automatically
    """
    # Attempt to claim (optimistic lock)
    demand = await demand_repo.claim_demand(db, demand_id, str(agent.id))

    if not demand:
        # Demand was already claimed by another agent
        raise DemandAlreadyClaimedException()

    # Send email notification to buyer
    agent_profile = agent.agent_profile
    await send_demand_claimed_email(
        to_email=demand.buyer.email,
        buyer_name=demand.buyer.name,
        agent_name=agent.name,
        agent_email=agent.email,
        agent_phone=agent_profile.phone_number if agent_profile else None,
        agent_whatsapp=agent_profile.whatsapp_number if agent_profile else None,
        demand_description=demand.description
    )

    logger.info(f"Demand {demand_id} claimed by agent {agent.id}, email sent to buyer")

    # Get updated demand details
    demand_dict = await demand_repo.get_demand_by_id(db, demand_id)

    return demand_dict


# ============================================================================
# UPDATE DEMAND STATUS
# ============================================================================

async def update_demand_status_service(
    db: AsyncSession,
    demand_id: str,
    new_status: str,
    current_user: User
) -> dict:
    """
    Update demand status with authorization check.

    Authorization:
    - Buyer who owns the demand can update
    - Admin can update any demand

    Valid status values:
    - "active" (only if currently active)
    - "assigned" (via claim, not this function)
    - "fulfilled" (buyer marks deal complete)
    - "closed" (buyer cancels)

    Args:
        db: Database session
        demand_id: Demand UUID
        new_status: New status value
        current_user: Current user

    Returns:
        Updated demand dict

    Raises:
        HTTPException: If not authorized or demand not found
    """
    # Fetch demand
    demand_dict = await demand_repo.get_demand_by_id(db, demand_id)

    if not demand_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demand not found"
        )

    # Check authorization
    is_owner = demand_dict["buyer_id"] == str(current_user.id)
    is_admin = current_user.role == "admin"

    if not is_owner and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to update this demand"
        )

    # Update status
    updated_demand = await demand_repo.update_demand_status(db, demand_id, new_status)

    # Get updated details
    demand_dict = await demand_repo.get_demand_by_id(db, demand_id)

    return demand_dict


# ============================================================================
# DELETE DEMAND
# ============================================================================

async def delete_demand_service(
    db: AsyncSession,
    demand_id: str,
    current_user: User
) -> bool:
    """
    Delete demand with authorization and historical tracking rules.

    Authorization:
    - Buyer who owns the demand can delete
    - Admin can delete any demand

    CRITICAL DELETION RULES:
    - status = "active": Can be deleted ✅
    - status = "assigned": Cannot be deleted ❌ (agent has committed)
    - status = "fulfilled": Cannot be deleted ❌ (historical tracking)
    - status = "closed": Cannot be deleted ❌ (historical tracking)

    Args:
        db: Database session
        demand_id: Demand UUID
        current_user: Current user

    Returns:
        True if deleted successfully

    Raises:
        HTTPException: If not authorized or cannot delete
    """
    # Fetch demand
    demand_dict = await demand_repo.get_demand_by_id(db, demand_id)

    if not demand_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demand not found"
        )

    # Check authorization
    is_owner = demand_dict["buyer_id"] == str(current_user.id)
    is_admin = current_user.role == "admin"

    if not is_owner and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to delete this demand"
        )

    # Delete demand (will enforce status rules in repository)
    return await demand_repo.delete_demand(db, demand_id)


# ============================================================================
# GET ACTIVE DEMANDS
# ============================================================================

async def get_active_demands_service(
    db: AsyncSession,
    search_params: DemandSearchParams
) -> Tuple[List[dict], int, int]:
    """
    Get active demands for agents to browse.

    Only verified agents can access this.

    Args:
        db: Database session
        search_params: Search and filter parameters

    Returns:
        Tuple of (demands_list, total_count, total_pages)

    Example:
        >>> params = DemandSearchParams(category="restaurant")
        >>> demands, total, pages = await get_active_demands_service(db, params)
    """
    demands_list, total = await demand_repo.get_active_demands(db, search_params)

    # Calculate total pages
    total_pages = (total + search_params.limit - 1) // search_params.limit

    return demands_list, total, total_pages


# ============================================================================
# GET BUYER'S DEMANDS
# ============================================================================

async def get_buyer_demands_service(
    db: AsyncSession,
    buyer_id: str,
    current_user: User
) -> List[dict]:
    """
    Get buyer's demands with authorization check.

    Authorization:
    - Buyer can view their own demands
    - Admin can view any buyer's demands

    Args:
        db: Database session
        buyer_id: Buyer UUID
        current_user: Current user

    Returns:
        List of demand dicts

    Raises:
        HTTPException: If not authorized
    """
    # Check authorization
    is_owner = str(current_user.id) == buyer_id
    is_admin = current_user.role == "admin"

    if not is_owner and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view these demands"
        )

    return await demand_repo.get_buyer_demands(db, buyer_id)


# ============================================================================
# GET AGENT'S CLAIMED DEMANDS
# ============================================================================

async def get_agent_claimed_demands_service(
    db: AsyncSession,
    agent_id: str,
    current_user: User
) -> List[dict]:
    """
    Get agent's claimed demands with authorization check.

    Authorization:
    - Agent can view their own claimed demands
    - Admin can view any agent's claimed demands

    Args:
        db: Database session
        agent_id: Agent UUID
        current_user: Current user

    Returns:
        List of claimed demand dicts

    Raises:
        HTTPException: If not authorized
    """
    # Check authorization
    is_owner = str(current_user.id) == agent_id
    is_admin = current_user.role == "admin"

    if not is_owner and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view these demands"
        )

    return await demand_repo.get_agent_claimed_demands(db, agent_id)
