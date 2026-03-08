"""
FastAPI main application.

Initializes the FastAPI app with:
- CORS middleware
- Rate limiting
- Authentication routes
- Health check endpoint
- Error handlers
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging

from app.config import settings
from app.api.routes import auth, users, upload, listings, leads, demands, promotions, admin, cron

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.ENVIRONMENT == "development" else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info(f"Starting {settings.APP_NAME}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"CORS Origins: {settings.cors_origins_list}")
    logger.info(f"JWT Algorithm: {settings.JWT_ALGORITHM}")
    logger.info(f"Access Token Expiry: {settings.ACCESS_TOKEN_EXPIRE_MINUTES} minutes")
    logger.info(f"Refresh Token Expiry: {settings.REFRESH_TOKEN_EXPIRE_DAYS} days")

    from app.config import JWT_PRIVATE_KEY, JWT_PUBLIC_KEY
    if not JWT_PRIVATE_KEY or not JWT_PUBLIC_KEY:
        logger.warning("JWT keys not loaded! Run: bash scripts/generate_jwt_keys.sh")

    yield

    logger.info(f"Shutting down {settings.APP_NAME}")


app = FastAPI(
    title=settings.APP_NAME,
    description="RESTful API for CompanyFinder Albania - Business acquisition marketplace platform",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT == "development" else None,
    lifespan=lifespan,
)

# ============================================================================
# CORS MIDDLEWARE
# ============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,  # Required for cookies
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
    expose_headers=["Content-Type"],
    max_age=3600,  # Cache preflight requests for 1 hour
)

# ============================================================================
# RATE LIMITING
# ============================================================================

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ============================================================================
# EXCEPTION HANDLERS
# ============================================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle Pydantic validation errors with detailed error messages.
    """
    errors = []
    for error in exc.errors():
        errors.append({
            "field": " -> ".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })

    logger.warning(f"Validation error on {request.url}: {errors}")

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": errors
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """
    Catch-all exception handler for unexpected errors.
    """
    logger.error(f"Unexpected error on {request.url}: {str(exc)}", exc_info=True)

    # In production, don't expose internal error details
    if settings.ENVIRONMENT == "production":
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"}
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": str(exc)}
        )

# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get(
    "/",
    tags=["Root"],
    summary="API Root",
    description="Welcome message and API status"
)
async def root():
    """
    API root endpoint.

    Returns basic information about the API.
    """
    return {
        "message": "Welcome to CompanyFinder Albania API",
        "version": "1.0.0",
        "docs": "/docs" if settings.ENVIRONMENT == "development" else "Disabled in production",
        "status": "online"
    }


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get(
    "/health",
    tags=["Health"],
    summary="Health Check",
    description="Check if API is running and responsive"
)
async def health_check():
    """
    Health check endpoint for monitoring and container orchestration.

    Returns:
        - status: "healthy"
        - environment: Current environment (development/production)
    """
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "service": "CompanyFinder Albania API"
    }


# ============================================================================
# REGISTER ROUTERS
# ============================================================================

# Authentication routes
app.include_router(
    auth.router,
    prefix=settings.API_PREFIX,
    tags=["Authentication"]
)

# User profile routes (Phase 2)
app.include_router(
    users.router,
    prefix=settings.API_PREFIX,
    tags=["Users"]
)

# File upload routes (Phase 2)
app.include_router(
    upload.router,
    prefix=settings.API_PREFIX,
    tags=["File Upload"]
)

# Listings routes (Phase 3)
app.include_router(
    listings.router,
    prefix=settings.API_PREFIX,
    tags=["Listings"]
)

# Leads and saved listings routes (Phase 4)
app.include_router(
    leads.router,
    prefix=settings.API_PREFIX,
    tags=["Leads"]
)

# Buyer demands routes (Phase 5)
app.include_router(
    demands.router,
    prefix=settings.API_PREFIX,
    tags=["Buyer Demands"]
)

# Promotion system routes (Phase 6-7)
app.include_router(
    promotions.router,
    prefix=settings.API_PREFIX,
    tags=["Promotions"]
)

# Admin panel routes (Phase 8)
app.include_router(
    admin.router,
    prefix=settings.API_PREFIX,
    tags=["Admin"]
)

# Cron job routes (Phase 9)
app.include_router(
    cron.router,
    prefix=settings.API_PREFIX,
    tags=["Cron Jobs"]
)


# ============================================================================
# APPLICATION ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT == "development",
        log_level="info" if settings.ENVIRONMENT == "development" else "warning"
    )


