"""
End-to-end tests for the SSE streaming endpoint POST /api/v1/chat/stream.

Tests verify:
- HTTP 200 with text/event-stream content-type
- `done` event is present
- `reasoning_step` events are present
- `answer_token` events are present
- Event data schemas match the spec (step/detail, token, conversation_id/intent/sources_used)
- source_chunk events carry expected fields when chunks are returned
- use_web_search and web_search_max_results are accepted without error
"""
from __future__ import annotations
import asyncio
import json
import logging
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_sse(text: str) -> list[dict]:
    """Parse raw SSE text into a list of {'event': str, 'data': any} dicts."""
    events: list[dict] = []
    current: dict = {}
    for line in text.splitlines():
        if line.startswith("event: "):
            current["event"] = line[len("event: "):]
        elif line.startswith("data: "):
            raw = line[len("data: "):]
            try:
                current["data"] = json.loads(raw)
            except json.JSONDecodeError:
                current["data"] = raw
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


def _mock_workflow(mock_state: dict):
    """Return a context manager that patches get_streaming_workflow with a mock graph.

    ``ainvoke`` mimics the real graph's live-callback contract: it fires
    ``state["on_step"]`` for every step in ``mock_state["reasoning_steps"]``
    before returning, exactly like the real nodes do via the queue/callback
    path in ``_stream_generator`` — so these mocked tests still exercise (and
    would catch a regression in) that live-emission wiring instead of relying
    on a since-removed post-hoc replay of the final state.
    """
    g = AsyncMock()

    async def _ainvoke(state, _mock_state=mock_state):
        on_step = state.get("on_step")
        if on_step:
            for step in _mock_state.get("reasoning_steps", []):
                on_step(step)
        return _mock_state

    g.ainvoke = AsyncMock(side_effect=_ainvoke)
    patcher = patch("app.api.v1.chat.get_streaming_workflow", return_value=g)
    return patcher


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MINIMAL_STATE = {
    "answer": "Section 302 IPC defines murder.",
    "citations": [{"quote": "murder", "verified": True, "source": "ipc.pdf", "page": 1}],
    "intent": "legal",
    "legal_chunks": [{"text": "murder is defined here", "source": "ipc.pdf", "page": 1, "score": 0.91}],
    "web_results": [],
    "reasoning_steps": [],
}

_NO_CHUNKS_STATE = {
    "answer": "I could not find relevant context.",
    "citations": [],
    "intent": "legal",
    "legal_chunks": [],
    "web_results": [],
    "reasoning_steps": [],
}

