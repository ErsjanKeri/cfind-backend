"""AI Agent chat routes."""

import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.deps import get_verified_user
from app.models.user import User
from app.config import settings
from app.repositories import chat_repo
from app.services import agent_service
from app.schemas.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    ConversationSchema,
    ConversationDetailSchema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat")


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    body: ChatMessageRequest,
    current_user: Annotated[User, Depends(get_verified_user)],
    db: AsyncSession = Depends(get_db),
):
    """Send a message to the AI agent and get a response."""
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="AI agent is not configured")

    # Check daily message limit
    today_count = await chat_repo.count_user_messages_today(db, str(current_user.id))
    if today_count >= settings.AGENT_MAX_MESSAGES_PER_DAY:
        raise HTTPException(
            status_code=429,
            detail=f"Daily message limit reached ({settings.AGENT_MAX_MESSAGES_PER_DAY}). Try again tomorrow.",
        )

    # Get or create conversation
    conversation = None
    if body.conversation_id:
        conversation = await chat_repo.get_conversation(db, body.conversation_id, str(current_user.id))
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

    if not conversation:
        conversation = await chat_repo.create_conversation(
            db, str(current_user.id), language=body.language,
        )

    # Save user message
    await chat_repo.add_message(db, str(conversation.id), "user", body.message)
    await chat_repo.increment_message_count(db, str(conversation.id))

    # Set conversation title from first message
    if conversation.message_count == 0:
        title = body.message[:100]
        await chat_repo.update_conversation_title(db, str(conversation.id), title)

    # Reload conversation with all messages for context
    conversation = await chat_repo.get_conversation(db, str(conversation.id), str(current_user.id))

    # Get AI response (pass all previous messages except the last user message for history)
    previous_messages = conversation.messages[:-1] if len(conversation.messages) > 1 else []

    response_text, tool_calls = await agent_service.chat(
        db=db,
        user_message=body.message,
        conversation_messages=previous_messages,
        language=conversation.language,
    )

    # Save model response
    model_message = await chat_repo.add_message(
        db, str(conversation.id), "model", response_text, tool_calls=tool_calls,
    )
    await chat_repo.increment_message_count(db, str(conversation.id))

    return ChatMessageResponse(
        conversation_id=str(conversation.id),
        message_id=str(model_message.id),
        content=response_text,
        tool_calls=tool_calls,
    )


@router.get("/conversations", response_model=list[ConversationSchema])
async def list_conversations(
    current_user: Annotated[User, Depends(get_verified_user)],
    db: AsyncSession = Depends(get_db),
):
    """List user's conversations."""
    conversations = await chat_repo.get_user_conversations(db, str(current_user.id))
    return [ConversationSchema.model_validate(c) for c in conversations]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailSchema)
async def get_conversation(
    conversation_id: str,
    current_user: Annotated[User, Depends(get_verified_user)],
    db: AsyncSession = Depends(get_db),
):
    """Get a conversation with all messages."""
    conversation = await chat_repo.get_conversation(db, conversation_id, str(current_user.id))
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationDetailSchema.model_validate(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    current_user: Annotated[User, Depends(get_verified_user)],
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation."""
    deleted = await chat_repo.delete_conversation(db, conversation_id, str(current_user.id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
