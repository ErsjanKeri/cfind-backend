"""Pydantic schemas for file upload operations."""

from app.schemas.base import BaseSchema


class DirectUploadResponse(BaseSchema):
    """Response for direct server-side uploads."""

    success: bool = True
    message: str = "File uploaded successfully"
    url: str