_WITH_EXTRA_STEPS_STATE = {
    "answer": "Web answer here.",
    "citations": [],
    "intent": "web",
    "legal_chunks": [],
    "web_results": [],
    "reasoning_steps": [
        {"step": "web_search", "detail": "Performing web search for current information"},
        {"step": "evidence_merge", "detail": "Merging web and corpus evidence"},
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_returns_200_and_event_stream_content_type():
    app = create_app()
    with _mock_workflow(_MINIMAL_STATE):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/chat/stream", json={"question": "What is 302 IPC?"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_stream_done_event_present():
    app = create_app()
    with _mock_workflow(_MINIMAL_STATE):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/chat/stream", json={"question": "What is 302 IPC?"})
    events = parse_sse(r.text)
    event_types = [e.get("event") for e in events]
    assert "done" in event_types, f"'done' event missing. Got: {event_types}"


@pytest.mark.asyncio
async def test_stream_reasoning_step_events_present():
    app = create_app()
    with _mock_workflow(_MINIMAL_STATE):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/chat/stream", json={"question": "What is 302 IPC?"})
    events = parse_sse(r.text)
    rs_events = [e for e in events if e.get("event") == "reasoning_step"]
    assert len(rs_events) >= 1, "No reasoning_step events emitted"


@pytest.mark.asyncio
async def test_stream_reasoning_step_schema():
    """Each reasoning_step event must have 'step' and 'detail' string fields."""
    app = create_app()
    with _mock_workflow(_MINIMAL_STATE):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/chat/stream", json={"question": "What is 302 IPC?"})
    events = parse_sse(r.text)
    for e in events:
        if e.get("event") == "reasoning_step":
            data = e["data"]
            assert isinstance(data, dict), "reasoning_step data must be a JSON object"
            assert "step" in data, f"reasoning_step missing 'step': {data}"
            assert "detail" in data, f"reasoning_step missing 'detail': {data}"
            assert isinstance(data["step"], str)
            assert isinstance(data["detail"], str)


@pytest.mark.asyncio
async def test_stream_done_event_schema():
    """done event must carry conversation_id, intent, and sources_used."""
    app = create_app()
    with _mock_workflow(_MINIMAL_STATE):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/v1/chat/stream",
                json={"question": "What is 302 IPC?", "conversation_id": "test-conv-001"},
            )
    events = parse_sse(r.text)
    done_events = [e for e in events if e.get("event") == "done"]
    assert len(done_events) == 1, f"Expected exactly 1 done event, got {len(done_events)}"
    data = done_events[0]["data"]
    assert "conversation_id" in data
    assert "intent" in data
    assert "sources_used" in data
    assert data["conversation_id"] == "test-conv-001"
    assert isinstance(data["sources_used"], int)


@pytest.mark.asyncio
async def test_stream_source_chunk_events_and_schema():
    """source_chunk events must carry text, source, page, score, verified, domain."""
    app = create_app()
    with _mock_workflow(_MINIMAL_STATE):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/chat/stream", json={"question": "What is 302 IPC?"})
    events = parse_sse(r.text)
    sc_events = [e for e in events if e.get("event") == "source_chunk"]
    assert len(sc_events) >= 1, "Expected source_chunk events for non-empty legal_chunks"
    for e in sc_events:
        data = e["data"]
        assert "text" in data
        assert "source" in data
        assert "score" in data
        assert "verified" in data
        assert data.get("domain") == "internal"


@pytest.mark.asyncio
async def test_stream_answer_token_events_present():
    """answer_token events must exist and each carry a 'token' string."""
    app = create_app()
    with _mock_workflow(_MINIMAL_STATE):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/chat/stream", json={"question": "What is 302 IPC?"})
    events = parse_sse(r.text)
    token_events = [e for e in events if e.get("event") == "answer_token"]
    assert len(token_events) >= 1, "No answer_token events emitted"
    for e in token_events:
        data = e["data"]
        assert "token" in data
        assert isinstance(data["token"], str)


@pytest.mark.asyncio
async def test_stream_event_order():
    """reasoning_step(s) must come before source_chunk, source_chunk before answer_token,
    answer_token before done."""
    app = create_app()
    with _mock_workflow(_MINIMAL_STATE):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/chat/stream", json={"question": "What is 302 IPC?"})
    events = parse_sse(r.text)
    typed = [e.get("event") for e in events]

    def first(t: str) -> int:
        try:
            return typed.index(t)
        except ValueError:
            return -1

    idx_rs = first("reasoning_step")
    idx_done = first("done")
    assert idx_rs != -1 and idx_done != -1
    assert idx_rs < idx_done, "reasoning_step must precede done"


@pytest.mark.asyncio
async def test_stream_no_chunks_sources_used_zero():
    """When legal_chunks is empty, done event sources_used must be 0."""
    app = create_app()
    with _mock_workflow(_NO_CHUNKS_STATE):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/chat/stream", json={"question": "Random question"})
    events = parse_sse(r.text)
    done = next(e for e in events if e.get("event") == "done")
    assert done["data"]["sources_used"] == 0


@pytest.mark.asyncio
async def test_stream_extra_reasoning_steps_from_state():
    """reasoning_steps in state are emitted after the fixed pre-run steps."""
    app = create_app()
    with _mock_workflow(_WITH_EXTRA_STEPS_STATE):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/v1/chat/stream",
                json={"question": "Latest case law?", "use_web_search": True},
            )
    events = parse_sse(r.text)
    rs_events = [e for e in events if e.get("event") == "reasoning_step"]
    step_names = [e["data"]["step"] for e in rs_events]
    # The two extra steps from state must appear
    assert "web_search" in step_names
    assert "evidence_merge" in step_names


@pytest.mark.asyncio
async def test_stream_web_search_start_and_done_are_discrete_ordered_events():
    """web_search_start and web_search_done must arrive as two separate
    reasoning_step events, start before done — not collapsed into one."""
    state = {
        **_MINIMAL_STATE,
        "reasoning_steps": [
            {"step": "web_search_start", "detail": "Searching web for current legal information"},
            {"step": "web_search_done", "detail": "3 web sources retrieved"},
        ],
    }
    app = create_app()
    with _mock_workflow(state):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/v1/chat/stream",
                json={"question": "Latest case law?", "use_web_search": True},
            )
    events = parse_sse(r.text)
    step_names = [e["data"]["step"] for e in events if e.get("event") == "reasoning_step"]
    assert "web_search_start" in step_names
    assert "web_search_done" in step_names
    assert step_names.index("web_search_start") < step_names.index("web_search_done")


