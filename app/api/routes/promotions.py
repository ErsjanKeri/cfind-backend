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

from typing import Annotated
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.promotion import (
    CreditPackagesResponse,
    PromotionTierConfigsResponse,
    AgentCreditsResponse,
    CreditPurchaseRequest, CreditPurchaseResponse,
    PromoteListingRequest, PromoteListingResponse,
    CancelPromotionResponse,
    AgentActivePromotionsResponse
)
from app.api.deps import (
    get_verified_agent,
    verify_csrf_token,
    RoleChecker
)
from app.services import promotion_service

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
    packages = await promotion_service.get_credit_packages_service(db)

    return CreditPackagesResponse(
        success=True,
        total=len(packages),
        packages=packages
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
    tiers = await promotion_service.get_promotion_tier_configs_service(db)

    return PromotionTierConfigsResponse(
        success=True,
        total=len(tiers),
        tiers=tiers
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
    balance, transactions = await promotion_service.get_agent_credits_service(
        db,
        str(current_user.id)
    )

    return AgentCreditsResponse(
        success=True,
        agent_id=str(current_user.id),
        credit_balance=balance,
        total_transactions=len(transactions),
        transactions=transactions
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
    credits_added, new_balance, transaction = await promotion_service.purchase_credits_service(
        db,
        str(current_user.id),
        purchase_data.package_id,
        purchase_data.payment_method
    )

    return CreditPurchaseResponse(
        success=True,
        message=f"Successfully purchased {credits_added} credits!",
        credits_added=credits_added,
        new_balance=new_balance,
        transaction=transaction
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
    credits_deducted, new_balance, promotion, listing_tier = await promotion_service.promote_listing_service(
        db,
        current_user,
        listing_id,
        promotion_data.tier
    )

    return PromoteListingResponse(
        success=True,
        message=f"Listing promoted to {promotion_data.tier} tier for 30 days! {credits_deducted} credits deducted.",
        credits_deducted=credits_deducted,
        new_balance=new_balance,
        promotion=promotion,
        listing_tier=listing_tier
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
    new_tier = await promotion_service.cancel_promotion_service(
        db,
        current_user,
        listing_id
    )

    return CancelPromotionResponse(
        success=True,
        message="Promotion cancelled successfully. Credits are non-refundable.",
        listing_tier=new_tier
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
    promotions = await promotion_service.get_agent_active_promotions_service(
        db,
        str(current_user.id)
    )

    return AgentActivePromotionsResponse(
        success=True,
        total=len(promotions),
        promotions=promotions
    )
