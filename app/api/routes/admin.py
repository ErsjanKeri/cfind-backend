"""
Admin panel routes.

Endpoints:
- GET /admin/stats - Platform statistics
- GET /admin/users - All users (with role filter)
- POST /admin/agents - Create agent
- POST /admin/buyers - Create buyer
- DELETE /admin/users/{user_id} - Delete user
- POST /admin/agents/{agent_id}/verify - Verify agent
- POST /admin/agents/{agent_id}/reject - Reject agent
- POST /admin/users/{user_id}/toggle-email-verification - Toggle email verification
- POST /admin/credits/adjust - Adjust agent credits
"""

import logging
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.admin import (
    PlatformStatsResponse,
    AdminUsersListResponse,
    AdminCreateAgentRequest, AdminCreateBuyerRequest, AdminCreateUserResponse,
    AgentRejectRequest, AgentVerificationResponse,
    AdminToggleEmailVerificationRequest, AdminToggleEmailVerificationResponse,
    AdminDeleteResponse
)
from app.schemas.promotion import (
    AdminCreditAdjustmentRequest, AdminCreditAdjustmentResponse,
    CreditTransactionResponse
)
from app.api.deps import (
    RoleChecker,
    verify_csrf_token
)
from app.repositories import admin_repo
from app.repositories.user_repo import get_user_by_id
from app.services.email_service import send_agent_rejection_email
from app.repositories import promotion_repo

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/admin", tags=["Admin"])


# ============================================================================
# PLATFORM STATISTICS
# ============================================================================

@router.get(
    "/stats",
    response_model=PlatformStatsResponse,
    summary="Get platform statistics",
    description="Get platform-wide analytics (admin only)"
)
async def get_platform_stats(
    current_user: Annotated[User, Depends(RoleChecker(["admin"]))],
    db: AsyncSession = Depends(get_db)
):
    """
    Get platform-wide statistics.

    **Admin-only endpoint.**

    Returns comprehensive analytics:
    - Total users (by role)
    - Agents (by verification status)
    - Listings (by status)
    - Total leads and demands
    - Active promotions
    - Credit transactions

    **Use case:**
    Admin dashboard overview to monitor platform health.
    """
    stats = await admin_repo.get_platform_stats(db)

    return PlatformStatsResponse(
        success=True,
        stats=stats
    )


# ============================================================================
# USER MANAGEMENT - LIST
# ============================================================================

@router.get(
    "/users",
    response_model=AdminUsersListResponse,
    summary="Get all users",
    description="Get all users with optional role filter (admin only)"
)
async def get_all_users(
    current_user: Annotated[User, Depends(RoleChecker(["admin"]))],
    db: AsyncSession = Depends(get_db),
    role: Optional[str] = Query(None, pattern="^(buyer|agent|admin)$", description="Filter by role")
):
    """
    Get all users.

    **Admin-only endpoint.**

    **Optional filters:**
    - role: Filter by buyer, agent, or admin

    **Returns:**
    - User basic info (id, name, email, role)
    - Email verification status
    - Agent verification status (if agent)
    - Agency name (if agent)
    - Credit balance (if agent)

    **Use case:**
    Admin views all platform users for management.
    """
    users = await admin_repo.get_all_users(db, role)

    return AdminUsersListResponse(
        success=True,
        total=len(users),
        users=users
    )


# ============================================================================
# AGENT VERIFICATION
# ============================================================================

