"""Lead and SavedListing SQLAlchemy models."""

from sqlalchemy import Column, String, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base


class Lead(Base):
    """
    Lead model - tracks buyer-agent interactions via listings.

    Deduplication rule:
    One lead per buyer + listing + interaction_type combination.
    Same buyer can create 3 separate leads for same listing via different methods
    (WhatsApp, phone, email).

    Interaction types:
    - whatsapp: Contact via WhatsApp
    - phone: Contact via phone call
    - email: Contact via email
    """

    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id = Column(UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True)
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Interaction type: "whatsapp" | "phone" | "email"
    interaction_type = Column(String, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # ========================================================================
    # RELATIONSHIPS
    # ========================================================================
    listing = relationship("Listing", back_populates="leads")
    buyer = relationship("User", foreign_keys=[buyer_id], back_populates="buyer_leads")
    agent = relationship("User", foreign_keys=[agent_id], back_populates="agent_leads")

    # ========================================================================
    # CONSTRAINTS
    # ========================================================================
    # Unique constraint: one lead per buyer+listing+interaction_type
    __table_args__ = (
        UniqueConstraint('buyer_id', 'listing_id', 'interaction_type', name='uq_lead_buyer_listing_type'),
    )

    def __repr__(self):
        return f"<Lead(id={self.id}, buyer_id={self.buyer_id}, listing_id={self.listing_id}, type={self.interaction_type})>"


class SavedListing(Base):
    """
    Saved listing model - buyer bookmarks.

    Composite primary key: (buyer_id, listing_id)
    """

    __tablename__ = "saved_listings"

    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    listing_id = Column(UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ========================================================================
    # RELATIONSHIPS
    # ========================================================================
    buyer = relationship("User", back_populates="saved_listings")
    listing = relationship("Listing", back_populates="saved_listings")

    def __repr__(self):
        return f"<SavedListing(buyer_id={self.buyer_id}, listing_id={self.listing_id})>"
