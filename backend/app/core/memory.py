"""Valkey-backed conversation memory.

Stores the trailing turns of a conversation keyed by ``conversation_id`` so the
answer prompt can carry multi-turn context. Best-effort: a down Valkey degrades
to an empty history (single-turn behaviour) and never raises into the request
path. Shares the process-wide client + breaker in ``app.core.valkey``.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from app.config.settings import settings
from app.core import valkey

logger = logging.getLogger("juryai.memory")

_KEY_PREFIX = "juryai:conv"


def _key(conversation_id: str) -> str:
    return f"{_KEY_PREFIX}:{conversation_id}"


async def load_history(conversation_id: Optional[str]) -> list[dict]:
    """Return the stored turns (oldest-first) for a conversation, capped.

    Returns [] on miss, disabled, or any failure.
    """
    if (
        not settings.CONVERSATION_MEMORY_ENABLED
        or not conversation_id
        or valkey.breaker_open()
    ):
        return []
    client = valkey.get_client()
    if client is None:
        return []
    try:
        # Keep only the last N*2 messages (N user + N assistant).
        raw = await client.lrange(_key(conversation_id), -settings.CONVERSATION_MAX_TURNS * 2, -1)
        history: list[dict] = []
        for item in raw or []:
            try:
                msg = json.loads(item)
                if isinstance(msg, dict) and msg.get("role") and msg.get("content"):
                    history.append(msg)
            except (json.JSONDecodeError, TypeError):
                continue
        return history
    except Exception as exc:  # noqa: BLE001 — empty history on any failure
        logger.warning("conversation load failed; opening breaker: %s", exc)
        valkey.trip_breaker()
        return []


async def append_turn(
    conversation_id: Optional[str], question: str, answer: str
) -> None:
    """Append a (user, assistant) turn to the conversation. Best-effort."""
    if (
        not settings.CONVERSATION_MEMORY_ENABLED
        or not conversation_id
        or not answer
        or valkey.breaker_open()
    ):
        return
    client = valkey.get_client()
    if client is None:
        return
    try:
        key = _key(conversation_id)
        await client.rpush(
            key,
            json.dumps({"role": "user", "content": question}),
            json.dumps({"role": "assistant", "content": answer}),
        )
        # Trim to the last N turns and refresh TTL so idle conversations expire.
        await client.ltrim(key, -settings.CONVERSATION_MAX_TURNS * 2, -1)
        await client.expire(key, settings.CONVERSATION_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 — never break the request path
        logger.warning("conversation append failed; opening breaker: %s", exc)
        valkey.trip_breaker()


def format_history(history: list[dict]) -> str:
    """Render history for the answer prompt. Returns '(none)' when empty."""
    if not history:
        return "(none)"
    lines = []
    for msg in history:
        role = "User" if msg.get("role") == "user" else "Assistant"
        lines.append(f"{role}: {msg.get('content', '')}")
    return "\n".join(lines)
