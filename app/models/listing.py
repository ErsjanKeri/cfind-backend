"""Listing and ListingImage SQLAlchemy models."""

from sqlalchemy import Column, String, Boolean, DateTime, Integer, Float, ForeignKey, func, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base


class Listing(Base):
    """
    Listing model - business listings for sale.

    Visibility:
    - Public fields: Shown to all users (hiding real business identity)
    - Private fields: Shown only to listing owner (agent) or admin

    Status values:
    - pending: Awaiting admin verification (default for new/edited listings)
    - active: Approved by admin, visible to public
    - rejected: Rejected by admin (agent can edit and resubmit)
    - sold: Marked as sold (hidden from public)
    - inactive: Temporarily paused (hidden from public)

    Promotion tiers:
    - standard: Free (default)
    - featured: 5 credits / 30 days
    - premium: 15 credits / 30 days
    """

    __tablename__ = "listings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    country_code = Column(String(2), ForeignKey("countries.code"), nullable=False, default="al", index=True)

    # Status: "pending" | "active" | "rejected" | "sold" | "inactive"
    status = Column(String, default="pending", nullable=False, index=True)
    rejection_reason = Column(String, nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)

    # ========================================================================
    # PROMOTION SYSTEM (PropertyFinder-style)
    # ========================================================================
    # Tier: "standard" (free) | "featured" (5 credits) | "premium" (15 credits)
    promotion_tier = Column(String, default="standard", nullable=False, index=True)
    promotion_start_date = Column(DateTime(timezone=True), nullable=True)
    promotion_end_date = Column(DateTime(timezone=True), nullable=True)

    # ========================================================================
    # PUBLIC INFORMATION (visible to all users)
    # ========================================================================
    public_title_en = Column(String, nullable=False)
    public_description_en = Column(String, nullable=False)
    category = Column(String, nullable=False, index=True)
    public_location_city_en = Column(String, nullable=False, index=True)
    public_location_area = Column(String, nullable=True)

    # ========================================================================
    # PRIVATE INFORMATION (visible only to owner/admin)
    # ========================================================================
    real_business_name = Column(String, nullable=True)
    real_location_address = Column(String, nullable=True)
    real_location_lat = Column(Float, nullable=True)
    real_location_lng = Column(Float, nullable=True)
    real_description_en = Column(String, nullable=True)

    # ========================================================================
    # FINANCIALS (EUR only)
    # ========================================================================
    # Using Numeric for precise decimal values
    asking_price_eur = Column(Numeric(precision=12, scale=2), nullable=False, index=True)
    monthly_revenue_eur = Column(Numeric(precision=12, scale=2), nullable=True, index=True)
    roi = Column(Numeric(precision=10, scale=2), nullable=True, index=True)  # Auto-calculated

    # ========================================================================
    # BUSINESS DETAILS
    # ========================================================================
    employee_count = Column(Integer, nullable=True)
    years_in_operation = Column(Integer, nullable=True)
    is_physically_verified = Column(Boolean, default=False, nullable=False, index=True)

    # ========================================================================
    # METADATA
    # ========================================================================
    view_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ========================================================================
    # RELATIONSHIPS
    # ========================================================================
    agent = relationship("User", back_populates="listings")
    images = relationship("ListingImage", back_populates="listing", cascade="all, delete-orphan", order_by="ListingImage.order")
    leads = relationship("Lead", back_populates="listing", cascade="all, delete-orphan")
    saved_listings = relationship("SavedListing", back_populates="listing", cascade="all, delete-orphan")
    promotion_history = relationship("PromotionHistory", back_populates="listing", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Listing(id={self.id}, title={self.public_title_en}, status={self.status}, tier={self.promotion_tier})>"


class ListingImage(Base):
    """
    Listing images - supports multiple images per listing.

    Images are ordered by the 'order' field (0, 1, 2, ...).
    First image (order=0) is the featured/primary image.
    """

    __tablename__ = "listing_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id = Column(UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String, nullable=False)
    order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    listing = relationship("Listing", back_populates="images")

    def __repr__(self):
        return f"<ListingImage(id={self.id}, listing_id={self.listing_id}, order={self.order})>"
