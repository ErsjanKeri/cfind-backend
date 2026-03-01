"""Custom exceptions for the application."""

from fastapi import HTTPException, status


class EmailNotVerifiedException(HTTPException):
    """Raised when user tries to login without verifying email."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address before logging in. Check your inbox for the verification email."
        )


class AgentNotVerifiedException(HTTPException):
    """Raised when unverified agent tries to perform actions requiring verification."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your agent account is pending verification. You cannot perform this action until verified."
        )


class AgentDocumentsIncompleteException(HTTPException):
    """Raised when agent tries to create listing without uploading all documents."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please upload all required documents (license, company registration, and ID) before creating listings."
        )


class InsufficientCreditsException(HTTPException):
    """Raised when agent tries to promote listing without enough credits."""

    def __init__(self, required: int, available: int):
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits. Required: {required}, Available: {available}. Please purchase more credits."
        )


class DemandAlreadyClaimedException(HTTPException):
    """Raised when agent tries to claim already-claimed demand."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This demand has already been claimed by another agent."
        )


class LeadAlreadyExistsException(HTTPException):
    """Raised when trying to create duplicate lead."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already contacted this listing via this method."
        )


class TokenExpiredException(HTTPException):
    """Raised when token (verification, reset) has expired."""

    def __init__(self, token_type: str):
        super().__init__(
            status_code=status.HTTP_410_GONE,
            detail=f"{token_type} token has expired. Please request a new one."
        )


class TokenAlreadyUsedException(HTTPException):
    """Raised when trying to use already-used token."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This token has already been used."
        )


class InvalidCredentialsException(HTTPException):
    """Raised on login with invalid email/password."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )


class CSRFTokenInvalidException(HTTPException):
    """Raised when CSRF token validation fails."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token validation failed. Please refresh and try again."
        )
