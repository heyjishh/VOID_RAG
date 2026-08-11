"""Durable audit-log writer — records every chat turn for compliance.

Unlike the Valkey-backed cache/ratelimit/memory modules, which are best-effort
because losing a cache hit or a rate-limit counter is harmless, a compliance
audit record silently failing to write is NOT harmless. Writes here retry with
exponential backoff on transient DB errors and log loudly on final failure —
but never raise into the request path, so a briefly-down audit DB never breaks
the user-facing chat response.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.config.settings import settings
from app.core.db import get_sessionmaker
from app.models.audit_log import AuditLog

logger = logging.getLogger("juryai.audit")


@dataclass
class TurnRecord:
    conversation_id: str
    question: str
    answer: str
    citations: list[dict]
    verification: dict
    evidence_content_hashes: list[str]
    model_provider: str
    model_name: str
    client_id: str
    streaming: bool
    gate_blocked: bool = False
    gate_regenerated: bool = False
    cache_hit: bool = False


def build_turn_record(
    *,
    conversation_id: str,
    question: str,
    answer: str,
    citations: list[dict],
    verification: dict,
    evidence: list[dict],
    model_provider: str,
    model_name: str,
    client_id: str,
    streaming: bool,
    cache_hit: bool = False,
) -> TurnRecord:
    """Shared "what to log" construction — both chat endpoints converge here
    once they have the final, post-gate answer/citations/verification.

    On a cache hit there is no retrieved evidence pool to pass as ``evidence``
    — only the cached ``citations``, which is a subset (whatever got cited).
    Callers pass the cached citations as ``evidence`` in that case; both shapes
    carry a ``content_hash`` key, so the extraction below works unchanged and
    ``evidence_content_hashes`` on a cache-hit row is honestly partial rather
    than empty.
    """
    return TurnRecord(
        conversation_id=conversation_id,
        question=question,
        answer=answer,
        citations=citations,
        verification=verification,
        gate_blocked=bool(verification.get("blocked", False)),
        gate_regenerated=bool(verification.get("regenerated", False)),
        evidence_content_hashes=sorted(
            {item.get("content_hash") for item in evidence if item.get("content_hash")}
        ),
        model_provider=model_provider,
        model_name=model_name,
        client_id=client_id,
        streaming=streaming,
        cache_hit=cache_hit,
    )


async def _write_once(record: TurnRecord) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        session.add(
            AuditLog(
                conversation_id=record.conversation_id,
                question=record.question,
                answer=record.answer,
                citations=record.citations,
                verification=record.verification,
                gate_blocked=record.gate_blocked,
                gate_regenerated=record.gate_regenerated,
                evidence_content_hashes=record.evidence_content_hashes,
                model_provider=record.model_provider,
                model_name=record.model_name,
                client_id=record.client_id,
                streaming=record.streaming,
                cache_hit=record.cache_hit,
            )
        )
        await asyncio.wait_for(session.commit(), timeout=settings.AUDIT_LOG_WRITE_TIMEOUT_SECONDS)


async def record_turn(record: TurnRecord) -> None:
    """Persist one Q&A turn with retry-with-backoff. Never raises.

    A small number of attempts with exponential backoff is enough to ride out
    a transient DB blip; a manual loop is used rather than pulling in a retry
    library since none is already a dependency.
    """
    if not settings.AUDIT_LOG_ENABLED:
        return
    attempts = max(1, settings.AUDIT_LOG_MAX_ATTEMPTS)
    for attempt in range(1, attempts + 1):
        try:
            await _write_once(record)
            return
        except Exception as exc:  # noqa: BLE001 — retry transient errors, never break chat
            if attempt == attempts:
                logger.error(
                    "audit log write failed after %d attempt(s) for conversation_id=%s: %s",
                    attempts,
                    record.conversation_id,
                    exc,
                )
                return
            backoff = settings.AUDIT_LOG_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "audit log write attempt %d/%d failed (retrying in %.2fs) for "
                "conversation_id=%s: %s",
                attempt,
                attempts,
                backoff,
                record.conversation_id,
                exc,
            )
            await asyncio.sleep(backoff)


def _log_task_exception(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:  # record_turn already swallows its own errors; this is a backstop
        logger.error("unexpected error in background audit task: %s", exc)


def schedule_record_turn(record: TurnRecord) -> None:
    """Fire-and-forget scheduling so audit persistence never adds request/SSE latency."""
    if not settings.AUDIT_LOG_ENABLED:
        return
    task = asyncio.create_task(record_turn(record))
    task.add_done_callback(_log_task_exception)