@pytest.mark.asyncio
async def test_stream_reasoning_steps_arrive_live_not_after_full_graph_resolves():
    """Regression test for the retroactive-burst bug: web_search_start must be
    yielded by ``_stream_generator`` while the (mocked) graph call is still in
    flight — delivered via the on_step callback + asyncio.Queue — rather than
    only after graph.ainvoke() fully resolves, which is how the previous
    ``for step in result.get("reasoning_steps", [])`` replay behaved.

    Exercises ``_stream_generator`` directly (not through the HTTP test
    client): httpx's ``ASGITransport`` buffers the entire SSE body and only
    hands it to the client once the whole response is done — true even for
    the pre-existing real LLM-token-streaming path — so it cannot distinguish
    live delivery from a retroactive burst. Iterating the async generator
    in-process can.
    """
    import time
    import uuid as _uuid

    from app.api.schemas import ChatRequest
    from app.api.v1.chat import _stream_generator

    g = AsyncMock()

    async def _slow_ainvoke(state):
        on_step = state["on_step"]
        on_step({"step": "web_search_start", "detail": "Searching web..."})
        await asyncio.sleep(0.3)
        on_step({"step": "web_search_done", "detail": "done"})
        return {**_MINIMAL_STATE, "reasoning_steps": []}

    g.ainvoke = AsyncMock(side_effect=_slow_ainvoke)

    request = ChatRequest(
        question=f"unique live-streaming question {_uuid.uuid4()}",
        use_web_search=True,
    )

    start_seen_at = None
    done_seen_at = None
    t0 = time.monotonic()
    with patch("app.api.v1.chat.get_streaming_workflow", return_value=g):
        async for raw in _stream_generator(request, "test-client"):
            for e in parse_sse(raw):
                if e.get("event") != "reasoning_step":
                    continue
                step = e["data"].get("step")
                now = time.monotonic() - t0
                if step == "web_search_start" and start_seen_at is None:
                    start_seen_at = now
                if step == "web_search_done" and done_seen_at is None:
                    done_seen_at = now

    assert start_seen_at is not None, "web_search_start was never observed"
    assert done_seen_at is not None, "web_search_done was never observed"
    assert start_seen_at < 0.15, (
        f"web_search_start arrived at {start_seen_at:.3f}s — should be near-instant, "
        "not buffered behind the 0.3s sleep"
    )
    assert done_seen_at - start_seen_at >= 0.2, (
        f"only {done_seen_at - start_seen_at:.3f}s between start/done — events look "
        "batched together instead of delivered live as they happen"
    )


@pytest.mark.asyncio
async def test_stream_accepts_web_search_flags():
    """use_web_search and web_search_max_results must not cause a validation error."""
    app = create_app()
    with _mock_workflow(_MINIMAL_STATE):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/v1/chat/stream",
                json={
                    "question": "What is res judicata?",
                    "use_web_search": True,
                    "web_search_max_results": 10,
                },
            )
    assert r.status_code == 200


_MIXED_MERGED = [
    {"text": "Section 302 IPC defines murder.", "source": "ipc.pdf", "page": 12,
     "domain": "internal", "content_hash": "int-hash-1", "score": 0.9},
    {"title": "Live Law", "url": "https://livelaw.in/x",
     "content": "The Supreme Court held that intent is essential to murder.",
     "domain": "web", "content_hash": "web-hash-1", "score": 0.7},
]

_MIXED_VERDICT = {
    "groundedness_score": 0.9,
    "verdict": "grounded",
    "supported_claims": [
        {"claim": "Section 302 IPC defines murder.", "content_hash": "int-hash-1"},
        {"claim": "The Supreme Court held that intent is essential to murder.",
         "content_hash": "web-hash-1"},
    ],
    "unsupported_claims": [],
    "summary": "Both internal and web claims are grounded.",
}

_MIXED_STATE = {
    "answer": "Section 302 IPC defines murder, and the Supreme Court has held intent is essential.",
    "citations": [],
    "intent": "legal",
    "legal_chunks": [],
    "web_results": [],
    "reasoning_steps": [],
    "merged_evidence": _MIXED_MERGED,
}


@pytest.mark.asyncio
async def test_stream_web_search_includes_web_domain_in_sources_and_citations():
    """Regression test: with use_web_search=True and merged_evidence carrying
    both internal and web items, verification/citations/source_chunks in the
    `done` event must include the web item — previously verify_evidence was
    hardcoded to domain == "internal", discarding web evidence end-to-end."""
    app = create_app()
    with _mock_workflow(_MIXED_STATE), \
         patch("app.api.v1.chat.verify_answer", AsyncMock(return_value=_MIXED_VERDICT)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/v1/chat/stream",
                json={"question": "What defines murder under IPC?", "use_web_search": True},
            )
    events = parse_sse(r.text)
    done = next(e for e in events if e.get("event") == "done")
    data = done["data"]

    domains = {sc["domain"] for sc in data["source_chunks"]}
    assert domains == {"internal", "web"}, f"expected both domains, got: {data['source_chunks']}"

    web_chunk = next(sc for sc in data["source_chunks"] if sc["domain"] == "web")
    assert web_chunk["verified"] is True
    assert web_chunk["text"] == "The Supreme Court held that intent is essential to murder."

    citation_hashes = {c["content_hash"] for c in data["citations"]}
    assert "web-hash-1" in citation_hashes
    assert "int-hash-1" in citation_hashes

    verification = data["verification"]
    assert verification["verdict"] == "grounded"


