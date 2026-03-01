"""
Promotion repository - database operations for promotion system.

Handles:
- Credit package management
- Credit transactions
- Listing promotion with atomic credit deduction
- Promotion history tracking
- Promotion expiration
"""

import logging
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, desc
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
import uuid

from app.models.promotion import CreditPackage, PromotionTierConfig, CreditTransaction, PromotionHistory
from app.models.listing import Listing
from app.models.user import AgentProfile

logger = logging.getLogger(__name__)


# ============================================================================
# CREDIT PACKAGES
# ============================================================================

async def get_credit_packages(db: AsyncSession) -> List[CreditPackage]:
    """
    Get all active credit packages.

    Returns packages sorted by sort_order.

    Args:
        db: Database session

    Returns:
        List of active credit packages

    Example:
        >>> packages = await get_credit_packages(db)
        >>> for pkg in packages:
        ...     print(f"{pkg.name}: {pkg.credits} credits for €{pkg.price_eur}")
    """
    result = await db.execute(
        select(CreditPackage)
        .where(CreditPackage.is_active == True)
        .order_by(CreditPackage.sort_order)
    )

    packages = result.scalars().all()
    logger.info(f"Fetched {len(packages)} credit packages")
    return packages


# ============================================================================
# PROMOTION TIER CONFIGS
# ============================================================================

async def get_promotion_tier_configs(db: AsyncSession) -> List[PromotionTierConfig]:
    """
    Get all active promotion tier configurations.

    Args:
        db: Database session

    Returns:
        List of active promotion tier configs

    Example:
        >>> tiers = await get_promotion_tier_configs(db)
        >>> for tier in tiers:
        ...     print(f"{tier.display_name}: {tier.credit_cost} credits / {tier.duration_days} days")
    """
    result = await db.execute(
        select(PromotionTierConfig)
        .where(PromotionTierConfig.is_active == True)
        .order_by(PromotionTierConfig.credit_cost)  # Featured first, then Premium
    )

    tiers = result.scalars().all()
    logger.info(f"Fetched {len(tiers)} promotion tier configs")
    return tiers


# ============================================================================
# AGENT CREDITS
# ============================================================================

async def get_agent_credit_balance(
    db: AsyncSession,
    agent_id: str
) -> int:
    """
    Get agent's current credit balance.

    Args:
        db: Database session
        agent_id: Agent UUID

    Returns:
        Current credit balance

    Raises:
        HTTPException: If agent not found
    """
    result = await db.execute(
        select(AgentProfile.credit_balance)
        .where(AgentProfile.user_id == agent_id)
    )

    balance = result.scalar_one_or_none()

    if balance is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent profile not found"
        )

    return balance


async def get_agent_credit_transactions(
    db: AsyncSession,
    agent_id: str
) -> List[CreditTransaction]:
    """
    Get all credit transactions for an agent.

    Returns transactions sorted by date (newest first).

    Args:
        db: Database session
        agent_id: Agent UUID

    Returns:
        List of credit transactions

    Example:
        >>> transactions = await get_agent_credit_transactions(db, agent_id)
        >>> for txn in transactions:
        ...     print(f"{txn.type}: {txn.amount} credits - {txn.description}")
    """
    result = await db.execute(
        select(CreditTransaction)
        .where(CreditTransaction.agent_id == agent_id)
        .order_by(desc(CreditTransaction.created_at))
    )

    transactions = result.scalars().all()
    logger.info(f"Fetched {len(transactions)} credit transactions for agent {agent_id}")
    return transactions


# ============================================================================
# CREATE CREDIT TRANSACTION
# ============================================================================

async def create_credit_transaction(
    db: AsyncSession,
    agent_id: str,
    amount: int,
    transaction_type: str,
    description: str,
    listing_id: Optional[str] = None,
    promotion_id: Optional[str] = None,
    payment_reference: Optional[str] = None
) -> CreditTransaction:
    """
    Create credit transaction and update agent balance atomically.

    CRITICAL: This function MUST be called within a transaction context
    to ensure atomic credit updates.

    Args:
        db: Database session
        agent_id: Agent UUID
        amount: Credit amount (positive = add, negative = deduct)
        transaction_type: "purchase" | "usage" | "refund" | "bonus" | "adjustment"
        description: Transaction description
        listing_id: Optional listing reference
        promotion_id: Optional promotion reference
        payment_reference: Optional payment gateway reference

    Returns:
        Created transaction object

    Example:
        >>> async with db.begin():  # Start transaction
        ...     txn = await create_credit_transaction(
        ...         db, agent_id, amount=50, transaction_type="purchase",
        ...         description="Purchased Standard package"
        ...     )
        ...     # Commit happens automatically
    """
    # Create transaction record
    transaction = CreditTransaction(
        id=uuid.uuid4(),
        agent_id=agent_id,
        amount=amount,
        type=transaction_type,
        description=description,
        listing_id=listing_id,
        promotion_id=promotion_id,
        payment_reference=payment_reference
    )

    db.add(transaction)

    # Update agent credit balance atomically
    await db.execute(
        update(AgentProfile)
        .where(AgentProfile.user_id == agent_id)
        .values(credit_balance=AgentProfile.credit_balance + amount)
    )

    await db.flush()  # Ensure transaction is created before returning

    logger.info(f"Created credit transaction: agent={agent_id}, amount={amount}, type={transaction_type}")
    return transaction


# ============================================================================
# LISTING PROMOTION
# ============================================================================

