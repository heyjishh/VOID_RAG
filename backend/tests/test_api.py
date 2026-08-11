import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from app.main import create_app


_MIXED_EVIDENCE = [
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

_MIXED_CITATIONS = [
    {"quote": "Section 302 IPC defines murder.", "verified": True,
     "source": "ipc.pdf", "page": 12, "content_hash": "int-hash-1"},
    {"quote": "The Supreme Court held that intent is essential to murder.",
     "verified": True, "source": "Live Law", "page": 0, "content_hash": "web-hash-1"},
]


@pytest.mark.asyncio
async def test_health():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_chat_returns_answer():
    app = create_app()
    mock_state = {
        "answer": "Section 302 IPC defines murder.",
        "citations": [{"quote": "murder", "verified": True, "source": "ipc.pdf", "page": 0}],
        "intent": "legal",
        "legal_chunks": [{"text": "murder", "source": "ipc.pdf", "page": 0, "score": 0.9}],
        "web_results": [],
    }
    with patch("app.api.v1.chat.get_workflow") as mwf:
        g = AsyncMock()
        g.ainvoke = AsyncMock(return_value=mock_state)
        mwf.return_value = g
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/chat", json={"question": "What is 302 IPC?"})
    assert r.status_code == 200
    d = r.json()
    assert "answer" in d and "conversation_id" in d and "citations" in d


@pytest.mark.asyncio
async def test_chat_forwards_use_web_search_true_to_graph_state():
    """POST /chat with use_web_search: true must reach state['use_web_search'] as
    True when the graph is invoked — regression test for the state dict silently
    defaulting use_web_search to False (route_and_retrieve otherwise never
    triggers web_search_node regardless of the request flag)."""
    app = create_app()
    mock_state = {
        "answer": "Section 302 IPC defines murder.",
        "citations": [],
        "intent": "legal",
        "legal_chunks": [],
        "web_results": [],
    }
    with patch("app.api.v1.chat.get_workflow") as mwf:
        g = AsyncMock()
        g.ainvoke = AsyncMock(return_value=mock_state)
        mwf.return_value = g
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/v1/chat",
                json={"question": "What is 302 IPC?", "use_web_search": True},
            )
    assert r.status_code == 200
    g.ainvoke.assert_awaited_once()
    passed_state = g.ainvoke.await_args.args[0]
    assert passed_state.get("use_web_search") is True


@pytest.mark.asyncio
async def test_chat_forwards_use_web_search_false_to_graph_state():
    """Default/false use_web_search must also be forwarded explicitly (not just
    relying on route_and_retrieve's own default)."""
    app = create_app()
    mock_state = {
        "answer": "Section 302 IPC defines murder.",
        "citations": [],
        "intent": "legal",
        "legal_chunks": [],
        "web_results": [],
    }
    with patch("app.api.v1.chat.get_workflow") as mwf:
        g = AsyncMock()
        g.ainvoke = AsyncMock(return_value=mock_state)
        mwf.return_value = g
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/v1/chat",
                json={"question": "What is 302 IPC?", "use_web_search": False},
            )
    assert r.status_code == 200
    passed_state = g.ainvoke.await_args.args[0]
    assert passed_state.get("use_web_search") is False


@pytest.mark.asyncio
async def test_chat_with_web_search_includes_web_domain_in_sources_and_citations():
    """Regression test: with use_web_search=True and merged_evidence carrying
    both internal and web items, the final response must surface the web item
    in both source_chunks and citations — previously evidence was hardcoded to
    legal_chunks (internal-only), so web items never reached the response."""
    app = create_app()
    mock_state = {
        "answer": "Section 302 IPC defines murder, and the Supreme Court has held intent is essential.",
        "citations": _MIXED_CITATIONS,
        "verification": _MIXED_VERDICT,
        "intent": "legal",
        "legal_chunks": [],
        "web_results": [],
        "merged_evidence": _MIXED_EVIDENCE,
        "model_provider": "test",
        "model_name": "test-model",
    }
    with patch("app.api.v1.chat.get_workflow") as mwf:
        g = AsyncMock()
        g.ainvoke = AsyncMock(return_value=mock_state)
        mwf.return_value = g
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/v1/chat",
                json={"question": "What defines murder under IPC?", "use_web_search": True},
            )
    assert r.status_code == 200
    d = r.json()

    domains = {sc["domain"] for sc in d["source_chunks"]}
    assert domains == {"internal", "web"}, f"expected both domains, got: {d['source_chunks']}"

    web_chunk = next(sc for sc in d["source_chunks"] if sc["domain"] == "web")
    assert web_chunk["verified"] is True
    assert web_chunk["text"] == "The Supreme Court held that intent is essential to murder."

    citation_hashes = {c["content_hash"] for c in d["citations"]}
    assert "web-hash-1" in citation_hashes
    assert "int-hash-1" in citation_hashes


@pytest.mark.asyncio
async def test_chat_internal_only_evidence_unaffected_by_merge_preference():
    """No web search / no web results: existing internal-only behavior must be
    unchanged — merged_evidence absent, falls back to legal_chunks as before."""
    app = create_app()
    mock_state = {
        "answer": "Section 302 IPC defines murder.",
        "citations": [{"quote": "murder", "verified": True, "source": "ipc.pdf",
                       "page": 0, "content_hash": "h1"}],
        "verification": {"groundedness_score": 0.9, "verdict": "grounded",
                          "supported_claims": [], "unsupported_claims": [], "summary": ""},
        "intent": "legal",
        "legal_chunks": [{"text": "murder", "source": "ipc.pdf", "page": 0,
                           "score": 0.9, "content_hash": "h1"}],
        "web_results": [],
    }
    with patch("app.api.v1.chat.get_workflow") as mwf:
        g = AsyncMock()
        g.ainvoke = AsyncMock(return_value=mock_state)
        mwf.return_value = g
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/chat", json={"question": "What is 302 IPC?"})
    assert r.status_code == 200
    d = r.json()
    assert len(d["source_chunks"]) == 1
    assert d["source_chunks"][0]["domain"] == "internal"
