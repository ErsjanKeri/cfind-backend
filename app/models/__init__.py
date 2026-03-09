"""
SQLAlchemy models - import all models to ensure relationships resolve correctly.

Import order matters for circular dependencies!
"""

# Import base first
from app.db.base import Base

# Import models in dependency order (least dependent first)
from app.models.country import Country, City
from app.models.token import EmailVerificationToken, PasswordResetToken, RefreshToken
from app.models.user import User, AgentProfile
from app.models.listing import Listing, ListingImage
from app.models.lead import Lead, SavedListing
from app.models.demand import BuyerDemand
from app.models.promotion import CreditPackage, PromotionTierConfig, PromotionHistory, CreditTransaction
from app.models.conversation import Conversation, Message

# Export all models
__all__ = [
    "Base",
    "Country",
    "City",
    "EmailVerificationToken",
    "PasswordResetToken",
    "RefreshToken",
    "User",
    "AgentProfile",
    "Listing",
    "ListingImage",
    "Lead",
    "SavedListing",
    "BuyerDemand",
    "CreditPackage",
    "PromotionTierConfig",
    "PromotionHistory",
    "CreditTransaction",
    "Conversation",
    "Message",
]
