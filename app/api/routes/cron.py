"""
Cron job routes (scheduled tasks).

Endpoints:
- GET /cron/expire-promotions - Expire promotions past end_date
- GET /cron/update-currency-rate - Update EUR/LEK exchange rate

Security: Protected with CRON_SECRET header
"""

from fastapi import APIRouter, Header, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.session import get_db
from app.config import settings
from app.repositories.promotion_repo import expire_promotions
import httpx
import logging

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/cron", tags=["Cron Jobs"])


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class ExpirePromotionsResponse(BaseModel):
    """Response schema for promotion expiration."""

    success: bool = True
    expired_count: int
    message: str


class UpdateCurrencyRateResponse(BaseModel):
    """Response schema for currency rate update."""

    success: bool = True
    eur_to_lek_rate: float
    previous_rate: float
    message: str


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

@router.get(
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


# ============================================================================
# UPDATE CURRENCY RATE
# ============================================================================

@router.get(
    "/update-currency-rate",
    response_model=UpdateCurrencyRateResponse,
    summary="Update EUR/LEK exchange rate",
    description="Fetch latest EUR/LEK rate from external API (cron job)"
)
async def update_currency_rate_cron(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_cron_secret)
):
    """
    Update EUR/LEK exchange rate from external API.

    **Secured with X-Cron-Secret header.**

    **Process:**
    1. Call exchangerate-api.io for latest EUR/LEK rate
    2. Update settings.EUR_TO_LEK_RATE
    3. Log old and new rates

    **Schedule:**
    Run daily at 9 AM via external cron

    **Example cron schedule:**
    ```
    0 9 * * * curl -H "X-Cron-Secret: $CRON_SECRET" https://api.cfind.ai/api/cron/update-currency-rate
    ```

    **Returns:**
    - New EUR/LEK rate
    - Previous rate
    """
    previous_rate = settings.EUR_TO_LEK_RATE

    try:
        # Call exchange rate API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.exchangerate-api.com/v4/latest/EUR",
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()

            # Get LEK rate
            lek_rate = data.get("rates", {}).get("ALL")

            if not lek_rate:
                raise ValueError("LEK rate not found in API response")

            # Update rate (in-memory only for now)
            # TODO: Store in database for persistence across restarts
            settings.EUR_TO_LEK_RATE = lek_rate

            logger.info(f"Updated EUR/LEK rate: {previous_rate} → {lek_rate}")

            return UpdateCurrencyRateResponse(
                success=True,
                eur_to_lek_rate=lek_rate,
                previous_rate=previous_rate,
                message=f"Currency rate updated successfully: 1 EUR = {lek_rate} LEK"
            )

    except Exception as e:
        logger.error(f"Failed to update currency rate: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch currency rate: {str(e)}"
        )
