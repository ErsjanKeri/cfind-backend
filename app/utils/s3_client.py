"""
S3 client wrapper for AWS S3 and DigitalOcean Spaces.

Provides:
- Presigned URL generation for direct client-side upload
- Direct file upload from server
- File deletion
- URL generation

Supports both:
- AWS S3 (when AWS_ENDPOINT is not set)
- DigitalOcean Spaces (when AWS_ENDPOINT is set)
"""

import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from app.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# S3 CLIENT INITIALIZATION
# ============================================================================

_s3_client = None


def get_s3_client():
    """
    Get boto3 S3 client configured for AWS S3 or DigitalOcean Spaces.
    Returns a cached singleton instance.
    """
    global _s3_client
    if _s3_client is not None:
        return _s3_client

    config = Config(
        signature_version='s3v4',
        s3={'addressing_style': 'virtual'}
    )

    client_kwargs = {
        'service_name': 's3',
        'region_name': settings.AWS_REGION,
        'aws_access_key_id': settings.AWS_ACCESS_KEY_ID,
        'aws_secret_access_key': settings.AWS_SECRET_ACCESS_KEY,
        'config': config
    }

    if settings.AWS_ENDPOINT:
        client_kwargs['endpoint_url'] = settings.AWS_ENDPOINT

    _s3_client = boto3.client(**client_kwargs)
    return _s3_client


# ============================================================================
# PRESIGNED URL GENERATION
# ============================================================================

def generate_presigned_post(
    key: str,
    content_type: str,
    max_file_size: int = 10 * 1024 * 1024,  # 10 MB default
    expiration: int = 3600,  # 1 hour default
    acl: str = "public-read"
) -> Dict[str, Any]:
    """
    Generate presigned POST URL for direct client-side upload to S3.

    This allows clients to upload files directly to S3/Spaces without
    going through the server, reducing server load and bandwidth.

    Args:
        key: S3 object key (file path in bucket)
        content_type: MIME type (e.g., "image/jpeg", "application/pdf")
        max_file_size: Maximum file size in bytes (default: 10 MB)
        expiration: URL expiration in seconds (default: 1 hour)

    Returns:
        Dict containing:
        - url: POST URL
        - fields: Form fields to include in POST request

    Example:
        >>> presigned = generate_presigned_post(
        ...     key="documents/license_123.pdf",
        ...     content_type="application/pdf",
        ...     max_file_size=5 * 1024 * 1024  # 5 MB
        ... )
        >>> # Client uploads with:
        >>> # POST presigned['url']
        >>> # with fields: presigned['fields']
    """
    s3 = get_s3_client()

    try:
        # Generate presigned POST
        response = s3.generate_presigned_post(
            Bucket=settings.AWS_BUCKET_NAME,
            Key=key,
            Fields={
                'Content-Type': content_type,
                'acl': acl,
            },
            Conditions=[
                {'Content-Type': content_type},
                {'acl': acl},
                ['content-length-range', 0, max_file_size]  # File size limit
            ],
            ExpiresIn=expiration
        )

        logger.info(f"Generated presigned POST for key: {key}")
        return response

    except ClientError as e:
        logger.error(f"Error generating presigned POST: {str(e)}")
        raise


def generate_presigned_get(
    key: str,
    expiration: int = 3600
) -> str:
    """
    Generate presigned GET URL for temporary access to private files.

    Args:
        key: S3 object key (file path in bucket)
        expiration: URL expiration in seconds (default: 1 hour)

    Returns:
        Presigned GET URL

    Example:
        >>> url = generate_presigned_get("private/document_123.pdf")
        >>> # Client can access file at this URL for 1 hour
    """
    s3 = get_s3_client()

    try:
        url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.AWS_BUCKET_NAME,
                'Key': key
            },
            ExpiresIn=expiration
        )

        logger.info(f"Generated presigned GET for key: {key}")
        return url

    except ClientError as e:
        logger.error(f"Error generating presigned GET: {str(e)}")
        raise


# ============================================================================
# DIRECT FILE UPLOAD
# ============================================================================

def upload_file(
    file_data: bytes,
    key: str,
    content_type: str,
    metadata: Optional[Dict[str, str]] = None,
    acl: str = "public-read"
) -> str:
    """
    Upload file directly to S3 from server.

    Use this for server-side uploads (e.g., processed images, generated files).
    For client uploads, prefer presigned POST URLs.

    Args:
        file_data: File content as bytes
        key: S3 object key (file path in bucket)
        content_type: MIME type (e.g., "image/jpeg")
        metadata: Optional metadata dict

    Returns:
        Public URL of uploaded file

    Raises:
        ClientError: If upload fails

    Example:
        >>> with open("image.jpg", "rb") as f:
        ...     file_data = f.read()
        >>> url = upload_file(
        ...     file_data=file_data,
        ...     key="images/profile_123.jpg",
        ...     content_type="image/jpeg",
        ...     metadata={"user_id": "123", "type": "profile"}
        ... )
    """
    s3 = get_s3_client()

    try:
        # Prepare upload parameters
        upload_params = {
            'Bucket': settings.AWS_BUCKET_NAME,
            'Key': key,
            'Body': file_data,
            'ContentType': content_type,
            'ACL': acl
        }

        # Add metadata if provided
        if metadata:
            upload_params['Metadata'] = metadata

        # Upload file
        s3.put_object(**upload_params)

        # Generate public URL
        url = get_public_url(key)

        logger.info(f"Uploaded file to S3: {key}")
        return url

    except ClientError as e:
        logger.error(f"Error uploading file to S3: {str(e)}")
        raise


