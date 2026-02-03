"""
File upload service.

Handles:
- File validation (type, size)
- Image uploads (profile pictures, listing images)
- Document uploads (agent verification documents)
- S3 presigned URL generation
- Direct server uploads
"""

import logging
from typing import Optional, Dict, Any
from fastapi import UploadFile, HTTPException, status
from app.utils.s3_client import (
    generate_presigned_post,
    upload_file,
    delete_file,
    get_public_url,
    generate_image_key,
    generate_document_key,
    extract_key_from_url
)

logger = logging.getLogger(__name__)


# ============================================================================
# FILE VALIDATION
# ============================================================================

# Allowed MIME types
ALLOWED_IMAGE_TYPES = [
    'image/jpeg',
    'image/jpg',
    'image/png',
    'image/webp',
    'image/gif'
]

ALLOWED_DOCUMENT_TYPES = [
    'application/pdf',
    'image/jpeg',
    'image/jpg',
    'image/png'
]

# File size limits (in bytes)
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_DOCUMENT_SIZE = 15 * 1024 * 1024  # 15 MB


def validate_image_file(
    content_type: str,
    file_size: Optional[int] = None
) -> None:
    """
    Validate image file type and size.

    Args:
        content_type: MIME type
        file_size: File size in bytes (optional)

    Raises:
        HTTPException: If validation fails
    """
    # Validate content type
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image type. Allowed types: {', '.join(ALLOWED_IMAGE_TYPES)}"
        )

    # Validate file size
    if file_size and file_size > MAX_IMAGE_SIZE:
        max_mb = MAX_IMAGE_SIZE / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image file too large. Maximum size: {max_mb} MB"
        )


def validate_document_file(
    content_type: str,
    file_size: Optional[int] = None
) -> None:
    """
    Validate document file type and size.

    Args:
        content_type: MIME type
        file_size: File size in bytes (optional)

    Raises:
        HTTPException: If validation fails
    """
    # Validate content type
    if content_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document type. Allowed types: {', '.join(ALLOWED_DOCUMENT_TYPES)}"
        )

    # Validate file size
    if file_size and file_size > MAX_DOCUMENT_SIZE:
        max_mb = MAX_DOCUMENT_SIZE / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Document file too large. Maximum size: {max_mb} MB"
        )


# ============================================================================
# PRESIGNED URL GENERATION
# ============================================================================

async def generate_image_upload_url(
    filename: str,
    content_type: str,
    folder: str = "general"
) -> Dict[str, Any]:
    """
    Generate presigned URL for image upload.

    Args:
        filename: Original filename
        content_type: MIME type
        folder: Image folder (e.g., "profiles", "listings")

    Returns:
        Dict with:
        - url: S3 POST URL
        - fields: Form fields for upload
        - key: S3 object key
        - public_url: URL where file will be accessible after upload

    Raises:
        HTTPException: If validation fails

    Example:
        >>> result = await generate_image_upload_url(
        ...     filename="avatar.jpg",
        ...     content_type="image/jpeg",
        ...     folder="profiles"
        ... )
        >>> # Client uploads to result['url'] with result['fields']
        >>> # File accessible at result['public_url']
    """
    # Validate image
    validate_image_file(content_type)

    # Generate unique S3 key
    key = generate_image_key(folder, filename)

    # Generate presigned POST
    presigned = generate_presigned_post(
        key=key,
        content_type=content_type,
        max_file_size=MAX_IMAGE_SIZE,
        expiration=3600  # 1 hour
    )

    # Get public URL (where file will be accessible after upload)
    public_url = get_public_url(key)

    return {
        "url": presigned["url"],
        "fields": presigned["fields"],
        "key": key,
        "public_url": public_url
    }


async def generate_document_upload_url(
    user_id: str,
    document_type: str,
    filename: str,
    content_type: str
) -> Dict[str, Any]:
    """
    Generate presigned URL for agent document upload.

    Args:
        user_id: User UUID
        document_type: "license" | "company" | "id"
        filename: Original filename
        content_type: MIME type

    Returns:
        Dict with:
        - url: S3 POST URL
        - fields: Form fields for upload
        - key: S3 object key
        - public_url: URL where file will be accessible after upload

    Raises:
        HTTPException: If validation fails
    """
    # Validate document
    validate_document_file(content_type)

    # Validate document type
    if document_type not in ["license", "company", "id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document type. Must be: license, company, or id"
        )

    # Generate unique S3 key
    key = generate_document_key(user_id, document_type, filename)

    # Generate presigned POST
    presigned = generate_presigned_post(
        key=key,
        content_type=content_type,
        max_file_size=MAX_DOCUMENT_SIZE,
        expiration=3600  # 1 hour
    )

    # Get public URL
    public_url = get_public_url(key)

    return {
        "url": presigned["url"],
        "fields": presigned["fields"],
        "key": key,
        "public_url": public_url
    }


