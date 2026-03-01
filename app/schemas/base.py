"""Base Pydantic schema for all response models."""

from uuid import UUID
from pydantic import BaseModel, model_validator


class BaseSchema(BaseModel):
    """Base schema with ORM mode and UUID→str coercion. All response schemas inherit from this."""

    model_config = {
        "from_attributes": True,
    }

    @model_validator(mode="before")
    @classmethod
    def _coerce_uuids(cls, data):
        """Convert UUID values to strings when loading from ORM objects or dicts."""
        if not isinstance(data, dict):
            # ORM object — extract schema fields, coerce UUIDs
            obj = data
            data = {}
            for field in cls.model_fields:
                try:
                    data[field] = getattr(obj, field, None)
                except Exception:
                    pass
        return {
            k: str(v) if isinstance(v, UUID) else v
            for k, v in data.items()
        }
