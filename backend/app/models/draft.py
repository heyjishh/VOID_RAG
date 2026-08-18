"""Draft feature's persisted output — one row per generated document.

Mirrors app.models.audit_log's role for chat: a durable record of what was
asked (brief) and what was produced (content), so a drafted document can be
listed and re-opened later. user_id is nullable because POST /draft has
never required auth (see tests/test_draft.py) — an anonymous draft is still
persisted, just without an owner to list it back to.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class DraftRun(Base):
    __tablename__ = "draft_run"
    __table_args__ = (
        Index("ix_draft_run_user_id", "user_id"),
        Index("ix_draft_run_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    document_type: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=True
    )
    brief: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
