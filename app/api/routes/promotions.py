"""
Promotion system routes.

Endpoints:
- GET /promotions/packages - Get credit packages
- GET /promotions/tiers - Get promotion tier configs
- GET /promotions/credits - Get agent's credit balance and history
- POST /promotions/purchase - Purchase credits
- POST /promotions/{listing_id}/promote - Promote listing
- POST /promotions/{listing_id}/cancel - Cancel promotion
- GET /promotions/active - Get agent's active promotions
"""

import uuid
import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.models.user import User
from app.models.listing import Listing
from app.models.promotion import CreditPackage, PromotionTierConfig
from app.schemas.promotion import (
    CreditPackageResponse, CreditPackagesResponse,
    PromotionTierConfigResponse, PromotionTierConfigsResponse,
    CreditTransactionResponse, AgentCreditsResponse,
    CreditPurchaseRequest, CreditPurchaseResponse,
    PromoteListingRequest, PromoteListingResponse,
    PromotionHistoryResponse, CancelPromotionResponse,
    AgentActivePromotionsResponse
)
from app.api.deps import (
    get_verified_agent,
    verify_csrf_token,
    RoleChecker,
    ensure_owner_or_admin
)
from app.repositories import promotion_repo
from app.core.exceptions import InsufficientCreditsException

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/promotions", tags=["Promotions"])


# ============================================================================
# GET CREDIT PACKAGES
# ============================================================================

@router.get(
    "/packages",
    response_model=CreditPackagesResponse,
    summary="Get credit packages",
    description="Get all available credit packages for purchase"
)
async def get_credit_packages(
    db: AsyncSession = Depends(get_db)
):
    """
    Get all active credit packages.

    **Public endpoint** - no authentication required.

    Returns:
    - Package name (Starter, Basic, Standard, Pro, Agency)
    - Credits amount
    - Price (EUR and LEK)
    - Savings badge (e.g., "Save 33%")
    - Popular flag
    - Sort order

    **Example packages:**
    - Starter: 10 credits for €15
    - Standard: 50 credits for €50 (Save 33%) ⭐ Popular
    - Agency: 250 credits for €175 (Save 53%)
    """
    packages = await promotion_repo.get_credit_packages(db)
    packages_list = [CreditPackageResponse.model_validate(pkg) for pkg in packages]

    return CreditPackagesResponse(
        success=True,
        total=len(packages_list),
        packages=packages_list
    )


# ============================================================================
# GET PROMOTION TIER CONFIGS
# ============================================================================

@router.get(
    "/tiers",
    response_model=PromotionTierConfigsResponse,
    summary="Get promotion tier configs",
    description="Get promotion tier configurations (Featured, Premium)"
)
async def get_promotion_tiers(
    db: AsyncSession = Depends(get_db)
):
    """
    Get all active promotion tier configurations.

    **Public endpoint** - no authentication required.

    Returns:
    - Tier name (Featured, Premium)
    - Credit cost (5 for Featured, 15 for Premium)
    - Duration in days (30 days)
    - Description of benefits
    - Badge color

    **Tiers:**
    - Featured: 5 credits / 30 days - Appear above standard listings
    - Premium: 15 credits / 30 days - Top of search results, homepage carousel
    """
    tiers = await promotion_repo.get_promotion_tier_configs(db)
    tiers_list = [PromotionTierConfigResponse.model_validate(tier) for tier in tiers]

    return PromotionTierConfigsResponse(
        success=True,
        total=len(tiers_list),
        tiers=tiers_list
    )


# ============================================================================
# GET AGENT CREDITS
# ============================================================================

@router.get(
    "/credits",
    response_model=AgentCreditsResponse,
    summary="Get agent's credits",
    description="Get credit balance and transaction history for current agent"
)
async def get_agent_credits(
    current_user: Annotated[User, Depends(RoleChecker(["agent"]))],
    db: AsyncSession = Depends(get_db)
):
    """
    Get agent's credit balance and transaction history.

    **Agent-only endpoint.**

    Returns:
    - Current credit balance
    - All credit transactions (purchases, usage, bonuses, adjustments)
    - Sorted by date (newest first)

    **Transaction types:**
    - purchase: Agent bought credits
    - usage: Agent promoted listing (negative amount)
    - refund: Admin refunded credits
    - bonus: Admin gave bonus credits
    - adjustment: Admin manual adjustment
    """
    agent_id = str(current_user.id)
    balance = await promotion_repo.get_agent_credit_balance(db, agent_id)
    transactions = await promotion_repo.get_agent_credit_transactions(db, agent_id)
    transactions_list = [CreditTransactionResponse.model_validate(txn) for txn in transactions]

    return AgentCreditsResponse(
        success=True,
        agent_id=agent_id,
        credit_balance=balance,
        total_transactions=len(transactions_list),
        transactions=transactions_list
    )


