"""Valkey-backed fixed-window rate limiter.

Fail-open by design: if Valkey is unavailable the request is allowed (never lock
users out because the limiter's store is down). Shares the process-wide client +
breaker in ``app.core.valkey``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config.settings import settings
from app.core import valkey

logger = logging.getLogger("juryai.ratelimit")

_KEY_PREFIX = "juryai:rl"


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int  # seconds until the window resets (0 when allowed)


async def check_rate_limit(identifier: str) -> RateLimitResult:
    """Fixed-window counter for ``identifier`` (e.g. client IP).

    First request in a window sets the key with EXPIRE; subsequent requests INCR.
    Over the cap → not allowed. Any Valkey failure → fail-open (allowed).
    """
    limit = settings.RATELIMIT_MAX_REQUESTS
    window = settings.RATELIMIT_WINDOW_SECONDS
    if not settings.RATELIMIT_ENABLED or valkey.breaker_open():
        return RateLimitResult(allowed=True, remaining=limit, retry_after=0)
    client = valkey.get_client()
    if client is None:
        return RateLimitResult(allowed=True, remaining=limit, retry_after=0)

    key = f"{_KEY_PREFIX}:{identifier}"
    try:
        count = await client.incr(key)
        if count == 1:
            # First hit in this window — start the expiry clock.
            await client.expire(key, window)
            ttl = window
        else:
            ttl = await client.ttl(key)
            if ttl < 0:  # key exists without TTL (edge case) — re-arm it
                await client.expire(key, window)
                ttl = window
        if count > limit:
            return RateLimitResult(allowed=False, remaining=0, retry_after=max(ttl, 1))
        return RateLimitResult(allowed=True, remaining=max(limit - count, 0), retry_after=0)
    except Exception as exc:  # noqa: BLE001 — fail open, never lock users out
        logger.warning("rate limit check failed; opening breaker: %s", exc)
        valkey.trip_breaker()
        return RateLimitResult(allowed=True, remaining=limit, retry_after=0)
