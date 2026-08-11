"""Valkey-backed answer cache.

Best-effort by design: every operation degrades to a cache miss on any error
(Valkey down, timeout, malformed payload) and NEVER propagates an exception into
the request path. Shares the process-wide client + circuit breaker in
``app.core.valkey``.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

from app.config.settings import settings
from app.core import valkey

logger = logging.getLogger("juryai.cache")

_KEY_PREFIX = "juryai:answer"


def _make_key(question: str, use_web_search: bool, scope: str) -> str:
    """Deterministic cache key from a normalized question + flags.

    ponytail: exact-normalized match (case/whitespace-insensitive). Add an
    embedding-keyed semantic cache when near-duplicate phrasings must also hit —
    bigger latency win, but needs the embedder in the hot path.
    """
    norm = " ".join((question or "").strip().lower().split())
    raw = f"{norm}|web={int(bool(use_web_search))}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{_KEY_PREFIX}:{scope}:{digest}"


async def answer_cache_get(
    question: str, use_web_search: bool, scope: str = "chat"
) -> Optional[dict]:
    """Return a cached answer payload, or None on miss/unavailable."""
    if not settings.ANSWER_CACHE_ENABLED or valkey.breaker_open():
        return None
    client = valkey.get_client()
    if client is None:
        return None
    try:
        raw = await client.get(_make_key(question, use_web_search, scope))
        return json.loads(raw) if raw else None
    except Exception as exc:  # noqa: BLE001 — miss on any failure
        logger.warning("answer cache get failed; opening breaker: %s", exc)
        valkey.trip_breaker()
        return None


async def answer_cache_set(
    question: str, use_web_search: bool, payload: dict, scope: str = "chat"
) -> None:
    """Store an answer payload with the configured TTL. Best-effort."""
    if not settings.ANSWER_CACHE_ENABLED or valkey.breaker_open():
        return
    client = valkey.get_client()
    if client is None:
        return
    try:
        await client.set(
            _make_key(question, use_web_search, scope),
            json.dumps(payload, default=str),
            ex=settings.CACHE_TTL_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 — never break the request path
        logger.warning("answer cache set failed; opening breaker: %s", exc)
        valkey.trip_breaker()


_DOCUMENT_INDEX_KEY = "juryai:docindex"


async def document_index_get() -> Optional[dict]:
    """Return the cached basename -> {key, bucket} document index, or None on
    miss/unavailable."""
    if valkey.breaker_open():
        return None
    client = valkey.get_client()
    if client is None:
        return None
    try:
        raw = await client.get(_DOCUMENT_INDEX_KEY)
        return json.loads(raw) if raw else None
    except Exception as exc:  # noqa: BLE001 — miss on any failure
        logger.warning("document index cache get failed; opening breaker: %s", exc)
        valkey.trip_breaker()
        return None


async def document_index_set(index: dict) -> None:
    """Store the basename -> {key, bucket} document index. Best-effort."""
    if valkey.breaker_open():
        return
    client = valkey.get_client()
    if client is None:
        return
    try:
        await client.set(
            _DOCUMENT_INDEX_KEY,
            json.dumps(index, default=str),
            ex=settings.DOCUMENT_INDEX_CACHE_TTL_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 — never break the request path
        logger.warning("document index cache set failed; opening breaker: %s", exc)
        valkey.trip_breaker()
