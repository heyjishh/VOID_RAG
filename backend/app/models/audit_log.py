"""Durable per-turn audit record — what JuryAI told a client, and why.

Compliance requirement: if a user is later shown to have relied on a
hallucinated or gate-blocked answer, this table is the only record of what
evidence was retrieved, what the model said, how the verifier scored it, and
whether the gate blocked or regenerated it.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_conversation_id", "conversation_id"),
        Index("ix_audit_log_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    verification: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    gate_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gate_regenerated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence_content_hashes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    model_provider: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    model_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    client_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    streaming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # True when this turn was served from the answer cache rather than the live
    # pipeline — evidence_content_hashes is then only the cited subset (no full
    # retrieval pool was available), which matters for anyone auditing later.
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
