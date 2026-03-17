"""
File upload routes.

Handles:
- Image uploads (profiles, listings) via direct server upload
- Document viewing (presigned GET URLs for private documents)

Endpoints:
- POST /upload/direct/image - Direct image upload through server (with EXIF stripping)
- GET /upload/document-url - Get presigned URL for viewing private documents
"""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.api.deps import get_verified_user, verify_csrf_token
from app.schemas.upload import DirectUploadResponse
from app.services.upload_service import upload_image_direct
from app.utils.s3_client import extract_key_from_url, generate_presigned_get


# Initialize router
router = APIRouter(prefix="/upload", tags=["File Upload"])


@router.post(
    "/direct/image",
    response_model=DirectUploadResponse,
    summary="Direct image upload",
    description="Upload image directly through server to S3 (EXIF metadata is stripped)"
)
async def upload_image_directly(
    current_user: Annotated[User, Depends(get_verified_user)],
    file: UploadFile = File(...),
    folder: str = Query(default="general", pattern="^(general|profiles|listings)$"),
    _: None = Depends(verify_csrf_token)
):
    """
    Upload image directly through server to S3.

    EXIF metadata (including GPS coordinates) is automatically stripped
    to protect business location privacy.

    **Supported types:** JPEG, PNG, WebP, GIF
    **Max size:** 10 MB
    """
    image_url = await upload_image_direct(file, folder=folder)

    return DirectUploadResponse(
        success=True,
        message="Image uploaded successfully",
        url=image_url
    )


@router.get(
    "/document-url",
    summary="Get presigned URL for viewing a private document",
    description="Generate a temporary (1-hour) signed URL for viewing an agent document"
)
async def get_document_view_url(
    url: str = Query(..., description="The stored document URL"),
    current_user: Annotated[User, Depends(get_verified_user)] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Generate a presigned GET URL for viewing a private document.

    **Access control:**
    - Agents can view their own documents
    - Admins can view any agent's documents

    Returns a signed URL valid for 1 hour.
    """
    key = extract_key_from_url(url)
    if not key or not key.startswith("documents/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid document URL")

    # Agents can only view their own documents
    is_admin = current_user.role == "admin"
    own_document = f"documents/agents/{current_user.id}/" in key
    if not is_admin and not own_document:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this document")

    presigned_url = generate_presigned_get(key, expiration=3600)
    return {"success": True, "url": presigned_url}
