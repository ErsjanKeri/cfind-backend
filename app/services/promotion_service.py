"""
Promotion service - business logic for promotion system.

Handles:
- Credit purchase (simulated payment, later Stripe integration)
- Listing promotion with upgrade cost calculation
- Promotion cancellation
- Promotion expiration
"""

import logging
from typing import List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.user import User
from app.models.listing import Listing
from app.models.promotion import CreditPackage, PromotionTierConfig
from app.repositories import promotion_repo
from app.core.exceptions import InsufficientCreditsException

logger = logging.getLogger(__name__)


# ============================================================================
# GET CREDIT PACKAGES
# ============================================================================

async def get_credit_packages_service(db: AsyncSession) -> List[dict]:
    """
    Get all active credit packages.

    Args:
        db: Database session

    Returns:
        List of credit package dicts

    Example:
        >>> packages = await get_credit_packages_service(db)
        >>> for pkg in packages:
        ...     print(f"{pkg['name']}: {pkg['credits']} credits")
    """
    packages = await promotion_repo.get_credit_packages(db)

    return [
        {
            "id": str(pkg.id),
            "name": pkg.name,
            "credits": pkg.credits,
            "price_eur": float(pkg.price_eur),
            "price_lek": float(pkg.price_lek),
            "is_popular": pkg.is_popular,
            "savings": pkg.savings,
            "is_active": pkg.is_active,
            "sort_order": pkg.sort_order
        }
        for pkg in packages
    ]


# ============================================================================
# GET PROMOTION TIER CONFIGS
# ============================================================================

async def get_promotion_tier_configs_service(db: AsyncSession) -> List[dict]:
    """
    Get all active promotion tier configurations.

    Args:
        db: Database session

    Returns:
        List of promotion tier config dicts
    """
    tiers = await promotion_repo.get_promotion_tier_configs(db)

    return [
        {
            "id": str(tier.id),
            "tier": tier.tier,
            "credit_cost": tier.credit_cost,
            "duration_days": tier.duration_days,
            "display_name": tier.display_name,
            "description": tier.description,
            "badge_color": tier.badge_color,
            "is_active": tier.is_active
        }
        for tier in tiers
    ]


# ============================================================================
# PURCHASE CREDITS
# ============================================================================

async def purchase_credits_service(
    db: AsyncSession,
    agent_id: str,
    package_id: str,
    payment_method: str = "manual"
) -> Tuple[int, int, dict]:
    """
    Purchase credits (simulated payment).

    TODO: Integrate with Stripe/PayPal for real payments.

    Args:
        db: Database session
        agent_id: Agent UUID
        package_id: CreditPackage UUID
        payment_method: "manual" | "stripe" | "paypal"

    Returns:
        Tuple of (credits_added, new_balance, transaction_dict)

    Raises:
        HTTPException: If package not found

    Example:
        >>> credits, balance, txn = await purchase_credits_service(db, agent_id, pkg_id)
        >>> print(f"Purchased {credits} credits, new balance: {balance}")
    """
    # Fetch package
    result = await db.execute(
        select(CreditPackage).where(CreditPackage.id == package_id)
    )
    package = result.scalar_one_or_none()

    if not package or not package.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credit package not found or inactive"
        )

    # TODO: Integrate real payment gateway
    # For now, simulate successful payment
    payment_reference = f"SIM-{payment_method.upper()}-{uuid.uuid4().hex[:8]}"

    # Create transaction (atomic with credit balance update)
    async with db.begin():
        transaction = await promotion_repo.create_credit_transaction(
            db=db,
            agent_id=agent_id,
            amount=package.credits,
            transaction_type="purchase",
            description=f"Purchased {package.name} package ({package.credits} credits)",
            payment_reference=payment_reference
        )

    # Get new balance
    new_balance = await promotion_repo.get_agent_credit_balance(db, agent_id)

    transaction_dict = {
        "id": str(transaction.id),
        "agent_id": str(transaction.agent_id),
        "amount": transaction.amount,
        "type": transaction.type,
        "description": transaction.description,
        "listing_id": None,
        "promotion_id": None,
        "payment_reference": transaction.payment_reference,
        "created_at": transaction.created_at
    }

    logger.info(f"Agent {agent_id} purchased {package.credits} credits (package: {package.name})")
    return package.credits, new_balance, transaction_dict


# ============================================================================
# PROMOTE LISTING
# ============================================================================

