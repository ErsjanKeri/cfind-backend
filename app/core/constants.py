"""Application constants (business categories, cities, roles, etc.)."""

from enum import Enum


# ============================================================================
# USER ROLES
# ============================================================================

class UserRole(str, Enum):
    """User role enumeration."""
    BUYER = "buyer"
    AGENT = "agent"
    ADMIN = "admin"


# ============================================================================
# AGENT VERIFICATION STATUS
# ============================================================================

class VerificationStatus(str, Enum):
    """Agent verification status enumeration."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ============================================================================
# LISTING STATUS
# ============================================================================

class ListingStatus(str, Enum):
    """Listing status enumeration (simplified, agent-controlled)."""
    DRAFT = "draft"
    ACTIVE = "active"
    SOLD = "sold"
    INACTIVE = "inactive"


# ============================================================================
# PROMOTION TIERS
# ============================================================================

class PromotionTier(str, Enum):
    """Promotion tier enumeration."""
    STANDARD = "standard"  # Free (default)
    FEATURED = "featured"  # 5 credits / 30 days
    PREMIUM = "premium"    # 15 credits / 30 days


# ============================================================================
# BUYER DEMAND STATUS
# ============================================================================

class DemandStatus(str, Enum):
    """Buyer demand status enumeration."""
    ACTIVE = "active"          # Available for agents to claim
    ASSIGNED = "assigned"      # Claimed by an agent
    FULFILLED = "fulfilled"    # Deal completed
    CLOSED = "closed"          # Cancelled/abandoned


# ============================================================================
# BUYER DEMAND TYPE
# ============================================================================

class DemandType(str, Enum):
    """Buyer demand type enumeration."""
    INVESTOR = "investor"                # Has money, looking for business
    SEEKING_FUNDING = "seeking_funding"  # Has business, needs investment


# ============================================================================
# LEAD INTERACTION TYPE
# ============================================================================

class InteractionType(str, Enum):
    """Lead interaction type enumeration."""
    WHATSAPP = "whatsapp"
    PHONE = "phone"
    EMAIL = "email"


# ============================================================================
# CREDIT TRANSACTION TYPE
# ============================================================================

class CreditTransactionType(str, Enum):
    """Credit transaction type enumeration."""
    PURCHASE = "purchase"      # Agent buys credits
    USAGE = "usage"            # Agent spends credits on promotion
    REFUND = "refund"          # Admin refunds credits
    BONUS = "bonus"            # Admin gives bonus credits
    ADJUSTMENT = "adjustment"  # Admin manual adjustment


# ============================================================================
# PROMOTION HISTORY STATUS
# ============================================================================

class PromotionStatus(str, Enum):
    """Promotion history status enumeration."""
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


# ============================================================================
# BUSINESS CATEGORIES
# ============================================================================

BUSINESS_CATEGORIES = [
    "restaurant",
    "bar",
    "cafe",
    "retail",
    "hotel",
    "manufacturing",
    "services",
    "technology",
    "healthcare",
    "education",
    "real-estate",
    "other",
]


# ============================================================================
# COUNTRIES & CITIES
# ============================================================================

VALID_COUNTRY_CODES = ["al", "ae"]

COUNTRY_DATA = {
    "al": {
        "name": "Albania",
        "cities": {
            "Tirana": ["Blloku", "Komuna e Parisit", "Astir", "Ish-Blloku", "Qendër", "Laprakë", "Don Bosko",
                        "21 Dhjetori", "Medreseja", "Selitë"],
            "Durrës": ["Plazh", "Qendër", "Shkozet", "Spitallë", "Currila"],
            "Vlorë": ["Lungomare", "Qendër", "Uji i Ftohtë", "Skelë"],
            "Sarandë": ["Qendër", "Mango"],
            "Shkodër": ["Qendër"],
            "Elbasan": ["Qendër"],
            "Korçë": ["Qendër"],
            "Fier": ["Qendër"],
            "Berat": ["Qendër", "Mangalem", "Goricë"],
            "Gjirokastër": ["Qendër"],
        },
    },
    "ae": {
        "name": "United Arab Emirates",
        "cities": {
            "Dubai": ["Downtown", "Marina", "JBR", "Business Bay", "DIFC", "Deira", "Jumeirah", "Al Barsha",
                       "JLT", "Silicon Oasis", "International City", "Al Quoz"],
            "Abu Dhabi": ["Corniche", "Al Reem Island", "Saadiyat Island", "Yas Island", "Khalifa City",
                           "Al Maryah Island"],
            "Sharjah": ["Al Majaz", "Al Nahda", "Al Qasimia", "Industrial Area"],
            "Ajman": ["Al Nuaimiya", "Al Rashidiya", "Emirates City"],
            "Ras Al Khaimah": ["Al Hamra", "Al Nakheel", "Corniche"],
            "Fujairah": ["City Centre", "Al Faseel"],
        },
    },
}