async def promote_listing(
    db: AsyncSession,
    listing_id: str,
    tier: str,
    credit_cost: int,
    duration_days: int
) -> tuple[Listing, PromotionHistory]:
    """
    Promote listing and create promotion history.

    CRITICAL: Call this within a transaction after deducting credits.

    Updates:
    - listing.promotion_tier
    - listing.promotion_start_date
    - listing.promotion_end_date
    Creates:
    - promotion_history record

    Args:
        db: Database session
        listing_id: Listing UUID
        tier: "featured" | "premium"
        credit_cost: Credits deducted for this promotion
        duration_days: Promotion duration

    Returns:
        Tuple of (updated_listing, promotion_history)

    Example:
        >>> async with db.begin():
        ...     # Deduct credits first
        ...     listing, promo = await promote_listing(db, listing_id, "featured", 5, 30)
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

    # Calculate dates
    start_date = datetime.now(timezone.utc)
    end_date = start_date + timedelta(days=duration_days)

    # If upgrading from existing promotion, mark old promotion as expired
    if listing.promotion_tier != "standard":
        # Mark current promotion as expired
        await db.execute(
            update(PromotionHistory)
            .where(
                and_(
                    PromotionHistory.listing_id == listing_id,
                    PromotionHistory.status == "active"
                )
            )
            .values(status="expired")
        )

    # Update listing
    listing.promotion_tier = tier
    listing.promotion_start_date = start_date
    listing.promotion_end_date = end_date

    # Create promotion history
    promotion = PromotionHistory(
        id=uuid.uuid4(),
        listing_id=listing_id,
        tier=tier,
        credit_cost=credit_cost,
        start_date=start_date,
        end_date=end_date,
        status="active"
    )

    db.add(promotion)
    await db.flush()

    logger.info(f"Promoted listing {listing_id} to {tier} tier (ends: {end_date})")
    return listing, promotion


# ============================================================================
# CANCEL PROMOTION
# ============================================================================

async def cancel_promotion(
    db: AsyncSession,
    listing_id: str
) -> Listing:
    """
    Cancel active promotion for a listing.

    NO REFUND - credits are already spent.

    Updates:
    - Marks current PromotionHistory as "cancelled"
    - Checks for other active promotions
    - If no other active promotions, resets listing to "standard" tier

    Args:
        db: Database session
        listing_id: Listing UUID

    Returns:
        Updated listing object

    Raises:
        HTTPException: If listing not found
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

    # Mark current active promotions as cancelled
    await db.execute(
        update(PromotionHistory)
        .where(
            and_(
                PromotionHistory.listing_id == listing_id,
                PromotionHistory.status == "active"
            )
        )
        .values(status="cancelled")
    )

    # Check if there are other active promotions
    result = await db.execute(
        select(PromotionHistory)
        .where(
            and_(
                PromotionHistory.listing_id == listing_id,
                PromotionHistory.status == "active"
            )
        )
    )

    other_active_promotions = result.scalars().all()

    if not other_active_promotions:
        # No other active promotions, reset to standard
        listing.promotion_tier = "standard"
        listing.promotion_start_date = None
        listing.promotion_end_date = None

    await db.commit()
    await db.refresh(listing)

    logger.info(f"Cancelled promotion for listing {listing_id}")
    return listing


# ============================================================================
# GET ACTIVE PROMOTIONS
# ============================================================================

async def get_agent_active_promotions(
    db: AsyncSession,
    agent_id: str
) -> List[PromotionHistory]:
    """
    Get agent's active promotions.

    Returns all promotions with status = "active" for agent's listings.

    Args:
        db: Database session
        agent_id: Agent UUID

    Returns:
        List of active promotions

    Example:
        >>> promotions = await get_agent_active_promotions(db, agent_id)
        >>> print(f"Agent has {len(promotions)} active promotions")
    """
    result = await db.execute(
        select(PromotionHistory)
        .join(Listing, PromotionHistory.listing_id == Listing.id)
        .where(
            and_(
                Listing.agent_id == agent_id,
                PromotionHistory.status == "active"
            )
        )
        .order_by(desc(PromotionHistory.start_date))
    )

    promotions = result.scalars().all()
    logger.info(f"Fetched {len(promotions)} active promotions for agent {agent_id}")
    return promotions


# ============================================================================
# EXPIRE PROMOTIONS (CRON JOB)
# ============================================================================

async def expire_promotions(db: AsyncSession) -> int:
    """
    Expire promotions that have passed their end_date.

    Called by cron job hourly.

    Process:
    1. Find all active promotions with end_date < now()
    2. Mark them as "expired"
    3. For each expired promotion:
       - Check if listing has other active promotions
       - If not, reset listing tier to "standard"

    Args:
        db: Database session

    Returns:
        Count of expired promotions

    Example:
        >>> count = await expire_promotions(db)
        >>> print(f"Expired {count} promotions")
    """
    now = datetime.now(timezone.utc)

    # Find expired promotions
    result = await db.execute(
        select(PromotionHistory)
        .options(selectinload(PromotionHistory.listing))
        .where(
            and_(
                PromotionHistory.status == "active",
                PromotionHistory.end_date < now
            )
        )
    )

    expired_promotions = result.scalars().all()

    if not expired_promotions:
        logger.info("No promotions to expire")
        return 0

    # Mark as expired
    for promotion in expired_promotions:
        promotion.status = "expired"

        # Check if listing has other active promotions
        result = await db.execute(
            select(PromotionHistory)
            .where(
                and_(
                    PromotionHistory.listing_id == promotion.listing_id,
                    PromotionHistory.status == "active",
                    PromotionHistory.id != promotion.id
                )
            )
        )

        other_active = result.scalars().all()

        if not other_active and promotion.listing:
            # No other active promotions, reset listing tier
            promotion.listing.promotion_tier = "standard"
            promotion.listing.promotion_start_date = None
            promotion.listing.promotion_end_date = None

    await db.commit()

    logger.info(f"Expired {len(expired_promotions)} promotions")
    return len(expired_promotions)
