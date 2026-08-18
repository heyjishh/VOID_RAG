"""Valkey-backed run storage.

Persists completed research runs so the frontend can load a run page at
``/ask/run/{run_id}/`` and replay the answer, citations, sources, and
follow-up questions. Best-effort: a down Valkey degrades to an in-memory
fallback for the current process and never raises into the request path.
Shares the process-wide client + breaker in ``app.core.valkey``.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from app.config.settings import settings
from app.core import valkey

logger = logging.getLogger("juryai.run_store")

_RUN_KEY_PREFIX = "juryai:run"
_CONV_RUNS_PREFIX = "juryai:conv:runs"
_RUN_TTL_SECONDS = getattr(settings, "RUN_TTL_SECONDS", 604800)
_RUN_STORAGE_ENABLED = getattr(settings, "RUN_STORAGE_ENABLED", True)

_in_memory_runs: dict[str, dict[str, Any]] = {}
_in_memory_conv_index: dict[str, list[str]] = {}


def _enabled() -> bool:
    return _RUN_STORAGE_ENABLED


def _run_key(run_id: str) -> str:
    return f"{_RUN_KEY_PREFIX}:{run_id}"


def _conv_runs_key(conversation_id: str) -> str:
    return f"{_CONV_RUNS_PREFIX}:{conversation_id}"


async def save_run(run_data: dict[str, Any]) -> None:
    """Persist a completed run. Best-effort."""
    if not _enabled():
        return
    run_id = run_data.get("run_id")
    conversation_id = run_data.get("conversation_id")
    if not run_id:
        return

    payload = json.dumps(run_data, default=str)

    client = valkey.get_client()
    if client is not None and not valkey.breaker_open():
        try:
            key = _run_key(run_id)
            await client.set(key, payload, ex=_RUN_TTL_SECONDS)
            if conversation_id:
                conv_key = _conv_runs_key(conversation_id)
                await client.rpush(conv_key, run_id)
                await client.ltrim(conv_key, -50, -1)
                await client.expire(conv_key, _RUN_TTL_SECONDS)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("run save failed; opening breaker: %s", exc)
            valkey.trip_breaker()

    _in_memory_runs[run_id] = run_data
    if conversation_id:
        idx = _in_memory_conv_index.setdefault(conversation_id, [])
        if run_id not in idx:
            idx.append(run_id)


async def load_run(run_id: str) -> Optional[dict[str, Any]]:
    """Load a single run by ID. Returns None on miss or any failure."""
    if not _enabled():
        return None

    client = valkey.get_client()
    if client is not None and not valkey.breaker_open():
        try:
            raw = await client.get(_run_key(run_id))
            if raw:
                return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("run load failed; opening breaker: %s", exc)
            valkey.trip_breaker()

    return _in_memory_runs.get(run_id)


async def list_runs(
    conversation_id: Optional[str], limit: int = 20
) -> list[dict[str, Any]]:
    """List recent runs for a conversation, newest first."""
    if not _enabled() or not conversation_id:
        return []

    client = valkey.get_client()
    if client is not None and not valkey.breaker_open():
        try:
            conv_key = _conv_runs_key(conversation_id)
            run_ids = await client.lrange(conv_key, -limit, -1)
            if run_ids:
                pipe = client.pipeline()
                for rid in run_ids:
                    pipe.get(_run_key(rid))
                results = await pipe.execute()
                runs = [json.loads(r) for r in results if r]
                return [r for r in runs if r]
        except Exception as exc:  # noqa: BLE001
            logger.warning("run list failed; opening breaker: %s", exc)
            valkey.trip_breaker()

    idx = _in_memory_conv_index.get(conversation_id, [])
    return [_in_memory_runs.get(rid) for rid in reversed(idx[-limit:]) if rid in _in_memory_runs]


async def delete_run(run_id: str) -> None:
    """Delete a run. Best-effort."""
    if not _enabled():
        return

    client = valkey.get_client()
    if client is not None and not valkey.breaker_open():
        try:
            await client.delete(_run_key(run_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("run delete failed; opening breaker: %s", exc)
            valkey.trip_breaker()

    _in_memory_runs.pop(run_id, None)
    for idx in _in_memory_conv_index.values():
        if run_id in idx:
            idx.remove(run_id)


def reset() -> None:
    """Test helper — clear in-memory state."""
    _in_memory_runs.clear()
    _in_memory_conv_index.clear()
