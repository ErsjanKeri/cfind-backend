"""Promotion system SQLAlchemy models."""

from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, func, Numeric, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base


class CreditTransaction(Base):
    """
    Credit transaction history - tracks all credit movements.

    Transaction types:
    - purchase: Agent buys credits (amount > 0)
    - usage: Agent spends credits on promotion (amount < 0)
    - refund: Admin refunds credits (amount > 0)
    - bonus: Admin gives bonus credits (amount > 0)
    - adjustment: Admin manual adjustment (amount +/-)
    """

    __tablename__ = "credit_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agent_profiles.user_id", ondelete="CASCADE"), nullable=False, index=True)

    # Amount: positive = credit added, negative = credit used
    amount = Column(Integer, nullable=False)

    # Type: "purchase" | "usage" | "refund" | "bonus" | "adjustment"
    type = Column(String, nullable=False, index=True)

    description = Column(String, nullable=False)

    # Reference to listing if this is a usage transaction
    listing_id = Column(UUID(as_uuid=True), ForeignKey("listings.id", ondelete="SET NULL"), nullable=True, index=True)

    # Reference to promotion if this is a usage transaction
    promotion_id = Column(UUID(as_uuid=True), ForeignKey("promotion_history.id", ondelete="SET NULL"), nullable=True)

    # Payment reference for purchases (e.g., Stripe payment ID)
    payment_reference = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # ========================================================================
    # RELATIONSHIPS
    # ========================================================================
    agent = relationship("AgentProfile", back_populates="credit_transactions")

    def __repr__(self):
        return f"<CreditTransaction(id={self.id}, agent_id={self.agent_id}, amount={self.amount}, type={self.type})>"


class PromotionHistory(Base):
    """
    Promotion history - tracks all promotions (active and expired).

    Status values:
    - active: Currently running
    - expired: Past end_date (auto-set by cron)
    - cancelled: Manually cancelled by agent (no refund)

    Performance metrics:
    - views_during_promotion: Views received during promotion period
    - leads_during_promotion: Leads generated during promotion period
    """

    __tablename__ = "promotion_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id = Column(UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True)

    # Promotion details
    tier = Column(String, nullable=False)  # "featured" | "premium"
    credit_cost = Column(Integer, nullable=False)

    # Duration
    start_date = Column(DateTime(timezone=True), nullable=False, index=True)
    end_date = Column(DateTime(timezone=True), nullable=False, index=True)

    # Status: "active" | "expired" | "cancelled"
    status = Column(String, default="active", nullable=False, index=True)

    # Performance metrics (updated periodically)
    views_during_promotion = Column(Integer, default=0, nullable=False)
    leads_during_promotion = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ========================================================================
    # RELATIONSHIPS
    # ========================================================================
    listing = relationship("Listing", back_populates="promotion_history")

    def __repr__(self):
        return f"<PromotionHistory(id={self.id}, listing_id={self.listing_id}, tier={self.tier}, status={self.status})>"


class CreditPackage(Base):
    """
    Credit package - admin-configurable credit bundles for purchase.

    Examples:
    - Starter: 10 credits for €10
    - Basic: 50 credits for €40
    - Standard: 100 credits for €75 (Save 25%)
    - Pro: 500 credits for €300 (Save 40%)
    - Agency: 1000 credits for €500 (Save 50%)
    """

    __tablename__ = "credit_packages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)  # "Starter", "Basic", "Standard", "Pro", "Agency"
    credits = Column(Integer, nullable=False)  # Number of credits in package

    # Pricing (EUR only)
    price_eur = Column(Numeric(precision=10, scale=2), nullable=False)

    # Display settings
    is_popular = Column(Boolean, default=False, nullable=False)  # Show "Popular" badge
    savings = Column(String, nullable=True)  # e.g., "Save 20%", "Best Value"

    # Admin controls
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<CreditPackage(id={self.id}, name={self.name}, credits={self.credits})>"


class PromotionTierConfig(Base):
    """
    Promotion tier configuration - admin-configurable tier settings.

    Default tiers:
    - featured: 5 credits / 30 days
    - premium: 15 credits / 30 days
    """

    __tablename__ = "promotion_tier_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tier = Column(String, unique=True, nullable=False)  # "featured" | "premium"
    credit_cost = Column(Integer, nullable=False)
    duration_days = Column(Integer, nullable=False)

    # Display settings
    display_name = Column(String, nullable=False)  # "Featured", "Premium"
    description = Column(String, nullable=True)  # Benefit description
    badge_color = Column(String, nullable=True)  # Tailwind color class, e.g., "blue-500", "yellow-500"

    # Admin controls
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<PromotionTierConfig(id={self.id}, tier={self.tier}, cost={self.credit_cost})>"