# ============================================================================
# FILE DELETION
# ============================================================================

def delete_file(key: str) -> bool:
    """
    Delete file from S3.

    Args:
        key: S3 object key (file path in bucket)

    Returns:
        True if deletion successful, False otherwise

    Example:
        >>> delete_file("images/old_profile_123.jpg")
        True
    """
    s3 = get_s3_client()

    try:
        s3.delete_object(
            Bucket=settings.AWS_BUCKET_NAME,
            Key=key
        )

        logger.info(f"Deleted file from S3: {key}")
        return True

    except ClientError as e:
        logger.error(f"Error deleting file from S3: {str(e)}")
        return False


# ============================================================================
# URL GENERATION
# ============================================================================

def get_public_url(key: str) -> str:
    """
    Get public URL for an S3 object.

    Args:
        key: S3 object key (file path in bucket)

    Returns:
        Public URL

    Example:
        >>> url = get_public_url("images/profile_123.jpg")
        >>> # https://bucket-name.s3.amazonaws.com/images/profile_123.jpg
    """
    if settings.AWS_ENDPOINT:
        # DigitalOcean Spaces or custom endpoint
        # Format: https://{bucket}.{region}.digitaloceanspaces.com/{key}
        endpoint_base = settings.AWS_ENDPOINT.replace('https://', '')
        return f"https://{settings.AWS_BUCKET_NAME}.{endpoint_base}/{key}"
    else:
        # AWS S3
        # Format: https://{bucket}.s3.{region}.amazonaws.com/{key}
        return f"https://{settings.AWS_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"


def extract_key_from_url(url: str) -> Optional[str]:
    """
    Extract S3 object key from public URL.

    Args:
        url: Full S3 public URL

    Returns:
        Object key (path) or None if URL is invalid

    Example:
        >>> url = "https://bucket.s3.amazonaws.com/images/profile.jpg"
        >>> extract_key_from_url(url)
        'images/profile.jpg'
    """
    try:
        # Remove protocol
        url = url.replace('https://', '').replace('http://', '')

        # Split by first slash to separate domain and key
        parts = url.split('/', 1)
        if len(parts) == 2:
            return parts[1]

        return None

    except Exception as e:
        logger.error(f"Error extracting key from URL: {str(e)}")
        return None


# ============================================================================
# KEY GENERATION HELPERS
# ============================================================================

def generate_unique_key(
    folder: str,
    filename: str,
    preserve_extension: bool = True
) -> str:
    """
    Generate unique S3 key with timestamp and UUID.

    Args:
        folder: Folder path (e.g., "images", "documents/licenses")
        filename: Original filename
        preserve_extension: Keep original file extension

    Returns:
        Unique S3 key

    Example:
        >>> generate_unique_key("images", "profile.jpg")
        'images/20240115_abc123def_profile.jpg'
    """
    # Generate timestamp
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')

    # Generate short UUID
    unique_id = str(uuid.uuid4())[:8]

    # Extract extension if needed
    if preserve_extension and '.' in filename:
        name, ext = filename.rsplit('.', 1)
        # Sanitize filename (remove special chars)
        name = ''.join(c for c in name if c.isalnum() or c in '-_')
        return f"{folder}/{timestamp}_{unique_id}_{name}.{ext}"
    else:
        # Sanitize filename
        name = ''.join(c for c in filename if c.isalnum() or c in '-_')
        return f"{folder}/{timestamp}_{unique_id}_{name}"


def generate_document_key(
    user_id: str,
    document_type: str,
    filename: str
) -> str:
    """
    Generate S3 key for agent document uploads.

    Args:
        user_id: User UUID
        document_type: "license" | "company" | "id"
        filename: Original filename

    Returns:
        S3 key for document

    Example:
        >>> generate_document_key("123e4567-e89b", "license", "license.pdf")
        'documents/agents/123e4567-e89b/license_20240115_abc123.pdf'
    """
    # Extract extension
    ext = filename.rsplit('.', 1)[1] if '.' in filename else 'pdf'

    # Generate timestamp and short UUID
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid.uuid4())[:8]

    return f"documents/agents/{user_id}/{document_type}_{timestamp}_{unique_id}.{ext}"


def generate_image_key(
    folder: str,
    filename: str
) -> str:
    """
    Generate S3 key for image uploads.

    Args:
        folder: Image folder (e.g., "profiles", "listings")
        filename: Original filename

    Returns:
        S3 key for image

    Example:
        >>> generate_image_key("profiles", "avatar.jpg")
        'images/profiles/20240115_abc123_avatar.jpg'
    """
    return generate_unique_key(f"images/{folder}", filename, preserve_extension=True)