@router.post(
    "/agents/{agent_id}/verify",
    response_model=AgentVerificationResponse,
    summary="Verify agent",
    description="Approve agent verification (admin only)"
)
async def verify_agent(
    agent_id: str,
    current_user: Annotated[User, Depends(RoleChecker(["admin"]))],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Approve agent verification.

    **Admin-only endpoint.**

    **What happens:**
    - verification_status → "approved"
    - verified_at timestamp set
    - Agent's listings become visible to public
    - Agent can create new listings

    **Use case:**
    Admin reviews agent documents and approves them.
    """
    agent_profile = await admin_repo.verify_agent(db, agent_id)

    return AgentVerificationResponse(
        success=True,
        message="Agent verified successfully. Their listings are now visible to buyers.",
        agent_id=str(agent_profile.user_id),
        verification_status=agent_profile.verification_status
    )


@router.post(
    "/agents/{agent_id}/reject",
    response_model=AgentVerificationResponse,
    summary="Reject agent",
    description="Reject agent verification with reason (admin only)"
)
async def reject_agent(
    agent_id: str,
    rejection_data: AgentRejectRequest,
    current_user: Annotated[User, Depends(RoleChecker(["admin"]))],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Reject agent verification.

    **Admin-only endpoint.**

    **What happens:**
    - verification_status → "rejected"
    - rejection_reason stored
    - Email sent to agent with reason
    - Agent can fix issues and resubmit

    **Use case:**
    Admin finds issues with agent documents and rejects with explanation.
    """
    agent_profile = await admin_repo.reject_agent(
        db, agent_id, rejection_data.rejection_reason, str(current_user.id)
    )

    # Send rejection email (don't fail the request if email fails)
    agent_user = await get_user_by_id(db, agent_id, include_profiles=True)
    if agent_user and agent_user.email:
        try:
            await send_agent_rejection_email(
                to_email=agent_user.email,
                agent_name=agent_user.name or "Agent",
                rejection_reason=rejection_data.rejection_reason
            )
        except Exception as e:
            logger.error(f"Failed to send rejection email to {agent_user.email}: {e}")

    return AgentVerificationResponse(
        success=True,
        message="Agent rejected. Rejection email sent with reason.",
        agent_id=str(agent_profile.user_id),
        verification_status=agent_profile.verification_status
    )


# ============================================================================
# USER CREATION
# ============================================================================

@router.post(
    "/agents",
    response_model=AdminCreateUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create agent",
    description="Admin creates agent with pre-verified email (admin only)"
)
async def create_agent(
    agent_data: AdminCreateAgentRequest,
    current_user: Annotated[User, Depends(RoleChecker(["admin"]))],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin creates agent.

    **Admin-only endpoint.**

    **Admin privileges:**
    - Can set email_verified = true (bypass email verification)
    - Can set verification_status = "approved" (pre-approve agent)

    **Use case:**
    Admin creates agent account and can immediately approve them.
    """
    user = await admin_repo.admin_create_agent(
        db,
        agent_data.name,
        agent_data.email,
        agent_data.password,
        agent_data.company_name,
        agent_data.license_number,
        agent_data.phone,
        agent_data.whatsapp,
        agent_data.bio_en,
        agent_data.email_verified,
        agent_data.verification_status
    )

    return AdminCreateUserResponse(
        success=True,
        message=f"Agent created successfully. Email verified: {agent_data.email_verified}",
        user_id=str(user.id),
        email=user.email,
        role=user.role
    )


@router.post(
    "/buyers",
    response_model=AdminCreateUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create buyer",
    description="Admin creates buyer with pre-verified email (admin only)"
)
async def create_buyer(
    buyer_data: AdminCreateBuyerRequest,
    current_user: Annotated[User, Depends(RoleChecker(["admin"]))],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin creates buyer.

    **Admin-only endpoint.**

    **Admin privileges:**
    - Can set email_verified = true (bypass email verification)

    **Use case:**
    Admin creates buyer account for testing or client onboarding.
    """
    user = await admin_repo.admin_create_buyer(
        db,
        buyer_data.name,
        buyer_data.email,
        buyer_data.password,
        buyer_data.company_name,
        buyer_data.email_verified
    )

    return AdminCreateUserResponse(
        success=True,
        message=f"Buyer created successfully. Email verified: {buyer_data.email_verified}",
        user_id=str(user.id),
        email=user.email,
        role=user.role
    )


# ============================================================================
# USER DELETION
# ============================================================================

@router.delete(
    "/users/{user_id}",
    response_model=AdminDeleteResponse,
    summary="Delete user",
    description="Delete user (cascade deletes profile, listings, etc.) (admin only)"
)
async def delete_user(
    user_id: str,
    current_user: Annotated[User, Depends(RoleChecker(["admin"]))],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete user.

    **Admin-only endpoint.**

    **Cascade deletion:**
    - User profile (agent or buyer)
    - All listings (if agent)
    - All leads
    - All saved listings
    - All demands (if buyer)
    - All credit transactions (if agent)

    **Cannot delete:**
    - Admin users (protected)

    **Use case:**
    Admin removes spam accounts or inactive users.
    """
    await admin_repo.admin_delete_user(db, user_id)

    return AdminDeleteResponse(
        success=True,
        message="User deleted successfully"
    )


# ============================================================================
# EMAIL VERIFICATION TOGGLE
# ============================================================================

@router.post(
    "/users/{user_id}/toggle-email-verification",
    response_model=AdminToggleEmailVerificationResponse,
    summary="Toggle email verification",
    description="Toggle user's email verification status (admin only)"
)
async def toggle_email_verification(
    user_id: str,
    toggle_data: AdminToggleEmailVerificationRequest,
    current_user: Annotated[User, Depends(RoleChecker(["admin"]))],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Toggle email verification status.

    **Admin-only endpoint.**

    **Use cases:**
    - Manually verify user email without token
    - Unverify email if suspicious activity
    - Fix email verification issues

    **Effect:**
    - If setting to false: User cannot login
    - If setting to true: User can login immediately
    """
    user = await admin_repo.toggle_email_verification(db, user_id, toggle_data.email_verified)

    return AdminToggleEmailVerificationResponse(
        success=True,
        message=f"Email verification set to {toggle_data.email_verified}",
        user_id=str(user.id),
        email_verified=user.email_verified
    )


# ============================================================================
# CREDIT MANAGEMENT
# ============================================================================

@router.post(
    "/credits/adjust",
    response_model=AdminCreditAdjustmentResponse,
    summary="Adjust agent credits",
    description="Manually add or deduct agent credits (admin only)"
)
async def adjust_agent_credits(
    adjustment_data: AdminCreditAdjustmentRequest,
    current_user: Annotated[User, Depends(RoleChecker(["admin"]))],
    _: None = Depends(verify_csrf_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually adjust agent credits.

    **Admin-only endpoint.**

    **Use cases:**
    - Bonus credits for excellent service
    - Refund for cancelled promotion
    - Compensation for platform issues
    - Manual corrections

    **Amount:**
    - Positive: Add credits
    - Negative: Deduct credits

    **Returns:**
    - Amount adjusted
    - New balance
    - Transaction record
    """
    transaction = await promotion_repo.create_credit_transaction(
        db=db,
        agent_id=adjustment_data.agent_id,
        amount=adjustment_data.amount,
        transaction_type="bonus" if adjustment_data.amount > 0 else "adjustment",
        description=adjustment_data.description
    )
    await db.commit()

    new_balance = await promotion_repo.get_agent_credit_balance(db, adjustment_data.agent_id)

    logger.info(f"Admin adjusted agent {adjustment_data.agent_id} credits by {adjustment_data.amount}")

    return AdminCreditAdjustmentResponse(
        success=True,
        message=f"Adjusted {adjustment_data.amount} credits for agent",
        agent_id=adjustment_data.agent_id,
        amount_adjusted=adjustment_data.amount,
        new_balance=new_balance,
        transaction=CreditTransactionResponse.model_validate(transaction)
    )
