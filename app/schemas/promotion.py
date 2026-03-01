"""Pydantic schemas for promotion system operations."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

from app.schemas.base import BaseSchema


# ============================================================================
# CREDIT PACKAGE
# ============================================================================

class CreditPackageResponse(BaseSchema):
    """Response schema for credit package."""

    id: str
    name: str
    credits: int
    price_eur: float
    is_popular: bool
    savings: Optional[str] = None
    is_active: bool
    sort_order: int


class CreditPackagesResponse(BaseSchema):
    """Response schema for credit packages list."""

    success: bool = True
    total: int
    packages: List[CreditPackageResponse]


# ============================================================================
# PROMOTION TIER CONFIG
# ============================================================================

class PromotionTierConfigResponse(BaseSchema):
    """Response schema for promotion tier config."""

    id: str
    tier: str  # "featured" | "premium"
    credit_cost: int
    duration_days: int
    display_name: str
    description: Optional[str] = None
    badge_color: Optional[str] = None
    is_active: bool


class PromotionTierConfigsResponse(BaseSchema):
    """Response schema for promotion tier configs list."""

    success: bool = True
    total: int
    tiers: List[PromotionTierConfigResponse]


# ============================================================================
# CREDIT TRANSACTION
# ============================================================================

class CreditTransactionResponse(BaseSchema):
    """Response schema for credit transaction."""

    id: str
    agent_id: str
    amount: int  # Positive = added, negative = used
    type: str  # "purchase" | "usage" | "refund" | "bonus" | "adjustment"
    description: str
    listing_id: Optional[str] = None
    promotion_id: Optional[str] = None
    payment_reference: Optional[str] = None
    created_at: datetime


class AgentCreditsResponse(BaseSchema):
    """Response schema for agent's credit balance and transactions."""

    success: bool = True
    agent_id: str
    credit_balance: int
    total_transactions: int
    transactions: List[CreditTransactionResponse]


# ============================================================================
# PROMOTION HISTORY
# ============================================================================

class PromotionHistoryResponse(BaseSchema):
    """Response schema for promotion history."""

    id: str
    listing_id: str
    tier: str  # "featured" | "premium"
    credit_cost: int
    start_date: datetime
    end_date: datetime
    status: str  # "active" | "expired" | "cancelled"
    views_during_promotion: int
    leads_during_promotion: int
    created_at: datetime


class AgentActivePromotionsResponse(BaseSchema):
    """Response schema for agent's active promotions."""

    success: bool = True
    total: int
    promotions: List[PromotionHistoryResponse]


# ============================================================================
# CREDIT PURCHASE
# ============================================================================

class CreditPurchaseRequest(BaseModel):
    """Request schema for purchasing credits."""

    package_id: str = Field(..., min_length=36, max_length=36)
    payment_method: str = Field(default="manual", pattern="^(manual|stripe|paypal)$")

    model_config = {
        "json_schema_extra": {
            "example": {
                "package_id": "123e4567-e89b-12d3-a456-426614174000",
                "payment_method": "manual"
            }
        }
    }


class CreditPurchaseResponse(BaseSchema):
    """Response schema for credit purchase."""

    success: bool = True
    message: str
    credits_added: int
    new_balance: int
    transaction: CreditTransactionResponse


# ============================================================================
# LISTING PROMOTION
# ============================================================================

class PromoteListingRequest(BaseModel):
    """Request schema for promoting a listing."""

    tier: str = Field(..., pattern="^(featured|premium)$")

    model_config = {
        "json_schema_extra": {
            "example": {
                "tier": "featured"
            }
        }
    }


class PromoteListingResponse(BaseSchema):
    """Response schema for listing promotion."""

    success: bool = True
    message: str
    credits_deducted: int
    new_balance: int
    promotion: PromotionHistoryResponse
    listing_tier: str


# ============================================================================
# CANCEL PROMOTION
# ============================================================================

class CancelPromotionResponse(BaseSchema):
    """Response schema for promotion cancellation."""

    success: bool = True
    message: str = "Promotion cancelled. Credits are non-refundable."
    listing_tier: str  # New tier after cancellation


# ============================================================================
# ADMIN CREDIT ADJUSTMENT
# ============================================================================

class AdminCreditAdjustmentRequest(BaseModel):
    """Request schema for admin credit adjustment."""

    agent_id: str = Field(..., min_length=36, max_length=36)
    amount: int = Field(..., description="Positive to add, negative to deduct")
    description: str = Field(..., min_length=5, max_length=200)

    model_config = {
        "json_schema_extra": {
            "example": {
                "agent_id": "123e4567-e89b-12d3-a456-426614174000",
                "amount": 25,
                "description": "Bonus credits for excellent service"
            }
        }
    }


class AdminCreditAdjustmentResponse(BaseSchema):
    """Response schema for admin credit adjustment."""

    success: bool = True
    message: str
    agent_id: str
    amount_adjusted: int
    new_balance: int
    transaction: CreditTransactionResponse


# ============================================================================
# CRON JOB RESPONSES
# ============================================================================

class ExpirePromotionsResponse(BaseSchema):
    """Response schema for scheduled promotion expiration job."""

    success: bool = True
    expired_count: int
    message: str
