"""Chat repository - database operations for conversations and messages."""

import logging
from typing import Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload
from app.models.conversation import Conversation, Message

logger = logging.getLogger(__name__)


async def create_conversation(
    db: AsyncSession,
    user_id: str,
    language: str = "en",
) -> Conversation:
    conversation = Conversation(user_id=user_id, language=language)
    db.add(conversation)
    await db.flush()
    return conversation


async def get_conversation(
    db: AsyncSession,
    conversation_id: str,
    user_id: str,
) -> Optional[Conversation]:
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_user_conversations(
    db: AsyncSession,
    user_id: str,
    limit: int = 20,
) -> list[Conversation]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def add_message(
    db: AsyncSession,
    conversation_id: str,
    role: str,
    content: str,
    tool_calls: Optional[list] = None,
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        tool_calls=tool_calls,
    )
    db.add(message)
    await db.flush()
    return message


async def increment_message_count(db: AsyncSession, conversation_id: str):
    conversation = await db.get(Conversation, conversation_id)
    if conversation:
        conversation.message_count += 1


async def update_conversation_title(db: AsyncSession, conversation_id: str, title: str):
    conversation = await db.get(Conversation, conversation_id)
    if conversation and not conversation.title:
        conversation.title = title[:100]


async def count_user_messages_today(db: AsyncSession, user_id: str) -> int:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.user_id == user_id,
            Message.role == "user",
            Message.created_at >= today_start,
        )
    )
    return result.scalar() or 0


async def delete_conversation(db: AsyncSession, conversation_id: str, user_id: str) -> bool:
    result = await db.execute(
        delete(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    return result.rowcount > 0
