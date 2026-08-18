from __future__ import annotations
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker
from app.core.models import Conversation, Turn

router = APIRouter()
logger = logging.getLogger("juryai.conversations")


class ConversationCreate(BaseModel):
    title: Optional[str] = None
    user_id: Optional[UUID] = None
    extra_data: dict = {}


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    extra_data: Optional[dict] = None


class ConversationOut(BaseModel):
    id: UUID
    title: Optional[str]
    user_id: Optional[UUID]
    created_at: str
    updated_at: str
    extra_data: dict
    turn_count: int = 0

    class Config:
        from_attributes = True


class TurnOut(BaseModel):
    id: UUID
    conversation_id: UUID
    turn_number: int
    question: str
    answer: Optional[str]
    intent: Optional[str]
    latency_ms: Optional[int]
    created_at: str

    class Config:
        from_attributes = True


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    user_id: Optional[UUID] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    async with get_sessionmaker()() as session:
        stmt = select(Conversation)
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        stmt = stmt.order_by(desc(Conversation.updated_at)).limit(limit).offset(offset)
        result = await session.execute(stmt)
        convs = result.scalars().all()

        # Get turn counts
        conv_ids = [c.id for c in convs]
        if conv_ids:
            count_stmt = (
                select(Turn.conversation_id, func.count(Turn.id).label("turn_count"))
                .where(Turn.conversation_id.in_(conv_ids))
                .group_by(Turn.conversation_id)
            )
            count_result = await session.execute(count_stmt)
            counts = {row[0]: row[1] for row in count_result.all()}
        else:
            counts = {}

        return [
            ConversationOut(
                id=c.id,
                title=c.title,
                user_id=c.user_id,
                created_at=c.created_at.isoformat() if c.created_at else "",
                updated_at=c.updated_at.isoformat() if c.updated_at else "",
                extra_data=c.extra_data or {},
                turn_count=counts.get(c.id, 0),
            )
            for c in convs
        ]


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(body: ConversationCreate):
    async with get_sessionmaker()() as session:
        conv = Conversation(
            title=body.title,
            user_id=body.user_id,
            extra_data=body.extra_data or {},
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        return ConversationOut(
            id=conv.id,
            title=conv.title,
            user_id=conv.user_id,
            created_at=conv.created_at.isoformat() if conv.created_at else "",
            updated_at=conv.updated_at.isoformat() if conv.updated_at else "",
            extra_data=conv.extra_data or {},
            turn_count=0,
        )


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(conversation_id: UUID):
    async with get_sessionmaker()() as session:
        conv = await session.get(Conversation, conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        count_stmt = select(func.count(Turn.id)).where(Turn.conversation_id == conversation_id)
        count_result = await session.execute(count_stmt)
        turn_count = count_result.scalar() or 0

        return ConversationOut(
            id=conv.id,
            title=conv.title,
            user_id=conv.user_id,
            created_at=conv.created_at.isoformat() if conv.created_at else "",
            updated_at=conv.updated_at.isoformat() if conv.updated_at else "",
            metadata=conv.metadata or {},
            turn_count=turn_count,
        )


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def update_conversation(conversation_id: UUID, body: ConversationUpdate):
    async with get_sessionmaker()() as session:
        conv = await session.get(Conversation, conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        if body.title is not None:
            conv.title = body.title
        if body.extra_data is not None:
            conv.extra_data = body.extra_data

        await session.commit()
        await session.refresh(conv)

        count_stmt = select(func.count(Turn.id)).where(Turn.conversation_id == conversation_id)
        count_result = await session.execute(count_stmt)
        turn_count = count_result.scalar() or 0

        return ConversationOut(
            id=conv.id,
            title=conv.title,
            user_id=conv.user_id,
            created_at=conv.created_at.isoformat() if conv.created_at else "",
            updated_at=conv.updated_at.isoformat() if conv.updated_at else "",
            extra_data=conv.extra_data or {},
            turn_count=turn_count,
        )


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: UUID):
    async with get_sessionmaker()() as session:
        conv = await session.get(Conversation, conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        await session.delete(conv)
        await session.commit()


@router.get("/conversations/{conversation_id}/turns", response_model=list[TurnOut])
async def list_turns(conversation_id: UUID, limit: int = Query(100, le=500), offset: int = Query(0, ge=0)):
    async with get_sessionmaker()() as session:
        conv = await session.get(Conversation, conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        stmt = (
            select(Turn)
            .where(Turn.conversation_id == conversation_id)
            .order_by(Turn.turn_number)
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(stmt)
        turns = result.scalars().all()

        return [
            TurnOut(
                id=t.id,
                conversation_id=t.conversation_id,
                turn_number=t.turn_number,
                question=t.question,
                answer=t.answer,
                intent=t.intent,
                latency_ms=t.latency_ms,
                created_at=t.created_at.isoformat() if t.created_at else "",
            )
            for t in turns
        ]
