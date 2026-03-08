"""
Authentication and authorization dependencies for FastAPI routes.

These dependencies are used to:
- Inject database sessions into routes
- Authenticate users via JWT tokens
- Enforce role-based access control
- Verify CSRF tokens
- Check agent verification status
"""

import hmac
from typing import Annotated, Optional
from fastapi import Depends, Request, status
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from jose import JWTError

from app.db.session import get_db
from app.models.user import User
from app.core.security import decode_token
from app.core.exceptions import (
    EmailNotVerifiedException,
    AgentNotVerifiedException,
    AgentDocumentsIncompleteException,
    CSRFTokenInvalidException,
    InvalidCredentialsException,
)


# ============================================================================
# CURRENT USER AUTHENTICATION
# ============================================================================

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Extract and verify JWT from cookie, return authenticated user.

    This dependency:
    1. Extracts access token from HTTPOnly cookie
    2. Verifies JWT signature and expiration
    3. Fetches fresh user data from database
    4. Attaches JWT claims to user object (for CSRF verification)

    CRITICAL: Always fetches fresh data from database.
    Do not trust JWT claims for critical operations (e.g., verification status).

    Args:
        request: FastAPI request object
        db: Database session (injected)

    Returns:
        User object with fresh data from database

    Raises:
        HTTPException 401: If token is missing, invalid, or expired
        HTTPException 401: If user not found in database

    Example:
        @app.get("/profile")
        async def get_profile(
            current_user: Annotated[User, Depends(get_current_user)]
        ):
            return {"name": current_user.name, "email": current_user.email}
    """
    # Extract token from cookie
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please log in."
        )

    try:
        # Verify JWT signature and decode
        payload = decode_token(token)
        user_id: str = payload.get("sub")

        if user_id is None:
            raise InvalidCredentialsException()

        # Fetch fresh user data from database
        # CRITICAL: Don't trust JWT claims for verification status!
        result = await db.execute(
            select(User)
            .options(selectinload(User.agent_profile))
            .where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found."
            )

        # Attach JWT claims to user object for CSRF verification
        user._jwt_claims = payload

        return user

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials. Token may be expired or invalid."
        )


# ============================================================================
# EMAIL VERIFICATION CHECK
# ============================================================================

async def get_verified_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """
    Ensure user has verified their email address.

    This dependency chains after get_current_user and adds email verification check.

    Args:
        current_user: Authenticated user (from get_current_user)

    Returns:
        User object (email verified)

    Raises:
        EmailNotVerifiedException: If email is not verified

    Example:
        @app.post("/listings")
        async def create_listing(
            current_user: Annotated[User, Depends(get_verified_user)]
        ):
            # User is authenticated AND email verified
            ...
    """
    if not current_user.email_verified:
        raise EmailNotVerifiedException()

    return current_user


# ============================================================================
# CSRF TOKEN VERIFICATION
# ============================================================================

async def verify_csrf_token(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)]
) -> None:
    """
    Verify CSRF token on state-changing operations (POST, PUT, DELETE, PATCH).

    Double-submit cookie pattern:
    1. CSRF token is embedded in JWT access token claims
    2. Same token is set as non-HTTPOnly cookie (JavaScript can read)
    3. Client must send token in X-CSRF-Token header
    4. We verify header value matches JWT claim value

    Safe methods (GET, HEAD, OPTIONS) skip CSRF check.

    Args:
        request: FastAPI request object
        current_user: Authenticated user with JWT claims attached

    Raises:
        CSRFTokenInvalidException: If CSRF token is missing or doesn't match

    Example:
        @app.post("/listings")
        async def create_listing(
            data: ListingCreate,
            current_user: Annotated[User, Depends(get_verified_user)],
            _: None = Depends(verify_csrf_token)  # CSRF protection
        ):
            ...
    """
    # Skip CSRF check for safe methods
    if request.method in ["GET", "HEAD", "OPTIONS"]:
        return

    # Extract CSRF token from header
    csrf_from_header = request.headers.get("X-CSRF-Token")

    # Extract CSRF token from JWT claims (attached by get_current_user)
    csrf_from_jwt = getattr(current_user, "_jwt_claims", {}).get("csrf")

    # Verify both exist and match
    if not csrf_from_header or not csrf_from_jwt or not hmac.compare_digest(csrf_from_header, csrf_from_jwt):
        raise CSRFTokenInvalidException()


# ============================================================================
# ROLE-BASED ACCESS CONTROL
# ============================================================================

class RoleChecker:
    """
    Role-based access control dependency factory.

    Creates a dependency that checks if user has one of the allowed roles.

    Example:
        # Single role
        require_admin = Depends(RoleChecker(["admin"]))

        @app.delete("/users/{user_id}")
        async def delete_user(
            user_id: str,
            current_user: Annotated[User, require_admin]
        ):
            ...

        # Multiple roles
        require_agent_or_admin = Depends(RoleChecker(["agent", "admin"]))

        @app.get("/listings/agent/{agent_id}")
        async def get_agent_listings(
            agent_id: str,
            current_user: Annotated[User, require_agent_or_admin]
        ):
            ...
    """

    def __init__(self, allowed_roles: list[str]):
        """
        Initialize role checker with allowed roles.

        Args:
            allowed_roles: List of role strings (e.g., ["buyer", "agent", "admin"])
        """
        self.allowed_roles = allowed_roles

    def __call__(
        self,
        current_user: Annotated[User, Depends(get_verified_user)]
    ) -> User:
        """
        Check if user has one of the allowed roles.

        Args:
            current_user: Authenticated and email-verified user

        Returns:
            User object (role authorized)

        Raises:
            HTTPException 403: If user's role is not in allowed_roles
        """
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {', '.join(self.allowed_roles)}"
            )

        return current_user


# ============================================================================
# OWNERSHIP CHECK
# ============================================================================

def ensure_owner_or_admin(
    resource_owner_id: str,
    current_user: User,
    detail: str = "Not authorized"
) -> None:
    """Raise 403 if current_user is neither the resource owner nor an admin."""
    if str(resource_owner_id) != str(current_user.id) and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )


# ============================================================================
# VERIFIED AGENT CHECK
# ============================================================================

async def get_verified_agent(
    current_user: Annotated[User, Depends(get_verified_user)],
) -> User:
    """
    Ensure user is an agent with 'approved' verification status and all documents uploaded.

    Uses the agent_profile already eagerly loaded by get_current_user
    (via selectinload). No extra DB query needed.

    Raises:
        HTTPException 403: If user is not an agent
        HTTPException 404: If agent profile not found
        AgentNotVerifiedException: If verification status is not "approved"
        AgentDocumentsIncompleteException: If any required document is missing
    """
    # Admins bypass agent verification checks
    if current_user.role == "admin":
        return current_user

    if current_user.role != "agent":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent access required."
        )

    agent_profile = current_user.agent_profile
    if not agent_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent profile not found."
        )

    if agent_profile.verification_status != "approved":
        raise AgentNotVerifiedException()

    if not all([
        agent_profile.license_document_url,
        agent_profile.company_document_url,
        agent_profile.id_document_url
    ]):
        raise AgentDocumentsIncompleteException()

    return current_user


# ============================================================================
# OPTIONAL AUTHENTICATION
# ============================================================================

async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Get current user if authenticated, otherwise return None.

    Useful for endpoints that behave differently for authenticated vs anonymous users.

    Args:
        request: FastAPI request object
        db: Database session (injected)

    Returns:
        User object if authenticated, None otherwise

    Example:
        @app.get("/listings")
        async def get_listings(
            current_user: Annotated[Optional[User], Depends(get_current_user_optional)]
        ):
            if current_user:
                # Show saved status for authenticated users
                ...
            else:
                # Anonymous user
                ...
    """
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None
