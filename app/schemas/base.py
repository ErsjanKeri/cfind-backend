"""
Base Pydantic schemas with automatic UUID serialization.

All response schemas should inherit from BaseSchema to ensure
UUID fields are automatically converted to strings for JSON serialization.
"""

from pydantic import BaseModel, model_validator
from uuid import UUID
from typing import Any


class BaseSchema(BaseModel):
    """
    Base schema with automatic UUID → string conversion.

    Handles both dict input and ORM object input (from_attributes).
    """

    @model_validator(mode='before')
    @classmethod
    def convert_uuids_to_strings(cls, data: Any) -> Any:
        """
        Convert all UUID objects to strings before validation.

        Handles two cases:
        1. Dict input: Convert UUID values in dict
        2. Object input (from_attributes): Extract attributes and convert UUIDs
        """
        # Case 1: Dict input
        if isinstance(data, dict):
            return {
                key: str(value) if isinstance(value, UUID) else value
                for key, value in data.items()
            }

        # Case 2: Object input (from_attributes=True)
        # Extract all attributes and convert UUIDs
        if hasattr(data, '__dict__'):
            result = {}
            for key in cls.model_fields.keys():
                if hasattr(data, key):
                    value = getattr(data, key)
                    result[key] = str(value) if isinstance(value, UUID) else value
            return result

        return data

    model_config = {
        "from_attributes": True,  # Enable ORM mode (Pydantic v2)
    }