async def promote_listing_service(
    db: AsyncSession,
    user: User,
    listing_id: str,
    target_tier: str
) -> Tuple[int, int, dict, str]:
    """
    Promote listing with upgrade cost calculation.

    CRITICAL UPGRADE LOGIC:
    - Standard → Featured: 5 credits
    - Standard → Premium: 15 credits
    - Featured → Premium: 10 credits (only charge difference!)
    - Premium → Premium: Error (already at max tier)

    Validation:
    - User owns listing or is admin
    - Agent has sufficient credits
    - Listing exists and is active

    Args:
        db: Database session
        user: Current user
        listing_id: Listing UUID
        target_tier: "featured" | "premium"

    Returns:
        Tuple of (credits_deducted, new_balance, promotion_dict, listing_tier)

    Raises:
        InsufficientCreditsException: If not enough credits
        HTTPException: If listing not found or not authorized

    Example:
        >>> credits, balance, promo, tier = await promote_listing_service(
        ...     db, user, listing_id, "premium"
        ... )
        >>> print(f"Deducted {credits} credits, new tier: {tier}")
    """
    # Fetch listing
    result = await db.execute(
        select(Listing).where(Listing.id == listing_id)
    )
    listing = result.scalar_one_or_none()

    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found"
        )

    # Check ownership
    if str(listing.agent_id) != str(user.id) and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to promote this listing"
        )

    # Get tier config
    result = await db.execute(
        select(PromotionTierConfig)
        .where(PromotionTierConfig.tier == target_tier)
    )
    tier_config = result.scalar_one_or_none()

    if not tier_config or not tier_config.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Promotion tier '{target_tier}' not found or inactive"
        )

    # Calculate cost based on current tier (upgrade logic)
    current_tier = listing.promotion_tier
    base_cost = tier_config.credit_cost

    if current_tier == "standard":
        # Standard → Featured (5 credits) or Premium (15 credits)
        cost = base_cost
    elif current_tier == "featured":
        if target_tier == "featured":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Listing is already featured"
            )
        elif target_tier == "premium":
            # Featured → Premium: Only charge difference (10 credits)
            # Premium costs 15, Featured costs 5, difference = 10
            featured_cost = 5  # Hardcoded for now, could fetch from tier config
            cost = base_cost - featured_cost  # 15 - 5 = 10
        else:
            cost = base_cost
    elif current_tier == "premium":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Listing is already at maximum promotion tier (Premium)"
        )
    else:
        cost = base_cost

    # Check credits (use agent_id which is listing.agent_id)
    agent_id = str(listing.agent_id)
    current_balance = await promotion_repo.get_agent_credit_balance(db, agent_id)

    if current_balance < cost:
        raise InsufficientCreditsException(required=cost, available=current_balance)

    # Deduct credits and promote listing (atomic transaction)
    async with db.begin():
        # Create deduction transaction
        transaction = await promotion_repo.create_credit_transaction(
            db=db,
            agent_id=agent_id,
            amount=-cost,  # Negative = deduction
            transaction_type="usage",
            description=f"Promoted listing to {target_tier} tier",
            listing_id=listing_id
        )

        # Promote listing
        updated_listing, promotion = await promotion_repo.promote_listing(
            db=db,
            listing_id=listing_id,
            tier=target_tier,
            credit_cost=cost,
            duration_days=tier_config.duration_days
        )

        # Link transaction to promotion
        transaction.promotion_id = promotion.id

    # Get new balance
    new_balance = await promotion_repo.get_agent_credit_balance(db, agent_id)

    promotion_dict = {
        "id": str(promotion.id),
        "listing_id": str(promotion.listing_id),
        "tier": promotion.tier,
        "credit_cost": promotion.credit_cost,
        "start_date": promotion.start_date,
        "end_date": promotion.end_date,
        "status": promotion.status,
        "views_during_promotion": promotion.views_during_promotion,
        "leads_during_promotion": promotion.leads_during_promotion,
        "created_at": promotion.created_at
    }

    logger.info(f"Promoted listing {listing_id} to {target_tier}, deducted {cost} credits")
    return cost, new_balance, promotion_dict, updated_listing.promotion_tier


# ============================================================================
# CANCEL PROMOTION
# ============================================================================

