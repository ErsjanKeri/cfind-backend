"""Pydantic schemas for AI agent chat."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.schemas.base import BaseSchema


class ChatMessageRequest(BaseModel):
    """Send a message to the AI agent."""
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[str] = None  # None = new conversation
    language: str = Field(default="en", max_length=10)
    mode: str = Field(default="buyer", pattern="^(buyer|agent)$")


class ChatMessageResponse(BaseSchema):
    """Agent response to a chat message."""
    conversation_id: str
    message_id: str
    content: str
    tool_calls: Optional[list] = None


class MessageSchema(BaseSchema):
    """Single message in a conversation."""
    id: str
    role: str
    content: str
    tool_calls: Optional[list] = None
    created_at: datetime


class ConversationSchema(BaseSchema):
    """Conversation summary."""
    id: str
    title: Optional[str] = None
    language: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class ConversationDetailSchema(ConversationSchema):
    """Conversation with messages."""
    messages: list[MessageSchema] = []