# ============================================================================
# DIRECT FILE UPLOAD (SERVER-SIDE)
# ============================================================================

async def upload_image_direct(
    file: UploadFile,
    folder: str = "general"
) -> str:
    """
    Upload image directly from server to S3.

    Use this when server needs to process the file before upload
    (e.g., resize, compress, watermark).

    For most cases, prefer presigned URLs (client uploads directly).

    Args:
        file: FastAPI UploadFile object
        folder: Image folder (e.g., "profiles", "listings")

    Returns:
        Public URL of uploaded image

    Raises:
        HTTPException: If upload fails

    Example:
        >>> @app.post("/upload")
        >>> async def upload(file: UploadFile = File(...)):
        ...     url = await upload_image_direct(file, folder="profiles")
        ...     return {"url": url}
    """
    # Validate image
    validate_image_file(
        content_type=file.content_type,
        file_size=file.size if hasattr(file, 'size') else None
    )

    # Read file content
    content = await file.read()

    # Generate unique key
    key = generate_image_key(folder, file.filename)

    # Upload to S3
    try:
        url = upload_file(
            file_data=content,
            key=key,
            content_type=file.content_type,
            metadata={
                'original_filename': file.filename,
                'upload_type': 'image'
            }
        )

        logger.info(f"Image uploaded: {key}")
        return url

    except Exception as e:
        logger.error(f"Error uploading image: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload image. Please try again."
        )


async def upload_document_direct(
    file: UploadFile,
    user_id: str,
    document_type: str
) -> str:
    """
    Upload agent document directly from server to S3.

    Args:
        file: FastAPI UploadFile object
        user_id: User UUID
        document_type: "license" | "company" | "id"

    Returns:
        Public URL of uploaded document

    Raises:
        HTTPException: If upload fails
    """
    # Validate document
    validate_document_file(
        content_type=file.content_type,
        file_size=file.size if hasattr(file, 'size') else None
    )

    # Validate document type
    if document_type not in ["license", "company", "id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document type. Must be: license, company, or id"
        )

    # Read file content
    content = await file.read()

    # Generate unique key
    key = generate_document_key(user_id, document_type, file.filename)

    # Upload to S3
    try:
        url = upload_file(
            file_data=content,
            key=key,
            content_type=file.content_type,
            metadata={
                'user_id': user_id,
                'document_type': document_type,
                'original_filename': file.filename
            }
        )

        logger.info(f"Document uploaded: {key}")
        return url

    except Exception as e:
        logger.error(f"Error uploading document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload document. Please try again."
        )


# ============================================================================
# FILE DELETION
# ============================================================================

async def delete_old_image(image_url: str) -> bool:
    """
    Delete old image from S3.

    Use when user updates profile picture or listing images.

    Args:
        image_url: Full public URL of image

    Returns:
        True if deletion successful, False otherwise

    Example:
        >>> old_url = "https://bucket.s3.amazonaws.com/images/old_profile.jpg"
        >>> await delete_old_image(old_url)
        True
    """
    # Extract key from URL
    key = extract_key_from_url(image_url)

    if not key:
        logger.warning(f"Could not extract key from URL: {image_url}")
        return False

    # Delete file
    return delete_file(key)


async def delete_old_document(document_url: str) -> bool:
    """
    Delete old document from S3.

    Use when agent uploads new verification documents.

    Args:
        document_url: Full public URL of document

    Returns:
        True if deletion successful, False otherwise
    """
    # Extract key from URL
    key = extract_key_from_url(document_url)

    if not key:
        logger.warning(f"Could not extract key from URL: {document_url}")
        return False

    # Delete file
    return delete_file(key)


# ============================================================================
# UPLOAD SCHEMAS (for API routes)
# ============================================================================

class PresignedUrlRequest:
    """Request schema for presigned URL generation."""
    filename: str
    content_type: str
    folder: Optional[str] = "general"


class PresignedUrlResponse:
    """Response schema for presigned URL generation."""
    url: str
    fields: Dict[str, str]
    key: str
    public_url: str


class DirectUploadResponse:
    """Response schema for direct upload."""
    success: bool = True
    message: str = "File uploaded successfully"
    url: str
    key: str