async def cancel_promotion_service(
    db: AsyncSession,
    user: User,
    listing_id: str
) -> str:
    """
    Cancel promotion for a listing.

    NO REFUND - credits are already spent.

    Validation:
    - User owns listing or is admin
    - Listing exists

    Args:
        db: Database session
        user: Current user
        listing_id: Listing UUID

    Returns:
        New listing tier after cancellation

    Raises:
        HTTPException: If not authorized or listing not found
    """
    # Fetch listing
    result = await db.execute(
        select(Listing).where(Listing.id == listing_id)
    )
    listing = result.scalar_one_or_none()

    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found"
        )

    # Check ownership
    if str(listing.agent_id) != str(user.id) and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to cancel this promotion"
        )

    # Cancel promotion
    updated_listing = await promotion_repo.cancel_promotion(db, listing_id)

    logger.info(f"Cancelled promotion for listing {listing_id}, new tier: {updated_listing.promotion_tier}")
    return updated_listing.promotion_tier


# ============================================================================
# GET AGENT CREDITS
# ============================================================================

async def get_agent_credits_service(
    db: AsyncSession,
    agent_id: str
) -> Tuple[int, List[dict]]:
    """
    Get agent's credit balance and transaction history.

    Args:
        db: Database session
        agent_id: Agent UUID

    Returns:
        Tuple of (credit_balance, transactions_list)

    Example:
        >>> balance, txns = await get_agent_credits_service(db, agent_id)
        >>> print(f"Balance: {balance}, Transactions: {len(txns)}")
    """
    # Get balance
    balance = await promotion_repo.get_agent_credit_balance(db, agent_id)

    # Get transactions
    transactions = await promotion_repo.get_agent_credit_transactions(db, agent_id)

    transactions_list = [
        {
            "id": str(txn.id),
            "agent_id": str(txn.agent_id),
            "amount": txn.amount,
            "type": txn.type,
            "description": txn.description,
            "listing_id": str(txn.listing_id) if txn.listing_id else None,
            "promotion_id": str(txn.promotion_id) if txn.promotion_id else None,
            "payment_reference": txn.payment_reference,
            "created_at": txn.created_at
        }
        for txn in transactions
    ]

    return balance, transactions_list


# ============================================================================
# GET AGENT ACTIVE PROMOTIONS
# ============================================================================

async def get_agent_active_promotions_service(
    db: AsyncSession,
    agent_id: str
) -> List[dict]:
    """
    Get agent's active promotions.

    Args:
        db: Database session
        agent_id: Agent UUID

    Returns:
        List of active promotion dicts
    """
    promotions = await promotion_repo.get_agent_active_promotions(db, agent_id)

    return [
        {
            "id": str(promo.id),
            "listing_id": str(promo.listing_id),
            "tier": promo.tier,
            "credit_cost": promo.credit_cost,
            "start_date": promo.start_date,
            "end_date": promo.end_date,
            "status": promo.status,
            "views_during_promotion": promo.views_during_promotion,
            "leads_during_promotion": promo.leads_during_promotion,
            "created_at": promo.created_at
        }
        for promo in promotions
    ]


# ============================================================================
# ADMIN: ADJUST CREDITS
# ============================================================================

async def admin_adjust_credits_service(
    db: AsyncSession,
    agent_id: str,
    amount: int,
    description: str
) -> Tuple[int, dict]:
    """
    Admin manually adjusts agent credits.

    Use cases:
    - Bonus credits for excellent service
    - Refund for cancelled promotion
    - Manual adjustment for errors

    Args:
        db: Database session
        agent_id: Agent UUID
        amount: Amount to add (positive) or deduct (negative)
        description: Reason for adjustment

    Returns:
        Tuple of (new_balance, transaction_dict)

    Example:
        >>> balance, txn = await admin_adjust_credits_service(
        ...     db, agent_id, amount=25, description="Bonus credits"
        ... )
    """
    # Create transaction (atomic with balance update)
    async with db.begin():
        transaction = await promotion_repo.create_credit_transaction(
            db=db,
            agent_id=agent_id,
            amount=amount,
            transaction_type="bonus" if amount > 0 else "adjustment",
            description=description
        )

    # Get new balance
    new_balance = await promotion_repo.get_agent_credit_balance(db, agent_id)

    transaction_dict = {
        "id": str(transaction.id),
        "agent_id": str(transaction.agent_id),
        "amount": transaction.amount,
        "type": transaction.type,
        "description": transaction.description,
        "listing_id": None,
        "promotion_id": None,
        "payment_reference": None,
        "created_at": transaction.created_at
    }

    logger.info(f"Admin adjusted agent {agent_id} credits by {amount}")
    return new_balance, transaction_dict
