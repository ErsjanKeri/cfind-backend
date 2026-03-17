"""
File upload service.

Handles:
- File validation (type, size)
- EXIF metadata stripping (privacy protection)
- Image uploads (profile pictures, listing images)
- Document uploads (agent verification documents)
- Direct server uploads to S3
"""

import asyncio
import io
import logging
from typing import Optional
from fastapi import UploadFile, HTTPException, status
from PIL import Image, ImageOps
from app.utils.s3_client import (
    upload_file,
    delete_file,
    generate_image_key,
    generate_document_key,
    extract_key_from_url
)

logger = logging.getLogger(__name__)


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

# MIME types that contain EXIF data and can be stripped
EXIF_STRIPPABLE_TYPES = [
    'image/jpeg',
    'image/jpg',
    'image/png',
    'image/webp',
]

# Pillow format mapping
CONTENT_TYPE_TO_PIL_FORMAT = {
    'image/jpeg': 'JPEG',
    'image/jpg': 'JPEG',
    'image/png': 'PNG',
    'image/webp': 'WEBP',
}

# File size limits (in bytes)
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_DOCUMENT_SIZE = 15 * 1024 * 1024  # 15 MB


def validate_image_file(
    content_type: str,
    file_size: Optional[int] = None
) -> None:
    """Validate image file type and size."""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image type. Allowed types: {', '.join(ALLOWED_IMAGE_TYPES)}"
        )

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
    """Validate document file type and size."""
    if content_type not in ALLOWED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document type. Allowed types: {', '.join(ALLOWED_DOCUMENT_TYPES)}"
        )

    if file_size and file_size > MAX_DOCUMENT_SIZE:
        max_mb = MAX_DOCUMENT_SIZE / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Document file too large. Maximum size: {max_mb} MB"
        )


def strip_exif(content: bytes, content_type: str) -> bytes:
    """
    Strip EXIF metadata from image bytes while preserving visual fidelity.

    - Applies EXIF orientation before stripping (prevents rotated photos)
    - Preserves ICC color profiles (prevents color shifts)
    - Removes GPS coordinates, camera info, timestamps, and all other EXIF data

    Returns original bytes unchanged for non-strippable types (GIF, PDF).
    """
    pil_format = CONTENT_TYPE_TO_PIL_FORMAT.get(content_type)
    if not pil_format:
        return content

    try:
        image = Image.open(io.BytesIO(content))

        # Apply EXIF orientation (rotate/flip) before stripping the tag,
        # otherwise phone photos will appear sideways
        image = ImageOps.exif_transpose(image)

        # Preserve ICC color profile if present
        icc_profile = image.info.get('icc_profile')

        # Re-encode without EXIF
        output = io.BytesIO()
        save_kwargs = {}
        if pil_format == 'JPEG':
            save_kwargs['quality'] = 95
        if pil_format == 'WEBP':
            save_kwargs['quality'] = 95
        if icc_profile:
            save_kwargs['icc_profile'] = icc_profile

        image.save(output, format=pil_format, **save_kwargs)
        stripped = output.getvalue()

        logger.info(f"Stripped EXIF metadata ({len(content)} -> {len(stripped)} bytes)")
        return stripped

    except Exception as e:
        logger.warning(f"Failed to strip EXIF, uploading original: {e}")
        return content


async def upload_image_direct(
    file: UploadFile,
    folder: str = "general"
) -> str:
    """
    Upload image directly from server to S3 with EXIF stripping.

    All EXIF metadata (GPS, camera info, timestamps) is removed before upload.

    Args:
        file: FastAPI UploadFile object
        folder: Image folder (e.g., "profiles", "listings")

    Returns:
        Public URL of uploaded image
    """
    validate_image_file(
        content_type=file.content_type,
        file_size=file.size if hasattr(file, 'size') else None
    )

    content = await file.read()

    # Strip EXIF metadata before uploading
    content = await asyncio.to_thread(strip_exif, content, file.content_type)

    key = generate_image_key(folder, file.filename)

    try:
        url = await asyncio.to_thread(
            upload_file,
            file_data=content,
            key=key,
            content_type=file.content_type,
            metadata={
                'original_filename': file.filename,
                'upload_type': 'image'
            },
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

    For image-based documents (JPEG, PNG), EXIF metadata is stripped.
    PDFs are uploaded as-is.

    Args:
        file: FastAPI UploadFile object
        user_id: User UUID
        document_type: "license" | "company" | "id"

    Returns:
        Public URL of uploaded document
    """
    validate_document_file(
        content_type=file.content_type,
        file_size=file.size if hasattr(file, 'size') else None
    )

    if document_type not in ["license", "company", "id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid document type. Must be: license, company, or id"
        )

    content = await file.read()

    # Strip EXIF from image-based documents (skip PDFs)
    if file.content_type in EXIF_STRIPPABLE_TYPES:
        content = await asyncio.to_thread(strip_exif, content, file.content_type)

    key = generate_document_key(user_id, document_type, file.filename)

    try:
        url = await asyncio.to_thread(
            upload_file,
            file_data=content,
            key=key,
            content_type=file.content_type,
            metadata={
                'user_id': user_id,
                'document_type': document_type,
                'original_filename': file.filename
            },
            acl="private",
        )

        logger.info(f"Document uploaded: {key}")
        return url

    except Exception as e:
        logger.error(f"Error uploading document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload document. Please try again."
        )


async def delete_old_image(image_url: str) -> bool:
    """Delete old image from S3 when user updates profile picture or listing images."""
    key = extract_key_from_url(image_url)

    if not key:
        logger.warning(f"Could not extract key from URL: {image_url}")
        return False

    return await asyncio.to_thread(delete_file, key)
