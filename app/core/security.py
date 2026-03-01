"""
Core security module for authentication and authorization.

Includes:
- Argon2id password hashing (production-grade parameters)
- RS256 JWT token creation and verification
- CSRF token generation
- Secure random token generation
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Any
from jose import jwt, JWTError
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from app.config import settings, JWT_PRIVATE_KEY, JWT_PUBLIC_KEY


# ============================================================================
# ARGON2 PASSWORD HASHING
# ============================================================================

# Initialize Argon2 password hasher with OWASP-recommended parameters
ph = PasswordHasher(
    time_cost=2,          # Number of iterations (OWASP min: 2)
    memory_cost=65536,    # 64 MB memory (OWASP min: 19 MB, recommended: 64 MB)
    parallelism=4,        # Number of threads (OWASP min: 1, recommended: 4)
    hash_len=32,          # Output hash length
    salt_len=16,          # Salt length
    encoding='utf-8',
)


def validate_password_strength(password: str) -> str:
    """
    Validate password meets strength requirements. Raises ValueError if not.
    Returns the password if valid (for use as Pydantic field_validator).
    """
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if not any(c.isupper() for c in password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not any(c.islower() for c in password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not any(c.isdigit() for c in password):
        raise ValueError("Password must contain at least one number")
    return password


def hash_password(password: str) -> str:
    """
    Hash password using Argon2id.

    Args:
        password: Plain text password

    Returns:
        Hashed password string

    Example:
        >>> hashed = hash_password("my_secure_password")
        >>> print(hashed)
        $argon2id$v=19$m=65536,t=2,p=4$...
    """
    return ph.hash(password)


def verify_password(password: str, hashed: str) -> tuple[bool, Optional[str]]:
    """
    Verify password and check if rehash is needed.

    If Argon2 parameters have changed (e.g., increased memory cost),
    this will detect it and return a new hash.

    Args:
        password: Plain text password to verify
        hashed: Hashed password from database

    Returns:
        tuple: (is_valid: bool, new_hash_if_needed: Optional[str])

    Example:
        >>> is_valid, new_hash = verify_password("my_password", hashed_from_db)
        >>> if is_valid:
        ...     if new_hash:
        ...         # Update password in database with new_hash
        ...         update_user_password(user_id, new_hash)
        ...     # Proceed with login
        >>> else:
        ...     # Invalid password
    """
    try:
        # Verify password
        ph.verify(hashed, password)

        # Check if rehash needed (parameters changed)
        if ph.check_needs_rehash(hashed):
            new_hash = hash_password(password)
            return True, new_hash

        return True, None

    except VerifyMismatchError:
        return False, None


# ============================================================================
# JWT TOKEN MANAGEMENT (RS256)
# ============================================================================

def create_access_token(
    subject: str,
    additional_claims: Optional[dict[str, Any]] = None,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT access token signed with RS256.

    Access tokens are short-lived (default: 15 minutes) and contain
    user information for API authentication.

    Args:
        subject: User ID (sub claim)
        additional_claims: Extra claims to include (email, role, csrf, etc.)
        expires_delta: Custom expiration timedelta (default: ACCESS_TOKEN_EXPIRE_MINUTES)

    Returns:
        Encoded JWT token string

    Example:
        >>> token = create_access_token(
        ...     subject=str(user.id),
        ...     additional_claims={
        ...         "email": user.email,
        ...         "role": user.role,
        ...         "csrf": csrf_token
        ...     }
        ... )
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    expire = datetime.now(timezone.utc) + expires_delta

    to_encode = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": secrets.token_urlsafe(16),  # Unique token ID
    }

    if additional_claims:
        to_encode.update(additional_claims)

    encoded_jwt = jwt.encode(
        to_encode,
        JWT_PRIVATE_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(
    subject: str,
    session_id: str,
    expires_delta: Optional[timedelta] = None
) -> tuple[str, str]:
    """
    Create JWT refresh token signed with RS256.

    Refresh tokens are long-lived (7-30 days) and are used to obtain
    new access tokens without re-authentication.

    Args:
        subject: User ID (sub claim)
        session_id: Session UUID for tracking
        expires_delta: Custom expiration timedelta (default: REFRESH_TOKEN_EXPIRE_DAYS)

    Returns:
        tuple: (encoded_token: str, jti: str)
            - encoded_token: JWT token string
            - jti: Token ID (store in database for revocation)

    Example:
        >>> token, jti = create_refresh_token(
        ...     subject=str(user.id),
        ...     session_id=str(session_uuid)
        ... )
        >>> # Store jti in database RefreshToken table
        >>> refresh_record = RefreshToken(jti=jti, user_id=user.id, ...)
    """
    if expires_delta is None:
        expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    expire = datetime.now(timezone.utc) + expires_delta
    jti = secrets.token_urlsafe(32)  # Unique token ID (stored in DB)

    to_encode = {
        "sub": subject,
        "jti": jti,
        "session_id": session_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    encoded_jwt = jwt.encode(
        to_encode,
        JWT_PRIVATE_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt, jti


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and verify JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded token payload (dict)

    Raises:
        JWTError: If token is invalid, expired, or signature verification fails

    Example:
        >>> try:
        ...     payload = decode_token(token)
        ...     user_id = payload.get("sub")
        ...     email = payload.get("email")
        ... except JWTError:
        ...     # Handle invalid token
    """
    return jwt.decode(
        token,
        JWT_PUBLIC_KEY,
        algorithms=[settings.JWT_ALGORITHM]
    )


# ============================================================================
# CSRF TOKEN GENERATION
# ============================================================================

def generate_csrf_token() -> str:
    """
    Generate cryptographically secure CSRF token.

    CSRF tokens are embedded in JWT access tokens and sent as HTTPOnly=False
    cookies so JavaScript can read them and include them in request headers.

    Returns:
        32-byte URL-safe token string

    Example:
        >>> csrf_token = generate_csrf_token()
        >>> # Include in JWT claims
        >>> access_token = create_access_token(
        ...     subject=user_id,
        ...     additional_claims={"csrf": csrf_token}
        ... )
        >>> # Set as non-HTTPOnly cookie
        >>> response.set_cookie("csrf_token", csrf_token, httponly=False)
    """
    return secrets.token_urlsafe(32)


# ============================================================================
# SECURE RANDOM TOKEN GENERATION
# ============================================================================

def generate_secure_token() -> str:
    """
    Generate cryptographically secure random token.

    Used for:
    - Email verification tokens
    - Password reset tokens
    - Any single-use security tokens

    Returns:
        32-byte URL-safe token string (64 characters)

    Example:
        >>> token = generate_secure_token()
        >>> verification_token = EmailVerificationToken(
        ...     user_id=user.id,
        ...     token=token,
        ...     expires=datetime.now(timezone.utc) + timedelta(hours=24)
        ... )
    """
    return secrets.token_urlsafe(32)
