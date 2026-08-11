"""Tests for the Valkey-backed answer cache (app.core.cache).

The cache is best-effort: it must degrade to a miss on any failure and never
raise into the request path. These tests use an in-memory fake async client so
they run without a live Valkey.
"""
from __future__ import annotations

import pytest

import app.core.cache as cache
from app.core import valkey


class FakeValkey:
    """Minimal in-memory async stand-in for redis.asyncio.Redis."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.set_calls: list[tuple] = []

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex=None):
        self.store[key] = value
        self.set_calls.append((key, ex))


class BrokenValkey:
    """Fake client whose ops always fail — exercises graceful degradation."""

    async def get(self, key: str):
        raise ConnectionError("valkey down")

    async def set(self, key: str, value: str, ex=None):
        raise ConnectionError("valkey down")


@pytest.fixture(autouse=True)
def _reset_valkey_state():
    """Reset the shared client + breaker before and after each test."""
    valkey.reset()
    yield
    valkey.reset()


def _use_client(monkeypatch, client):
    monkeypatch.setattr(valkey, "get_client", lambda: client)


# --- key generation --------------------------------------------------------

def test_key_is_stable_across_whitespace_and_case():
    a = cache._make_key("What is Section 80C?", False, "chat")
    b = cache._make_key("  what   is   section 80c?  ", False, "chat")
    assert a == b


def test_key_differs_by_web_flag_and_scope():
    q = "What is Section 80C?"
    assert cache._make_key(q, False, "chat") != cache._make_key(q, True, "chat")
    assert cache._make_key(q, False, "post") != cache._make_key(q, False, "stream")


# --- round trip ------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_then_get_round_trips(monkeypatch):
    fake = FakeValkey()
    _use_client(monkeypatch, fake)
    payload = {"answer": "Section 80C allows deductions.", "intent": "legal"}

    await cache.answer_cache_set("Q about 80C", False, payload, scope="post")
    got = await cache.answer_cache_get("q  about 80c", False, scope="post")  # normalized-equal

    assert got == payload
    assert fake.set_calls and fake.set_calls[0][1] == cache.settings.CACHE_TTL_SECONDS


@pytest.mark.asyncio
async def test_get_miss_returns_none(monkeypatch):
    _use_client(monkeypatch, FakeValkey())
    assert await cache.answer_cache_get("never stored", False) is None


# --- graceful degradation --------------------------------------------------

@pytest.mark.asyncio
async def test_get_returns_none_when_client_unavailable(monkeypatch):
    _use_client(monkeypatch, None)
    assert await cache.answer_cache_get("anything", False) is None


@pytest.mark.asyncio
async def test_broken_client_never_raises_and_trips_breaker(monkeypatch):
    _use_client(monkeypatch, BrokenValkey())

    assert await cache.answer_cache_get("q", False) is None
    assert valkey.breaker_open()
    await cache.answer_cache_set("q", False, {"answer": "x"})  # must not raise


@pytest.mark.asyncio
async def test_open_breaker_skips_client(monkeypatch):
    fake = FakeValkey()
    _use_client(monkeypatch, fake)
    valkey.trip_breaker()

    assert await cache.answer_cache_get("q", False) is None
    await cache.answer_cache_set("q", False, {"answer": "x"})
    assert fake.set_calls == []  # client never consulted while breaker open
