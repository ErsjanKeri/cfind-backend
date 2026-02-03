"""User, AgentProfile, and BuyerProfile SQLAlchemy models."""

from sqlalchemy import Column, String, Boolean, DateTime, Integer, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.db.base import Base


class User(Base):
    """
    User model - base authentication and identity.

    Roles:
    - buyer: Regular buyer account (has BuyerProfile)
    - agent: Business agent account (has AgentProfile)
    - admin: Platform administrator (no profile)
    """

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=True)
    email = Column(String, unique=True, nullable=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    image = Column(String, nullable=True)
    password = Column(String, nullable=True)
    role = Column(String, default="buyer", nullable=False)

    # Common fields for both buyers and agents
    phone_number = Column(String, nullable=True)  # Contact phone
    company_name = Column(String, nullable=True)  # Business/company name (for both!)
    website = Column(String, nullable=True)  # Company website

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")

    # Profile Relations
    # Agents have extended profile for verification/documents
    agent_profile = relationship("AgentProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    # BuyerProfile removed - buyer fields are now in User table

    # Data Relations
    listings = relationship("Listing", back_populates="agent", cascade="all, delete-orphan")
    buyer_leads = relationship("Lead", back_populates="buyer", foreign_keys="[Lead.buyer_id]")
    agent_leads = relationship("Lead", back_populates="agent", foreign_keys="[Lead.agent_id]")
    saved_listings = relationship("SavedListing", back_populates="buyer", cascade="all, delete-orphan")

    # Buyer Demands
    buyer_demands = relationship("BuyerDemand", back_populates="buyer", foreign_keys="[BuyerDemand.buyer_id]", cascade="all, delete-orphan")
    assigned_demands = relationship("BuyerDemand", back_populates="assigned_agent", foreign_keys="[BuyerDemand.assigned_agent_id]")

    # Token Relations
    email_verification_tokens = relationship("EmailVerificationToken", back_populates="user", cascade="all, delete-orphan")
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"


class AgentProfile(Base):
    """
    Agent profile - extended information for business agents.

    Verification flow:
    1. Agent registers with basic info
    2. Uploads 3 required documents (license, company registration, ID)
    3. Admin reviews and approves/rejects
    4. verificationStatus is the single source of truth

    Re-verification triggers:
    - Updating license_number
    - Uploading new documents

    Note: agency_name removed - use User.company_name instead!
    Note: phone_number removed - use User.phone_number instead!
    """

    __tablename__ = "agent_profiles"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)

    # Agent-specific fields (phone, company_name moved to User table!)
    license_number = Column(String, nullable=True)  # Business license number
    whatsapp_number = Column(String, nullable=True)  # WhatsApp for business
    bio_en = Column(String, nullable=True)  # Agent bio/description

    # Required document uploads
    license_document_url = Column(String, nullable=True)
    company_document_url = Column(String, nullable=True)
    id_document_url = Column(String, nullable=True)

    # Verification status - single source of truth
    # Values: "pending" | "approved" | "rejected"
    verification_status = Column(String, default="pending", nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(String, nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by = Column(String, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)

    # Cached counts
    listings_count = Column(Integer, default=0, nullable=False)
    deals_completed = Column(Integer, default=0, nullable=False)

    # Promotion Credits System
    credit_balance = Column(Integer, default=0, nullable=False)

    # Relationships
    user = relationship("User", back_populates="agent_profile")
    credit_transactions = relationship("CreditTransaction", back_populates="agent", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<AgentProfile(user_id={self.user_id}, status={self.verification_status})>"


# BuyerProfile class REMOVED - buyer fields moved to User table
# Migration: 20260127_150000_simplify_user_profiles.py


class Session(Base):
    """
    NextAuth-compatible session model.
    Note: For FastAPI JWT auth, we use RefreshToken model instead.
    This is kept for potential compatibility/migration purposes.
    """

    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    session_token = Column(String, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires = Column(DateTime(timezone=True), nullable=False)

    # Relationships
    user = relationship("User", back_populates="sessions")

    def __repr__(self):
        return f"<Session(id={self.id}, user_id={self.user_id})>"