@pytest.mark.asyncio
async def test_stream_internal_only_evidence_unaffected_by_merge_change():
    """No web search / no merged_evidence: existing internal-only behavior via
    the legal_chunks fallback must be unchanged (domain always "internal")."""
    app = create_app()
    with _mock_workflow(_MINIMAL_STATE), \
         patch("app.api.v1.chat.verify_answer", AsyncMock(return_value={
             "groundedness_score": 0.9, "verdict": "grounded",
             "supported_claims": [], "unsupported_claims": [], "summary": ""
         })):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/chat/stream", json={"question": "What is 302 IPC?"})
    events = parse_sse(r.text)
    done = next(e for e in events if e.get("event") == "done")
    data = done["data"]
    assert all(sc["domain"] == "internal" for sc in data["source_chunks"])


@pytest.mark.asyncio
async def test_stream_auto_generates_conversation_id():
    """If no conversation_id is supplied, done event must still have one."""
    app = create_app()
    with _mock_workflow(_MINIMAL_STATE):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/chat/stream", json={"question": "Any question"})
    events = parse_sse(r.text)
    done = next(e for e in events if e.get("event") == "done")
    cid = done["data"].get("conversation_id", "")
    assert cid, "conversation_id must not be empty"


# ---------------------------------------------------------------------------
# LLM gateway failure mid-stream — must log AND still ship the fallback token
# ---------------------------------------------------------------------------

# Real token-streaming only runs when the graph produced an "answer_prompt"
# (streaming mode). Evidence lists are left empty so verify_answer/gate_answer
# short-circuit to their safe fallback without needing get_llm() for anything
# other than the astream() call under test.
_ANSWER_PROMPT_STATE = {
    "answer": "",
    "answer_prompt": "Answer the question using only the evidence below.",
    "citations": [],
    "intent": "legal",
    "legal_chunks": [],
    "web_results": [],
    "reasoning_steps": [],
}


def _raising_llm():
    """Return a get_llm()-shaped mock whose astream() raises mid-iteration."""

    async def _boom_astream(*_args, **_kwargs):
        raise RuntimeError("simulated LLM gateway failure")
        yield  # pragma: no cover - unreachable; makes this an async generator

    mock_llm = MagicMock()
    mock_llm.astream = MagicMock(side_effect=lambda *a, **k: _boom_astream())
    return MagicMock(return_value=mock_llm)


@pytest.mark.asyncio
async def test_stream_llm_failure_logs_exception_and_still_yields_fallback_token(caplog):
    """A raised exception from get_llm().astream() must be logged with a full
    traceback (the previous bare `except Exception: pass`-equivalent left zero
    log trail) while the client-facing recovery behavior — a "stream_interrupted"
    reasoning_step, never a literal token in the visible answer — is surfaced."""
    app = create_app()
    with _mock_workflow(_ANSWER_PROMPT_STATE), \
         patch("app.api.v1.chat.get_llm", _raising_llm()):
        with caplog.at_level(logging.WARNING, logger="juryai.chat"):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.post(
                    "/api/v1/chat/stream",
                    json={"question": "What is 302 IPC?", "conversation_id": "conv-boom-1"},
                )

    events = parse_sse(r.text)
    tokens = [e["data"]["token"] for e in events if e.get("event") == "answer_token"]
    assert not any("[Stream interrupted]" in t for t in tokens), (
        f"raw interrupt marker leaked into visible answer tokens: {tokens}"
    )
    steps = [e["data"] for e in events if e.get("event") == "reasoning_step"]
    assert any(s.get("step") == "stream_interrupted" for s in steps), (
        f"stream_interrupted reasoning_step missing: {steps}"
    )

    warning_records = [rec for rec in caplog.records if rec.name == "juryai.chat"]
    assert warning_records, "LLM stream failure was not logged at all"
    record = warning_records[0]
    assert record.levelno == logging.WARNING
    assert "conv-boom-1" in record.getMessage()
    assert record.exc_info is not None, "traceback was not captured (exc_info missing)"
    assert record.exc_info[1] is not None
    assert "simulated LLM gateway failure" in str(record.exc_info[1])
