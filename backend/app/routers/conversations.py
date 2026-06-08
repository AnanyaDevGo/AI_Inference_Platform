from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies.auth import CurrentUser, get_current_user
from app.models.conversation import ChatMessage, Conversation
from app.utils.errors import NotFoundError, ForbiddenError

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/conversations", tags=["conversations"])


# ── Schemas ────────────────────────────────────────────────────────────────
class ConversationOut(BaseModel):
    id: str
    title: str
    model_name: str | None = None
    created_at: str
    updated_at: str
    message_count: int = 0


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    position: int


class ConversationDetailOut(BaseModel):
    id: str
    title: str
    model_name: str | None = None
    messages: list[MessageOut]


class CreateConversationReq(BaseModel):
    title: str = "New Chat"
    model_name: str | None = None


class SaveMessageReq(BaseModel):
    role: str
    content: str


class UpdateTitleReq(BaseModel):
    title: str


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    limit: int = 50,
    offset: int = 0,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all conversations for the current user, newest first."""
    stmt = (
        select(
            Conversation.id,
            Conversation.title,
            Conversation.model_name,
            Conversation.created_at,
            Conversation.updated_at,
            func.count(ChatMessage.id).label("message_count"),
        )
        .outerjoin(ChatMessage)
        .where(Conversation.user_id == uuid.UUID(user.user_id))
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return [
        ConversationOut(
            id=str(r.id),
            title=r.title,
            model_name=r.model_name,
            created_at=r.created_at.isoformat(),
            updated_at=r.updated_at.isoformat(),
            message_count=r.message_count,
        )
        for r in rows
    ]


@router.post("", response_model=ConversationDetailOut, status_code=201)
async def create_conversation(
    req: CreateConversationReq,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new empty conversation."""
    conv = Conversation(
        user_id=uuid.UUID(user.user_id),
        title=req.title,
        model_name=req.model_name,
    )
    db.add(conv)
    await db.flush()
    await db.refresh(conv)

    return ConversationDetailOut(
        id=str(conv.id),
        title=conv.title,
        model_name=conv.model_name,
        messages=[],
    )


@router.get("/{conv_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conv_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a conversation with all its messages."""
    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == uuid.UUID(conv_id))
    )
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise NotFoundError("Conversation not found")
        
    # Enforce strict ownership check
    if conv.user_id != uuid.UUID(user.user_id):
        raise ForbiddenError("You do not have access to this conversation")

    return ConversationDetailOut(
        id=str(conv.id),
        title=conv.title,
        model_name=conv.model_name,
        messages=[
            MessageOut(
                id=str(m.id),
                role=m.role,
                content=m.content,
                position=m.position,
            )
            for m in conv.messages
        ],
    )


@router.patch("/{conv_id}", response_model=ConversationOut)
async def update_conversation(
    conv_id: str,
    req: UpdateTitleReq,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update conversation details (e.g., title)."""
    stmt = select(Conversation).where(Conversation.id == uuid.UUID(conv_id))
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise NotFoundError("Conversation not found")
        
    # Enforce strict ownership check
    if conv.user_id != uuid.UUID(user.user_id):
        raise ForbiddenError("You do not have access to this conversation")

    conv.title = req.title
    conv.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(conv)

    # Count messages
    count_stmt = select(func.count(ChatMessage.id)).where(
        ChatMessage.conversation_id == conv.id
    )
    count_result = await db.execute(count_stmt)
    message_count = count_result.scalar() or 0

    return ConversationOut(
        id=str(conv.id),
        title=conv.title,
        model_name=conv.model_name,
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
        message_count=message_count,
    )


@router.delete("/{conv_id}", status_code=204)
async def delete_conversation(
    conv_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation and all its messages."""
    stmt = select(Conversation).where(Conversation.id == uuid.UUID(conv_id))
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise NotFoundError("Conversation not found")
        
    # Enforce strict ownership check
    if conv.user_id != uuid.UUID(user.user_id):
        raise ForbiddenError("You do not have access to this conversation")

    await db.delete(conv)


@router.post("/{conv_id}/messages", response_model=MessageOut, status_code=201)
async def save_message(
    conv_id: str,
    req: SaveMessageReq,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Append a message to a conversation."""
    # Verify ownership
    stmt = select(Conversation).where(Conversation.id == uuid.UUID(conv_id))
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise NotFoundError("Conversation not found")
        
    # Enforce strict ownership check
    if conv.user_id != uuid.UUID(user.user_id):
        raise ForbiddenError("You do not have access to this conversation")

    # Get next position
    count_stmt = select(func.count(ChatMessage.id)).where(
        ChatMessage.conversation_id == uuid.UUID(conv_id)
    )
    count_result = await db.execute(count_stmt)
    position = count_result.scalar() or 0

    msg = ChatMessage(
        conversation_id=uuid.UUID(conv_id),
        user_id=uuid.UUID(user.user_id),
        role=req.role,
        content=req.content,
        position=position,
    )
    db.add(msg)

    # Update conversation title from first user message
    if req.role == "user" and position == 0:
        title = req.content.strip()
        conv.title = title[:40] + "…" if len(title) > 40 else title

    # Touch updated_at
    conv.updated_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(msg)

    return MessageOut(
        id=str(msg.id),
        role=msg.role,
        content=msg.content,
        position=msg.position,
    )


@router.patch("/{conv_id}/messages/{msg_id}", response_model=MessageOut)
async def update_message(
    conv_id: str,
    msg_id: str,
    req: SaveMessageReq,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a message's content (used for streaming completion updates)."""
    # Verify ownership
    stmt = select(Conversation).where(Conversation.id == uuid.UUID(conv_id))
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise NotFoundError("Conversation not found")
        
    # Enforce strict ownership check
    if conv.user_id != uuid.UUID(user.user_id):
        raise ForbiddenError("You do not have access to this conversation")

    msg_stmt = select(ChatMessage).where(
        ChatMessage.id == uuid.UUID(msg_id),
        ChatMessage.conversation_id == uuid.UUID(conv_id),
    )
    msg_result = await db.execute(msg_stmt)
    msg = msg_result.scalar_one_or_none()
    if not msg:
        raise NotFoundError("Message not found")

    msg.content = req.content
    conv.updated_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(msg)

    return MessageOut(
        id=str(msg.id),
        role=msg.role,
        content=msg.content,
        position=msg.position,
    )


@router.delete("/{conv_id}/messages/{msg_id}", status_code=204)
async def delete_messages_from(
    conv_id: str,
    msg_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a message and all subsequent messages in the conversation."""
    # Verify ownership
    stmt = select(Conversation).where(Conversation.id == uuid.UUID(conv_id))
    result = await db.execute(stmt)
    conv = result.scalar_one_or_none()
    if not conv:
        raise NotFoundError("Conversation not found")
        
    # Enforce strict ownership check
    if conv.user_id != uuid.UUID(user.user_id):
        raise ForbiddenError("You do not have access to this conversation")

    msg_stmt = select(ChatMessage).where(
        ChatMessage.id == uuid.UUID(msg_id),
        ChatMessage.conversation_id == uuid.UUID(conv_id),
    )
    msg_result = await db.execute(msg_stmt)
    msg = msg_result.scalar_one_or_none()
    if not msg:
        raise NotFoundError("Message not found")

    # Delete all messages in this conversation with position >= msg.position
    delete_stmt = delete(ChatMessage).where(
        ChatMessage.conversation_id == uuid.UUID(conv_id),
        ChatMessage.position >= msg.position,
    )
    await db.execute(delete_stmt)
    
    # Touch updated_at
    conv.updated_at = datetime.now(timezone.utc)
    await db.flush()