# ============================================================================
# PURCHASE CREDITS
# ============================================================================

@router.post(
    "/purchase",
    response_model=CreditPurchaseResponse,
    summary="Purchase credits",
    description="Purchase credit package (simulated payment, Stripe integration later)"
)
async def purchase_credits(
    purchase_data: CreditPurchaseRequest,
    current_user: Annotated[User, Depends(get_verified_agent)],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Purchase credits.

    **Verified agents only.**

    **Payment methods:**
    - manual: Admin manually adds credits (simulated)
    - stripe: Stripe integration (TODO)
    - paypal: PayPal integration (TODO)

    **Current implementation:**
    Payment is simulated. Credits are added immediately.

    **Returns:**
    - Credits added
    - New balance
    - Transaction record
    """
    # Fetch package
    result = await db.execute(
        select(CreditPackage).where(CreditPackage.id == purchase_data.package_id)
    )
    package = result.scalar_one_or_none()

    if not package or not package.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credit package not found or inactive")

    # TODO: Integrate real payment gateway. For now, simulate successful payment.
    payment_reference = f"SIM-{purchase_data.payment_method.upper()}-{uuid.uuid4().hex[:8]}"

    agent_id = str(current_user.id)
    transaction = await promotion_repo.create_credit_transaction(
        db=db,
        agent_id=agent_id,
        amount=package.credits,
        transaction_type="purchase",
        description=f"Purchased {package.name} package ({package.credits} credits)",
        payment_reference=payment_reference
    )
    await db.commit()

    new_balance = await promotion_repo.get_agent_credit_balance(db, agent_id)

    logger.info(f"Agent {agent_id} purchased {package.credits} credits (package: {package.name})")

    return CreditPurchaseResponse(
        success=True,
        message=f"Successfully purchased {package.credits} credits!",
        credits_added=package.credits,
        new_balance=new_balance,
        transaction=CreditTransactionResponse.model_validate(transaction)
    )


# ============================================================================
# PROMOTE LISTING
# ============================================================================

@router.post(
    "/{listing_id}/promote",
    response_model=PromoteListingResponse,
    summary="Promote listing",
    description="Promote listing to Featured or Premium tier (deducts credits)"
)
async def promote_listing(
    listing_id: str,
    promotion_data: PromoteListingRequest,
    current_user: Annotated[User, Depends(get_verified_agent)],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Promote listing to Featured or Premium tier.

    **Verified agents only.**

    **Pricing:**
    - Featured: 5 credits / 30 days
    - Premium: 15 credits / 30 days

    **CRITICAL UPGRADE LOGIC:**
    - Standard → Featured: 5 credits
    - Standard → Premium: 15 credits
    - Featured → Premium: 10 credits (only charge difference!)
    - Premium: Already at max tier (error)

    **Validation:**
    - Must own listing or be admin
    - Must have sufficient credits
    - Listing must exist

    **Returns:**
    - Credits deducted
    - New credit balance
    - Promotion details (start/end dates, tier)
    - New listing tier
    """
    target_tier = promotion_data.tier

    # Fetch listing
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")

    ensure_owner_or_admin(listing.agent_id, current_user, "You are not authorized to promote this listing")

    # Get tier config
    result = await db.execute(select(PromotionTierConfig).where(PromotionTierConfig.tier == target_tier))
    tier_config = result.scalar_one_or_none()
    if not tier_config or not tier_config.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Promotion tier '{target_tier}' not found or inactive")

    # Calculate cost based on current tier (upgrade logic)
    current_tier = listing.promotion_tier
    base_cost = tier_config.credit_cost

    if current_tier == "standard":
        cost = base_cost
    elif current_tier == "featured":
        if target_tier == "featured":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Listing is already featured")
        elif target_tier == "premium":
            # Featured → Premium: Only charge difference
            featured_result = await db.execute(
                select(PromotionTierConfig).where(PromotionTierConfig.tier == "featured")
            )
            featured_config = featured_result.scalar_one_or_none()
            featured_cost = featured_config.credit_cost if featured_config else 0
            cost = base_cost - featured_cost
        else:
            cost = base_cost
    elif current_tier == "premium":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Listing is already at maximum promotion tier (Premium)")
    else:
        cost = base_cost

    # Check credits
    agent_id = str(listing.agent_id)
    current_balance = await promotion_repo.get_agent_credit_balance(db, agent_id)
    if current_balance < cost:
        raise InsufficientCreditsException(required=cost, available=current_balance)

    # Deduct credits and promote listing (atomic)
    transaction = await promotion_repo.create_credit_transaction(
        db=db,
        agent_id=agent_id,
        amount=-cost,
        transaction_type="usage",
        description=f"Promoted listing to {target_tier} tier",
        listing_id=listing_id
    )

    updated_listing, promotion = await promotion_repo.promote_listing(
        db=db,
        listing_id=listing_id,
        tier=target_tier,
        credit_cost=cost,
        duration_days=tier_config.duration_days
    )

    transaction.promotion_id = promotion.id
    await db.commit()

    new_balance = await promotion_repo.get_agent_credit_balance(db, agent_id)

    logger.info(f"Promoted listing {listing_id} to {target_tier}, deducted {cost} credits")

    return PromoteListingResponse(
        success=True,
        message=f"Listing promoted to {target_tier} tier for 30 days! {cost} credits deducted.",
        credits_deducted=cost,
        new_balance=new_balance,
        promotion=PromotionHistoryResponse.model_validate(promotion),
        listing_tier=updated_listing.promotion_tier
    )


# ============================================================================
# CANCEL PROMOTION
# ============================================================================

@router.post(
    "/{listing_id}/cancel",
    response_model=CancelPromotionResponse,
    summary="Cancel promotion",
    description="Cancel active promotion for listing (no refund)"
)
async def cancel_promotion(
    listing_id: str,
    current_user: Annotated[User, Depends(get_verified_agent)],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Cancel active promotion for a listing.

    **Verified agents only.**

    **IMPORTANT:**
    Credits are NOT refunded. Once spent, credits are gone.

    **What happens:**
    - Current promotion marked as "cancelled"
    - Listing tier reset to "standard" (unless another active promotion exists)
    - No credit refund

    **Returns:**
    - New listing tier after cancellation
    """
    # Fetch listing
    result = await db.execute(select(Listing).where(Listing.id == listing_id))
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")

    ensure_owner_or_admin(listing.agent_id, current_user, "You are not authorized to cancel this promotion")

    updated_listing = await promotion_repo.cancel_promotion(db, listing_id)
    logger.info(f"Cancelled promotion for listing {listing_id}, new tier: {updated_listing.promotion_tier}")

    return CancelPromotionResponse(
        success=True,
        message="Promotion cancelled successfully. Credits are non-refundable.",
        listing_tier=updated_listing.promotion_tier
    )


# ============================================================================
# GET ACTIVE PROMOTIONS
# ============================================================================

@router.get(
    "/active",
    response_model=AgentActivePromotionsResponse,
    summary="Get active promotions",
    description="Get current agent's active promotions"
)
async def get_active_promotions(
    current_user: Annotated[User, Depends(RoleChecker(["agent"]))],
    db: AsyncSession = Depends(get_db)
):
    """
    Get agent's active promotions.

    **Agent-only endpoint.**

    Returns:
    - All promotions with status = "active"
    - Promotion tier (featured or premium)
    - Start and end dates
    - Credit cost
    - Performance metrics (views, leads during promotion)

    **Use case:**
    Agent tracks which listings are currently promoted and when they expire.
    """
    promotions = await promotion_repo.get_agent_active_promotions(db, str(current_user.id))
    promotions_list = [PromotionHistoryResponse.model_validate(promo) for promo in promotions]

    return AgentActivePromotionsResponse(
        success=True,
        total=len(promotions_list),
        promotions=promotions_list
    )
