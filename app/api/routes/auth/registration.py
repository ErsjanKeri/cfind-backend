"""
User registration.

Endpoints:
- POST /register - Register new user (buyer or agent)
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Request, status, Form, UploadFile, File
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.db.session import get_db
from app.models.user import User, AgentProfile
from app.models.token import EmailVerificationToken
from app.schemas.auth import RegisterResponse
from app.core.security import hash_password, generate_secure_token, validate_password_strength
from app.services.email_service import send_verification_email
from app.services.upload_service import upload_document_direct
from app.core.constants import VALID_COUNTRY_CODES

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
    description="Register a new buyer or agent account. Sends email verification link."
)
@limiter.limit("3/hour")
async def register(
    request: Request,
    db: AsyncSession = Depends(get_db),
    # Common fields
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    phone: Optional[str] = Form(None),
    company_name: Optional[str] = Form(None),
    # Agent-specific fields
    operating_country: Optional[str] = Form(None),
    license_number: Optional[str] = Form(None),
    whatsapp: Optional[str] = Form(None),
    bio_en: Optional[str] = Form(None),
    # Document uploads for agents
    license_document: Optional[UploadFile] = File(None),
    company_document: Optional[UploadFile] = File(None),
    id_document: Optional[UploadFile] = File(None),
):
    """
    Register new user (buyer or agent).

    **Buyer registration**: Only requires name, email, password, role="buyer"

    **Agent registration**: Requires additional fields:
    - company_name (agency name)
    - license_number
    - phone
    - whatsapp (REQUIRED)
    - license_document (file upload - REQUIRED)
    - company_document (file upload - REQUIRED)
    - id_document (file upload - REQUIRED)
    - bio_en (optional)

    After registration:
    1. User created with emailVerified=false
    2. Documents uploaded to S3 (for agents)
    3. Profile created based on role
    4. Verification token generated (24-hour validity)
    5. Verification email sent

    User must verify email before logging in.
    """
    # Validate role
    if role not in ["buyer", "agent"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be 'buyer' or 'agent'"
        )

    # Validate password strength
    try:
        validate_password_strength(password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Check if email already exists
    existing = await db.execute(
        select(User).where(User.email == email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered. Please use a different email or log in."
        )

    # Validate agent-specific fields
    if role == "agent":
        if not operating_country or operating_country not in VALID_COUNTRY_CODES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Operating country is required for agent registration. Must be one of: {', '.join(VALID_COUNTRY_CODES)}"
            )
        if not company_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Company name is required for agent registration"
            )
        if not license_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="License number is required for agent registration"
            )
        if not phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number is required for agent registration"
            )
        if not whatsapp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="WhatsApp number is required for agent registration"
            )
        if not license_document:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="License document is required for agent registration"
            )
        if not company_document:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Company document is required for agent registration"
            )
        if not id_document:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ID/Passport document is required for agent registration"
            )

    # Generate user ID upfront so S3 paths match the actual user
    user_id = uuid.uuid4()

    # Upload documents to S3 for agents (BEFORE creating user)
    license_document_url = None
    company_document_url = None
    id_document_url = None

    if role == "agent":
        license_document_url = await upload_document_direct(
            file=license_document,
            user_id=str(user_id),
            document_type="license"
        )

        company_document_url = await upload_document_direct(
            file=company_document,
            user_id=str(user_id),
            document_type="company"
        )

        id_document_url = await upload_document_direct(
            file=id_document,
            user_id=str(user_id),
            document_type="id"
        )

    # Hash password
    hashed_password = hash_password(password)

    # Create user
    user = User(
        id=user_id,
        name=name,
        email=email,
        password=hashed_password,
        role=role,
        email_verified=False,
        # Common fields (for both buyers and agents)
        phone_number=phone,
        company_name=company_name,
    )
    db.add(user)
    await db.flush()  # Get user.id before creating profile

    # Create agent profile (if agent)
    if role == "agent":
        agent_profile = AgentProfile(
            user_id=user.id,
            operating_country=operating_country,
            license_number=license_number,
            whatsapp_number=whatsapp,
            bio_en=bio_en,
            license_document_url=license_document_url,
            company_document_url=company_document_url,
            id_document_url=id_document_url,
            verification_status="pending",
            submitted_at=datetime.now(timezone.utc)
        )
        db.add(agent_profile)

    # Generate email verification token (24-hour validity)
    token = generate_secure_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=24)

    verification_token = EmailVerificationToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token=token,
        expires=expires
    )
    db.add(verification_token)

    await db.commit()

    # Send verification email
    await send_verification_email(
        to_email=user.email,
        user_name=user.name,
        verification_token=token
    )

    return RegisterResponse(
        success=True,
        message="Registration successful! Please check your email to verify your account.",
        user_id=str(user.id)
    )
