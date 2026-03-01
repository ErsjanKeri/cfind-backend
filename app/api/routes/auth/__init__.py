"""
Authentication routes package.

Sub-modules:
- registration: User signup (buyer and agent onboarding)
- session: Login, token refresh, logout
- verification: Email verification
- password: Password reset flow
"""

from fastapi import APIRouter

from app.api.routes.auth.registration import router as registration_router
from app.api.routes.auth.session import router as session_router
from app.api.routes.auth.verification import router as verification_router
from app.api.routes.auth.password import router as password_router

router = APIRouter(prefix="/auth", tags=["Authentication"])

router.include_router(registration_router)
router.include_router(session_router)
router.include_router(verification_router)
router.include_router(password_router)
