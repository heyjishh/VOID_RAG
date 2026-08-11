"""Tests for the meta-verification layer (app.core.graph.verifier) and its
integration into the SSE streaming endpoint.

Covers:
- verify_answer short-circuits to the fallback on empty answer/evidence (no LLM call)
- robust JSON parsing of fenced ```json blocks
- verdict is derived from score when the model omits it
- SSE emits a `verification` event before `done`, and `done` nests `verification`
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from app.core.graph.verifier import verify_answer, _build_evidence_text, _FALLBACK
from app.main import create_app
from tests.test_sse import parse_sse, _MINIMAL_STATE, _mock_workflow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_llm(content: str):
    """Return a mock get_llm() whose ainvoke resolves to a message with .content."""
    resp = MagicMock()
    resp.content = content
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=resp)
    return llm


_EVIDENCE = [
    {"text": "Section 302 IPC defines the punishment for murder.",
     "source": "ipc.pdf", "page": 1, "domain": "internal"},
]


# ---------------------------------------------------------------------------
# (a) Fallback on empty inputs — no LLM call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_answer_empty_answer_returns_fallback_no_llm():
    with patch("app.core.graph.verifier.get_llm") as mget:
        result = await verify_answer("", _EVIDENCE)
    assert result == _FALLBACK
    mget.assert_not_called()


@pytest.mark.asyncio
async def test_verify_answer_whitespace_answer_returns_fallback_no_llm():
    with patch("app.core.graph.verifier.get_llm") as mget:
        result = await verify_answer("   \n  ", _EVIDENCE)
    assert result == _FALLBACK
    mget.assert_not_called()


@pytest.mark.asyncio
async def test_verify_answer_empty_evidence_returns_fallback_no_llm():
    with patch("app.core.graph.verifier.get_llm") as mget:
        result = await verify_answer("Some answer.", [])
    assert result == _FALLBACK
    mget.assert_not_called()


@pytest.mark.asyncio
async def test_verify_answer_fallback_is_a_copy():
    """The fallback returned must not be the shared module-level dict."""
    result = await verify_answer("", [])
    assert result is not _FALLBACK
    assert result == _FALLBACK


# ---------------------------------------------------------------------------
# (b) Robust JSON parsing of fenced ```json blocks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_answer_parses_fenced_json_block():
    payload = {
        "groundedness_score": 0.86,
        "verdict": "grounded",
        "supported_claims": [
            {"claim": "Section 302 IPC defines murder.", "content_hash": "abc123"}
        ],
        "unsupported_claims": [],
        "summary": "Fully supported by the evidence.",
    }
    fenced = "```json\n" + json.dumps(payload) + "\n```"
    with patch("app.core.graph.verifier.get_llm", return_value=_mock_llm(fenced)):
        result = await verify_answer("Section 302 IPC defines murder.", _EVIDENCE)
    assert result["groundedness_score"] == 0.86
    assert result["verdict"] == "grounded"
    assert result["supported_claims"] == [
        {"claim": "Section 302 IPC defines murder.", "content_hash": "abc123"}
    ]
    assert result["unsupported_claims"] == []
    assert result["summary"] == "Fully supported by the evidence."


@pytest.mark.asyncio
async def test_verify_answer_parses_json_with_surrounding_prose():
    payload = {
        "groundedness_score": 0.5,
        "verdict": "partially_grounded",
        "supported_claims": [{"claim": "a", "content_hash": "h1"}],
        "unsupported_claims": ["b"],
        "summary": "Half supported.",
    }
    noisy = "Here is my verdict:\n" + json.dumps(payload) + "\nThanks!"
    with patch("app.core.graph.verifier.get_llm", return_value=_mock_llm(noisy)):
        result = await verify_answer("answer", _EVIDENCE)
    assert result["verdict"] == "partially_grounded"
    assert result["supported_claims"] == [{"claim": "a", "content_hash": "h1"}]


# ---------------------------------------------------------------------------
# (c) Verdict derived from score when the model omits it
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "score,expected",
    [(0.9, "grounded"), (0.8, "grounded"), (0.6, "partially_grounded"),
     (0.5, "partially_grounded"), (0.3, "unsupported"), (0.0, "unsupported")],
)
async def test_verify_answer_derives_verdict_from_score(score, expected):
    payload = {
        "groundedness_score": score,
        "supported_claims": [],
        "unsupported_claims": [],
        "summary": "no verdict field present",
    }
    with patch("app.core.graph.verifier.get_llm", return_value=_mock_llm(json.dumps(payload))):
        result = await verify_answer("answer", _EVIDENCE)
    assert result["verdict"] == expected


@pytest.mark.asyncio
async def test_verify_answer_prefers_model_verdict_when_valid():
    """A valid model verdict wins even if it disagrees with the score band."""
    payload = {
        "groundedness_score": 0.95,
        "verdict": "partially_grounded",
        "supported_claims": [],
        "unsupported_claims": [],
        "summary": "model chose its own verdict",
    }
    with patch("app.core.graph.verifier.get_llm", return_value=_mock_llm(json.dumps(payload))):
        result = await verify_answer("answer", _EVIDENCE)
    assert result["verdict"] == "partially_grounded"


@pytest.mark.asyncio
async def test_verify_answer_computes_score_when_missing():
    """When score is absent, it is computed from supported/total claim counts."""
    payload = {
        "supported_claims": ["a", "b", "c"],
        "unsupported_claims": ["d"],
        "summary": "3 of 4 supported",
    }
    with patch("app.core.graph.verifier.get_llm", return_value=_mock_llm(json.dumps(payload))):
        result = await verify_answer("answer", _EVIDENCE)
    assert abs(result["groundedness_score"] - 0.75) < 1e-9
    assert result["verdict"] == "partially_grounded"


@pytest.mark.asyncio
async def test_verify_answer_bad_json_returns_fallback():
    with patch("app.core.graph.verifier.get_llm", return_value=_mock_llm("not json at all")):
        result = await verify_answer("answer", _EVIDENCE)
    assert result == _FALLBACK


@pytest.mark.asyncio
async def test_verify_answer_llm_exception_returns_fallback():
    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=RuntimeError("provider down"))
    with patch("app.core.graph.verifier.get_llm", return_value=llm):
        result = await verify_answer("answer", _EVIDENCE)
    assert result == _FALLBACK


# ---------------------------------------------------------------------------
# (d) _build_evidence_text internal-preference policy, now that callers pass
# real mixed-domain evidence instead of pre-filtering to internal-only.
# ---------------------------------------------------------------------------

_MIXED_EVIDENCE = [
    {"text": "Section 302 IPC defines murder.", "source": "ipc.pdf", "page": 12,
     "domain": "internal", "content_hash": "int-hash-1"},
    {"title": "Live Law", "url": "https://livelaw.in/x",
     "content": "The Supreme Court held that intent is essential to murder.",
     "domain": "web", "content_hash": "web-hash-1"},
]


def test_build_evidence_text_prefers_internal_when_both_domains_present():
    text = _build_evidence_text(_MIXED_EVIDENCE)
    assert "Section 302 IPC defines murder." in text
    assert "The Supreme Court held that" not in text


def test_build_evidence_text_falls_back_to_web_when_no_internal():
    web_only = [item for item in _MIXED_EVIDENCE if item["domain"] == "web"]
    text = _build_evidence_text(web_only)
    assert "The Supreme Court held that" in text


@pytest.mark.asyncio
async def test_verify_answer_prompt_still_prioritizes_internal_with_mixed_input():
    """verify_answer must render only internal evidence in its prompt to the
    LLM when mixed evidence is passed directly (the new, correct input shape),
    even though it also received web evidence."""
    captured_prompt = {}

    async def fake_ainvoke(messages):
        captured_prompt["text"] = messages[0].content
        resp = MagicMock()
        resp.content = json.dumps({
            "groundedness_score": 0.9, "verdict": "grounded",
            "supported_claims": [], "unsupported_claims": [], "summary": "ok",
        })
        return resp

    llm = MagicMock()
    llm.ainvoke = AsyncMock(side_effect=fake_ainvoke)
    with patch("app.core.graph.verifier.get_llm", return_value=llm):
        await verify_answer("Murder requires intent.", _MIXED_EVIDENCE)

    assert "Section 302 IPC defines murder." in captured_prompt["text"]
    assert "The Supreme Court held that" not in captured_prompt["text"]


# ---------------------------------------------------------------------------
# SSE integration: verification event before done; done nests verification
# ---------------------------------------------------------------------------

_VERDICT = {
    "groundedness_score": 0.86,
    "verdict": "grounded",
    "supported_claims": ["Section 302 IPC defines murder."],
    "unsupported_claims": [],
    "summary": "Supported by the evidence.",
}


@pytest.mark.asyncio
async def test_stream_emits_verification_before_done():
    app = create_app()
    with _mock_workflow(_MINIMAL_STATE), \
         patch("app.api.v1.chat.verify_answer", AsyncMock(return_value=_VERDICT)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/chat/stream", json={"question": "What is 302 IPC?"})
    events = parse_sse(r.text)
    typed = [e.get("event") for e in events]
    assert "verification" in typed, f"no verification event. Got: {typed}"
    assert typed.index("verification") < typed.index("done")
    # answer_token(s) must precede verification
    assert typed.index("answer_token") < typed.index("verification")


@pytest.mark.asyncio
async def test_stream_verification_event_schema():
    app = create_app()
    with _mock_workflow(_MINIMAL_STATE), \
         patch("app.api.v1.chat.verify_answer", AsyncMock(return_value=_VERDICT)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/chat/stream", json={"question": "What is 302 IPC?"})
    events = parse_sse(r.text)
    ver = next(e for e in events if e.get("event") == "verification")
    data = ver["data"]
    for key in ("groundedness_score", "verdict", "supported_claims",
                "unsupported_claims", "summary"):
        assert key in data, f"verification event missing '{key}'"
    assert data["verdict"] == "grounded"


@pytest.mark.asyncio
async def test_stream_done_nests_verification():
    app = create_app()
    with _mock_workflow(_MINIMAL_STATE), \
         patch("app.api.v1.chat.verify_answer", AsyncMock(return_value=_VERDICT)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/chat/stream", json={"question": "What is 302 IPC?"})
    events = parse_sse(r.text)
    done = next(e for e in events if e.get("event") == "done")
    assert "verification" in done["data"]
    assert done["data"]["verification"]["verdict"] == "grounded"
