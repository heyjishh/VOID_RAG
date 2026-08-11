"""Shared async Valkey (redis-protocol) client with a best-effort circuit breaker.

Every consumer — answer cache, conversation memory, rate limiter — shares ONE
client and ONE breaker, so a dead Valkey trips the breaker once and all consumers
short-circuit together instead of each paying a connect timeout.

The client is redis-py's async client; it speaks the Valkey wire protocol, so no
separate `valkey` package is needed.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from app.config.settings import settings

logger = logging.getLogger("juryai.valkey")

_client: Any = None
_client_ready: bool = False
_breaker_open_until: float = 0.0


def get_client() -> Any:
    """Return a lazily-built async Valkey client, or None if unavailable."""
    global _client, _client_ready
    if _client_ready:
        return _client
    _client_ready = True
    try:
        from redis.asyncio import Redis  # redis-py: Valkey wire-compatible

        _client = Redis.from_url(
            settings.VALKEY_URL,
            socket_connect_timeout=settings.VALKEY_TIMEOUT_SECONDS,
            socket_timeout=settings.VALKEY_TIMEOUT_SECONDS,
            decode_responses=True,
        )
    except Exception as exc:  # noqa: BLE001 — Valkey is optional infrastructure
        logger.warning("Valkey client unavailable: %s", exc)
        _client = None
    return _client


def breaker_open() -> bool:
    """True while the breaker is tripped (skip Valkey to avoid a reconnect tax)."""
    return time.monotonic() < _breaker_open_until


def trip_breaker() -> None:
    global _breaker_open_until
    _breaker_open_until = time.monotonic() + settings.VALKEY_BREAKER_COOLDOWN_SECONDS


def reset() -> None:
    """Test helper — clear the cached client and breaker state."""
    global _client, _client_ready, _breaker_open_until
    _client = None
    _client_ready = False
    _breaker_open_until = 0.0
