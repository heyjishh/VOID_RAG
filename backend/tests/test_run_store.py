"""Tests for the Valkey-backed run store (app.core.run_store)."""
from __future__ import annotations

import pytest

from app.core import valkey
from app.core.run_store import save_run, load_run, list_runs, delete_run, reset


class FakeValkey:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex=None):
        self.store[key] = value

    async def delete(self, key: str):
        self.store.pop(key, None)

    async def rpush(self, key: str, *values):
        self.lists.setdefault(key, []).extend(values)

    async def lrange(self, key: str, start: int, stop: int):
        lst = self.lists.get(key, [])
        if stop == -1:
            return lst[start:]
        return lst[start:stop + 1]

    async def ltrim(self, key: str, start: int, stop: int):
        lst = self.lists.get(key, [])
        self.lists[key] = lst[start:stop + 1] if stop != -1 else lst[start:]

    async def expire(self, key: str, ttl: int):
        pass

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, client):
        self._client = client
        self._queue = []

    def get(self, key):
        self._queue.append(("get", key))
        return self

    async def execute(self):
        results = []
        for op, key in self._queue:
            if op == "get":
                results.append(self._client.store.get(key))
        return results


class BrokenValkey:
    async def get(self, key: str):
        raise ConnectionError("valkey down")

    async def set(self, key: str, value: str, ex=None):
        raise ConnectionError("valkey down")

    async def delete(self, key: str):
        raise ConnectionError("valkey down")

    async def rpush(self, key: str, *values):
        raise ConnectionError("valkey down")

    async def lrange(self, key: str, start: int, stop: int):
        raise ConnectionError("valkey down")

    async def ltrim(self, key: str, start: int, stop: int):
        raise ConnectionError("valkey down")

    async def expire(self, key: str, ttl: int):
        raise ConnectionError("valkey down")

    def pipeline(self):
        return self

    async def execute(self):
        raise ConnectionError("valkey down")


@pytest.fixture(autouse=True)
def _reset():
    reset()
    valkey.reset()
    yield
    reset()
    valkey.reset()


def _use_client(monkeypatch, client):
    monkeypatch.setattr(valkey, "get_client", lambda: client)


@pytest.mark.asyncio
async def test_save_and_load_run(monkeypatch):
    fake = FakeValkey()
    _use_client(monkeypatch, fake)
    run = {"run_id": "abc123", "question": "Q?", "answer": "A.", "conversation_id": "c1"}
    await save_run(run)
    got = await load_run("abc123")
    assert got == run


@pytest.mark.asyncio
async def test_load_missing_returns_none(monkeypatch):
    fake = FakeValkey()
    _use_client(monkeypatch, fake)
    assert await load_run("missing") is None


@pytest.mark.asyncio
async def test_list_runs(monkeypatch):
    fake = FakeValkey()
    _use_client(monkeypatch, fake)
    for i in range(3):
        await save_run({"run_id": f"r{i}", "conversation_id": "c1", "answer": str(i)})
    runs = await list_runs("c1", limit=10)
    assert len(runs) == 3
    assert runs[0]["run_id"] == "r0"


@pytest.mark.asyncio
async def test_delete_run(monkeypatch):
    fake = FakeValkey()
    _use_client(monkeypatch, fake)
    await save_run({"run_id": "x", "conversation_id": "c1"})
    assert await load_run("x") is not None
    await delete_run("x")
    assert await load_run("x") is None


@pytest.mark.asyncio
async def test_broken_valkey_falls_back_to_memory(monkeypatch):
    broken = BrokenValkey()
    _use_client(monkeypatch, broken)
    run = {"run_id": "mem1", "conversation_id": "c1", "answer": "A"}
    await save_run(run)
    got = await load_run("mem1")
    assert got == run
