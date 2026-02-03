"""
SQLAlchemy models - import all models to ensure relationships resolve correctly.

Import order matters for circular dependencies!
"""

# Import base first
from app.db.base import Base

# Import models in dependency order (least dependent first)
from app.models.token import EmailVerificationToken, PasswordResetToken, RefreshToken
from app.models.user import User, AgentProfile  # BuyerProfile removed
from app.models.listing import Listing, ListingImage
from app.models.lead import Lead, SavedListing
from app.models.demand import BuyerDemand
from app.models.promotion import CreditPackage, PromotionTierConfig, PromotionHistory, CreditTransaction

# Export all models
__all__ = [
    "Base",
    # Token models
    "EmailVerificationToken",
    "PasswordResetToken",
    "RefreshToken",
    # User models
    "User",
    "AgentProfile",
    # "BuyerProfile", # Removed - buyer fields in User table
    # Listing models
    "Listing",
    "ListingImage",
    # Lead models
    "Lead",
    "SavedListing",
    # Demand models
    "BuyerDemand",
    # Promotion models
    "CreditPackage",
    "PromotionTierConfig",
    "PromotionHistory",
    "CreditTransaction",
]