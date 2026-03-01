"""BuyerDemand SQLAlchemy model."""

from sqlalchemy import Column, String, DateTime, ForeignKey, func, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base


class BuyerDemand(Base):
    """
    Buyer demand model - reverse marketplace where buyers post what they're looking for.

    Workflow:
    1. Buyer creates demand (status: "active")
    2. Verified agents browse active demands
    3. Agent claims demand (status: "assigned", exclusive assignment)
    4. Email sent to buyer with agent contact info
    5. Buyer marks as "fulfilled" or "closed"

    Status lifecycle:
    - active: Available for agents to claim
    - assigned: Claimed by an agent (exclusive, cannot be deleted)
    - fulfilled: Deal completed (cannot be deleted)
    - closed: Cancelled/abandoned (cannot be deleted)

    Deletion rules (historical tracking):
    - active: Can be deleted by buyer or admin
    - assigned/fulfilled/closed: Cannot be deleted (kept for history)

    Demand types:
    - investor: Buyer has money, looking for business
    - seeking_funding: Buyer has business idea, needs investment
    """

    __tablename__ = "buyer_demands"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # ========================================================================
    # BUDGET (EUR only)
    # ========================================================================
    budget_min_eur = Column(Numeric(precision=12, scale=2), nullable=False)
    budget_max_eur = Column(Numeric(precision=12, scale=2), nullable=False)

    # ========================================================================
    # CATEGORY & LOCATION
    # ========================================================================
    # Category: same as Listing.category (restaurant, bar, cafe, etc.)
    category = Column(String, nullable=False, index=True)
    preferred_city_en = Column(String, nullable=False, index=True)
    preferred_area = Column(String, nullable=True)

    # ========================================================================
    # DESCRIPTION
    # ========================================================================
    description = Column(String, nullable=False)

    # ========================================================================
    # STATUS & TYPE
    # ========================================================================
    # Status: "active" | "assigned" | "fulfilled" | "closed"
    status = Column(String, default="active", nullable=False, index=True)

    # Demand type: "investor" | "seeking_funding"
    demand_type = Column(String, default="investor", nullable=False)

    # ========================================================================
    # EXCLUSIVE ASSIGNMENT
    # ========================================================================
    assigned_agent_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)

    # ========================================================================
    # TIMESTAMPS
    # ========================================================================
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ========================================================================
    # RELATIONSHIPS
    # ========================================================================
    buyer = relationship("User", foreign_keys=[buyer_id], back_populates="buyer_demands")
    assigned_agent = relationship("User", foreign_keys=[assigned_agent_id], back_populates="assigned_demands")

    def __repr__(self):
        return f"<BuyerDemand(id={self.id}, buyer_id={self.buyer_id}, status={self.status}, type={self.demand_type})>"
