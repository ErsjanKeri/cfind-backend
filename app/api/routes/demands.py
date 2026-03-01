"""
Buyer demand routes.

Endpoints:
- POST /demands - Create buyer demand (buyers only)
- GET /demands - Get active demands (verified agents only)
- GET /demands/buyer/{buyer_id} - Get buyer's demands
- GET /demands/agent/{agent_id} - Get agent's claimed demands
- POST /demands/{id}/claim - Claim demand (verified agent, exclusive)
- PUT /demands/{id}/status - Update demand status (buyer or admin)
- DELETE /demands/{id} - Delete demand (only if active, buyer or admin)
"""

import logging
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from app.db.session import get_db
from app.models.user import User
from app.schemas.demand import (
    DemandCreate, DemandCreateResponse,
    DemandStatusUpdate, DemandStatusUpdateResponse,
    DemandClaimResponse,
    DemandDeleteResponse,
    DemandSearchParams, DemandsListResponse,
    BuyerDemandsResponse,
    AgentClaimedDemandsResponse
)
from app.api.deps import (
    get_verified_user,
    get_verified_agent,
    verify_csrf_token,
    RoleChecker,
    ensure_owner_or_admin
)
from app.repositories import demand_repo
from app.services.email_service import send_demand_claimed_email
from app.core.exceptions import DemandAlreadyClaimedException

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/demands", tags=["Buyer Demands"])


# ============================================================================
# CREATE DEMAND
# ============================================================================

