"""AI Agent chat routes."""

import logging
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.api.deps import RoleChecker, verify_csrf_token
from app.models.user import User
from app.models.lead import SavedListing
from app.models.listing import Listing
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
    current_user: Annotated[User, Depends(RoleChecker(["buyer", "admin"]))],
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_csrf_token),
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

    # Set conversation title from first message (before incrementing count)
    if conversation.message_count == 0:
        title = body.message[:100]
        await chat_repo.update_conversation_title(db, str(conversation.id), title)

    # Save user message
    await chat_repo.add_message(db, str(conversation.id), "user", body.message)
    await chat_repo.increment_message_count(db, str(conversation.id))

    # Reload conversation with all messages for context
    conversation = await chat_repo.get_conversation(db, str(conversation.id), str(current_user.id))

    # Build user context for personalized recommendations
    user_context = {}
    country_name_map = {"al": "Albania", "ae": "United Arab Emirates"}
    if current_user.country_preference:
        user_context["country"] = country_name_map.get(
            current_user.country_preference, current_user.country_preference
        )

    # Fetch saved listing titles
    saved_result = await db.execute(
        select(Listing.public_title_en)
        .join(SavedListing, SavedListing.listing_id == Listing.id)
        .where(SavedListing.buyer_id == current_user.id)
        .limit(10)
    )
    saved_titles = [row[0] for row in saved_result.all() if row[0]]
    if saved_titles:
        user_context["saved_listings"] = saved_titles

    # Get AI response
    previous_messages = conversation.messages[:-1] if len(conversation.messages) > 1 else []

    response_text, tool_calls = await agent_service.chat(
        db=db,
        user_message=body.message,
        conversation_messages=previous_messages,
        language=conversation.language,
        user_context=user_context if user_context else None,
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
    current_user: Annotated[User, Depends(RoleChecker(["buyer", "admin"]))],
    db: AsyncSession = Depends(get_db),
):
    """List user's conversations."""
    conversations = await chat_repo.get_user_conversations(db, str(current_user.id))
    return [ConversationSchema.model_validate(c) for c in conversations]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailSchema)
async def get_conversation(
    conversation_id: str,
    current_user: Annotated[User, Depends(RoleChecker(["buyer", "admin"]))],
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
    current_user: Annotated[User, Depends(RoleChecker(["buyer", "admin"]))],
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_csrf_token),
):
    """Delete a conversation."""
    deleted = await chat_repo.delete_conversation(db, conversation_id, str(current_user.id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
