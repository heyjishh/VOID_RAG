from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class LegalChunk(Base):
    """Postgres mirror of the main legal corpus already stored in Qdrant
    (vectors) and Quickwit (BM25) — SpiceAI has no Qdrant connector, so this
    is what its `juryai_legal` dataset actually queries for SQL/NQL search
    and (via the DuckDB vector engine) its own semantic search.

    `id` is the same content-addressed uuid5(source|page|text) Qdrant and
    Quickwit already compute, so a chunk's identity agrees across all three
    stores instead of each inventing its own."""
    __tablename__ = "legal_chunks"
    __table_args__ = (
        Index("ix_legal_chunks_source", "source"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(512), nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