@router.post(
    "",
    response_model=DemandCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create buyer demand",
    description="Buyer posts what they're looking for (reverse marketplace)"
)
async def create_demand(
    demand_data: DemandCreate,
    current_user: Annotated[User, Depends(RoleChecker(["buyer"]))],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Create buyer demand.

    **Buyer-only feature.**

    Buyer posts:
    - Budget range (EUR and LEK)
    - Category (restaurant, bar, etc.)
    - Preferred city and area
    - Description of what they're looking for
    - Demand type (investor or seeking_funding)

    After creation:
    - Status = "active"
    - Verified agents can browse and claim
    - Only one agent can claim (exclusive assignment)

    **Returns:** Created demand
    """
    demand = await demand_repo.create_demand(db, str(current_user.id), demand_data)
    demand_dict = await demand_repo.get_demand_by_id(db, str(demand.id))

    return DemandCreateResponse(
        success=True,
        message="Demand created successfully. Verified agents can now view and claim it.",
        demand=demand_dict
    )


# ============================================================================
# GET ACTIVE DEMANDS (FOR AGENTS)
# ============================================================================

@router.get(
    "",
    response_model=DemandsListResponse,
    summary="Get active demands",
    description="Browse active buyer demands (verified agents only)"
)
async def get_active_demands(
    current_user: Annotated[User, Depends(get_verified_agent)],
    db: AsyncSession = Depends(get_db),
    # Filters
    category: Optional[str] = Query(None, description="Business category"),
    city: Optional[str] = Query(None, description="Preferred city"),
    min_budget_eur: Optional[float] = Query(None, ge=0, description="Minimum budget in EUR"),
    max_budget_eur: Optional[float] = Query(None, ge=0, description="Maximum budget in EUR"),
    demand_type: Optional[str] = Query(None, pattern="^(investor|seeking_funding)$", description="Demand type"),
    # Pagination
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page")
):
    """
    Get active buyer demands for agents to browse and claim.

    **Verified agents only.**

    **Shows:**
    - Only demands with status = "active" (not yet claimed)
    - Buyer details (name, email, company)
    - Budget range
    - Description

    **Filters:**
    - Category (restaurant, bar, etc.)
    - City (Tirana, Durrës, etc.)
    - Budget range (EUR)
    - Demand type (investor or seeking_funding)

    **Use case:**
    Agents browse available demands and claim ones matching their expertise.
    """
    # Build search params
    search_params = DemandSearchParams(
        category=category,
        city=city,
        min_budget_eur=Decimal(min_budget_eur) if min_budget_eur else None,
        max_budget_eur=Decimal(max_budget_eur) if max_budget_eur else None,
        demand_type=demand_type,
        page=page,
        limit=limit
    )

    demands, total = await demand_repo.get_active_demands(db, search_params)
    total_pages = (total + limit - 1) // limit

    return DemandsListResponse(
        success=True,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
        demands=demands
    )


# ============================================================================
# CLAIM DEMAND
# ============================================================================

@router.post(
    "/{demand_id}/claim",
    response_model=DemandClaimResponse,
    summary="Claim buyer demand",
    description="Agent claims exclusive rights to contact buyer (first-claimer wins)"
)
async def claim_demand(
    demand_id: str,
    current_user: Annotated[User, Depends(get_verified_agent)],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Agent claims a buyer demand.

    **Verified agents only.**

    **Claiming rules:**
    - Only one agent can claim (exclusive assignment)
    - First-claimer wins (optimistic locking)
    - Second agent attempting to claim gets 409 Conflict

    **After claiming:**
    1. Status changes to "assigned"
    2. assigned_agent_id and assigned_at are set
    3. Email sent to buyer with agent contact details

    **Email contains:**
    - Agent name, email, phone, WhatsApp
    - Demand description
    - Encouragement to connect

    **Historical tracking:**
    Once claimed, demand cannot be deleted (kept for history).
    """
    # Attempt claim (optimistic lock — first agent wins)
    demand = await demand_repo.claim_demand(db, demand_id, str(current_user.id))
    if not demand:
        raise DemandAlreadyClaimedException()

    # Send email to buyer with agent contact info
    agent_profile = current_user.agent_profile
    try:
        await send_demand_claimed_email(
            to_email=demand.buyer.email,
            buyer_name=demand.buyer.name,
            agent_name=current_user.name,
            agent_email=current_user.email,
            agent_phone=current_user.phone_number,
            agent_whatsapp=agent_profile.whatsapp_number if agent_profile else None,
            demand_description=demand.description
        )
    except Exception as e:
        logger.error(f"Failed to send demand claimed email: {e}")

    demand_dict = await demand_repo.get_demand_by_id(db, demand_id)

    return DemandClaimResponse(
        success=True,
        message="Demand claimed successfully! Email sent to buyer with your contact information.",
        demand=demand_dict
    )


# ============================================================================
# GET BUYER'S DEMANDS
# ============================================================================

@router.get(
    "/buyer/{buyer_id}",
    response_model=BuyerDemandsResponse,
    summary="Get buyer's demands",
    description="Get all demands for a specific buyer (all statuses)"
)
async def get_buyer_demands(
    buyer_id: str,
    current_user: Annotated[User, Depends(RoleChecker(["buyer", "admin"]))],
    db: AsyncSession = Depends(get_db)
):
    """
    Get all demands for a buyer.

    **Authorization:**
    - Buyer can view their own demands
    - Admin can view any buyer's demands

    **Returns:**
    - ALL demands (active, assigned, fulfilled, closed)
    - If assigned: Shows agent contact details
    - Sorted by creation date (newest first)

    **Use case:**
    Buyer tracks their posted demands and sees which agents claimed them.
    """
    ensure_owner_or_admin(buyer_id, current_user, "You are not authorized to view these demands")

    demands = await demand_repo.get_buyer_demands(db, buyer_id)

    return BuyerDemandsResponse(
        success=True,
        total=len(demands),
        demands=demands
    )


# ============================================================================
# GET AGENT'S CLAIMED DEMANDS
# ============================================================================

@router.get(
    "/agent/{agent_id}",
    response_model=AgentClaimedDemandsResponse,
    summary="Get agent's claimed demands",
    description="Get all demands claimed by a specific agent"
)
async def get_agent_claimed_demands(
    agent_id: str,
    current_user: Annotated[User, Depends(RoleChecker(["agent", "admin"]))],
    db: AsyncSession = Depends(get_db)
):
    """
    Get all demands claimed by an agent.

    **Authorization:**
    - Agent can view their own claimed demands
    - Admin can view any agent's claimed demands

    **Returns:**
    - All demands where assigned_agent_id = agent_id
    - Buyer contact details
    - Sorted by claim date (newest first)

    **Use case:**
    Agent tracks which buyer demands they've claimed and can follow up.
    """
    ensure_owner_or_admin(agent_id, current_user, "You are not authorized to view these demands")

    demands = await demand_repo.get_agent_claimed_demands(db, agent_id)

    return AgentClaimedDemandsResponse(
        success=True,
        total=len(demands),
        demands=demands
    )


# ============================================================================
# UPDATE DEMAND STATUS
# ============================================================================

@router.put(
    "/{demand_id}/status",
    response_model=DemandStatusUpdateResponse,
    summary="Update demand status",
    description="Update demand status (buyer or admin only)"
)
async def update_demand_status(
    demand_id: str,
    status_data: DemandStatusUpdate,
    current_user: Annotated[User, Depends(get_verified_user)],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Update demand status.

    **Authorization:**
    - Demand owner (buyer) can update
    - Admin can update any demand

    **Valid status transitions:**
    - active → closed (buyer cancels before assignment)
    - assigned → fulfilled (buyer marks deal complete)
    - assigned → closed (buyer cancels after assignment)

    **Note:**
    Use POST /demands/{id}/claim to change status from "active" to "assigned".
    This endpoint is for buyer/admin status updates.
    """
    # Fetch demand and check authorization
    demand_dict = await demand_repo.get_demand_by_id(db, demand_id)
    if not demand_dict:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demand not found")

    ensure_owner_or_admin(demand_dict.buyer_id, current_user, "You are not authorized to update this demand")

    await demand_repo.update_demand_status(db, demand_id, status_data.status)
    updated_dict = await demand_repo.get_demand_by_id(db, demand_id)

    return DemandStatusUpdateResponse(
        success=True,
        message=f"Demand status updated to {status_data.status}",
        demand=updated_dict
    )


# ============================================================================
# DELETE DEMAND
# ============================================================================

@router.delete(
    "/{demand_id}",
    response_model=DemandDeleteResponse,
    summary="Delete demand",
    description="Delete demand (only if active, buyer or admin)"
)
async def delete_demand(
    demand_id: str,
    current_user: Annotated[User, Depends(get_verified_user)],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete buyer demand.

    **Authorization:**
    - Demand owner (buyer) can delete
    - Admin can delete any demand

    **CRITICAL DELETION RULES:**
    - status = "active": Can be deleted ✅
    - status = "assigned": Cannot be deleted ❌ (agent has committed)
    - status = "fulfilled": Cannot be deleted ❌ (historical tracking)
    - status = "closed": Cannot be deleted ❌ (historical tracking)

    **Historical tracking:**
    Once a demand is assigned, fulfilled, or closed, it's kept for history.
    This ensures agents' commitments are tracked and deals are recorded.
    """
    # Fetch demand and check authorization
    demand_dict = await demand_repo.get_demand_by_id(db, demand_id)
    if not demand_dict:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demand not found")

    ensure_owner_or_admin(demand_dict.buyer_id, current_user, "You are not authorized to delete this demand")

    await demand_repo.delete_demand(db, demand_id)

    return DemandDeleteResponse(
        success=True,
        message="Demand deleted successfully"
    )
