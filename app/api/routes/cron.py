"""
Cron job routes (scheduled tasks).

Endpoints:
- GET /cron/expire-promotions - Expire promotions past end_date

Security: Protected with CRON_SECRET header
"""

from fastapi import APIRouter, Header, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.db.session import get_db
from app.config import settings
from app.schemas.promotion import ExpirePromotionsResponse
from app.repositories.promotion_repo import expire_promotions

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/cron", tags=["Cron Jobs"])


# ============================================================================
# SECURITY: VERIFY CRON SECRET
# ============================================================================

def verify_cron_secret(x_cron_secret: str = Header(...)):
    """
    Verify cron secret header.

    Cron endpoints are protected with a secret header to prevent
    unauthorized triggering.

    Args:
        x_cron_secret: Secret header value

    Raises:
        HTTPException: If secret is invalid or missing

    Example:
        curl -H "X-Cron-Secret: your_secret" http://localhost:8000/api/cron/expire-promotions
    """
    if not settings.CRON_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CRON_SECRET not configured"
        )

    if x_cron_secret != settings.CRON_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cron secret"
        )


# ============================================================================
# EXPIRE PROMOTIONS
# ============================================================================

@router.post(
    "/expire-promotions",
    response_model=ExpirePromotionsResponse,
    summary="Expire promotions",
    description="Find and expire promotions past their end_date (cron job)"
)
async def expire_promotions_cron(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_cron_secret)
):
    """
    Expire promotions past their end_date.

    **Secured with X-Cron-Secret header.**

    **Process:**
    1. Find all active promotions with end_date < now()
    2. Mark them as "expired"
    3. For each expired promotion:
       - Check if listing has other active promotions
       - If not, reset listing tier to "standard"

    **Schedule:**
    Run hourly via external cron (Vercel Cron, AWS EventBridge, crontab)

    **Example cron schedule:**
    ```
    0 * * * * curl -H "X-Cron-Secret: $CRON_SECRET" https://api.cfind.ai/api/cron/expire-promotions
    ```

    **Returns:**
    - Count of expired promotions
    """
    expired_count = await expire_promotions(db)

    return ExpirePromotionsResponse(
        success=True,
        expired_count=expired_count,
        message=f"Expired {expired_count} promotions"
    )
