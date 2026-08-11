"""Async SQLAlchemy engine/session for the Postgres-backed audit log.

Lazily constructed, cached singletons — mirrors ``app.core.valkey``'s
``get_client()`` and ``app.core.llm.provider``'s ``get_llm()`` idiom, since this
is the second durable-store dependency in the codebase.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config.settings import settings

logger = logging.getLogger("juryai.db")


class Base(DeclarativeBase):
    metadata = MetaData(
        schema=None if settings.POSTGRES_SCHEMA == "public" else settings.POSTGRES_SCHEMA
    )


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    connect_args = (
        {"server_settings": {"search_path": settings.POSTGRES_SCHEMA}}
        if settings.POSTGRES_SCHEMA != "public"
        else {}
    )
    return create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def ping() -> bool:
    """Lightweight connectivity check for startup. Never raises — logs and returns False."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 — startup check must never crash the app
        logger.warning("Postgres unreachable at startup: %s", exc)
        return False
