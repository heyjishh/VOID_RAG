import pytest
from unittest.mock import AsyncMock, patch
from app.core.graph.intent import classify_intent
from app.core.graph.nodes import (
    generate_answer_node,
    legal_retrieve_node,
    verify_answer_node,
    web_search_node,
)
from app.core.retrieval.citation import derive_citations
from app.core.graph.workflow import get_workflow


_MIXED_MERGED = [
    {"text": "Section 302 IPC defines murder.", "source": "ipc.pdf", "page": 12,
     "domain": "internal", "content_hash": "int-hash-1"},
    {"title": "Live Law", "url": "https://livelaw.in/x", "content": "SC ruling text",
     "domain": "web", "content_hash": "web-hash-1"},
]


def test_intent_legal_keywords():
    assert classify_intent("What is the punishment under Section 302 IPC?") == "legal"
    assert classify_intent("Define cognizable offence under CrPC") == "legal"


def test_intent_web_no_legal_terms():
    assert classify_intent("What happened in the Supreme Court yesterday?") in ("web", "both")


def test_intent_fast(benchmark):
    benchmark(classify_intent, "Section 302 IPC murder punishment India")


def test_intent_returns_valid_value():
    for q in ["What is bail?", "latest news", "contract act 1872"]:
        assert classify_intent(q) in ("legal", "web", "both")


# ---------------------------------------------------------------------------
# Legacy workflow wiring — retrieve -> merge -> answer -> verify
# ---------------------------------------------------------------------------

def test_get_workflow_wires_merge_node_between_retrieve_and_answer():
    """The legacy POST /chat graph must run evidence_merge_node, mirroring the
    streaming graph, so verify_answer_node always receives merged_evidence."""
    get_workflow.cache_clear()
    graph = get_workflow()
    node_names = set(graph.get_graph().nodes.keys())
    assert "merge" in node_names


# ---------------------------------------------------------------------------
# verify_answer_node — must use full merged evidence, not internal-only
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_answer_node_numbers_evidence_by_merged_position():
    """The answer prompt labels each evidence item with a fixed [N] keyed to its
    1-based position in merged_evidence — the same order derive_citations() uses —
    so [N] in the answer maps to citations[N-1]. The old verbose "[Source: ...]"
    form must be gone."""
    state = {
        "question": "What is the punishment for murder?",
        "history": [],
        "merged_evidence": _MIXED_MERGED,
        "streaming": True,  # store the prompt, skip the LLM call
    }
    result = await generate_answer_node(state)
    prompt = result["answer_prompt"]

    assert "[1] ipc.pdf p.12" in prompt      # merged[0] (internal) → [1]
    assert "[2] Live Law" in prompt          # merged[1] (web)      → [2]
    assert "[Source:" not in prompt

    # [N] must line up with citations[N-1] derived from the same evidence list.
    verification = {"supported_claims": [{"claim": "murder", "content_hash": "int-hash-1"}]}
    citations = derive_citations(verification, _MIXED_MERGED)
    assert citations[0]["source"] == "ipc.pdf"          # [1]
    assert citations[1]["content_hash"] == "web-hash-1"  # [2]
    # citations[N-1]["index"] must equal N — the explicit field the frontend
    # keys off, independent of citations[] never being reordered/filtered today.
    assert citations[0]["index"] == 1
    assert citations[1]["index"] == 2


@pytest.mark.asyncio
async def test_verify_answer_node_passes_full_mixed_domain_evidence():
    """Regression test: verify_answer_node used to filter merged_evidence down
    to domain == "internal" before calling verify_answer, silently discarding
    web evidence. It must now forward the full merged list."""
    captured: dict = {}

    async def fake_verify(answer, evidence):
        captured["evidence"] = evidence
        return {
            "groundedness_score": 0.9, "verdict": "grounded",
            "supported_claims": [], "unsupported_claims": [], "summary": "",
        }

    with patch("app.core.graph.verifier.verify_answer", fake_verify):
        await verify_answer_node({"answer": "some answer", "merged_evidence": _MIXED_MERGED})

    domains = {item.get("domain") for item in captured["evidence"]}
    assert domains == {"internal", "web"}


@pytest.mark.asyncio
async def test_verify_answer_node_falls_back_to_legal_chunks_when_unmerged():
    """Callers/tests that never populate merged_evidence (e.g. mocked graphs)
    must still work via the legacy legal_chunks fallback."""
    captured: dict = {}

    async def fake_verify(answer, evidence):
        captured["evidence"] = evidence
        return {
            "groundedness_score": 0.9, "verdict": "grounded",
            "supported_claims": [], "unsupported_claims": [], "summary": "",
        }

    legal_chunks = [{"text": "murder", "source": "ipc.pdf", "page": 0, "content_hash": "h1"}]
    with patch("app.core.graph.verifier.verify_answer", fake_verify):
        await verify_answer_node({"answer": "some answer", "legal_chunks": legal_chunks})

    assert captured["evidence"] == legal_chunks


# ---------------------------------------------------------------------------
# on_step live callback — required so the SSE layer can emit reasoning_step
# events the moment each node reaches that point, instead of only after the
# whole graph.ainvoke() resolves (the retroactive-burst bug).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_web_search_node_invokes_on_step_for_start_before_search_runs():
    """web_search_start must fire via on_step before web_search() is awaited,
    and web_search_done only after it returns — proving the callback reports
    progress live rather than being reconstructable only from the final
    reasoning_steps list."""
    observed: list[dict] = []

    async def fake_search(question, max_results=5, on_step=None):
        assert [s["step"] for s in observed] == ["web_search_start"], (
            "web_search_start must have already fired via on_step before "
            "web_search() runs"
        )
        return []

    with patch("app.core.graph.nodes.web_search", fake_search):
        await web_search_node({"question": "q", "on_step": observed.append})

    assert [s["step"] for s in observed] == ["web_search_start", "web_search_done"]


@pytest.mark.asyncio
async def test_legal_retrieve_node_invokes_on_step_for_start_and_done():
    observed: list[dict] = []

    class _FakeReranker:
        def rerank(self, question, chunks, top_k, as_of_date=None):
            assert [s["step"] for s in observed] == ["internal_retrieval_start"], (
                "internal_retrieval_start must fire before retrieval runs"
            )
            return []

    with patch("app.core.graph.nodes.hybrid_search", lambda *a, **k: []), \
         patch("app.core.graph.nodes.get_reranker", lambda: _FakeReranker()):
        await legal_retrieve_node(
            {"question": "q", "on_step": observed.append}, qdrant=object(), quickwit=object()
        )

    assert [s["step"] for s in observed] == [
        "internal_retrieval_start", "internal_retrieval_done",
    ]


@pytest.mark.asyncio
async def test_nodes_are_on_step_optional_and_do_not_error_when_absent():
    """State dicts without on_step (e.g. the legacy non-streaming path) must
    still work — the callback is opt-in, never required."""
    with patch("app.core.graph.nodes.web_search", AsyncMock(return_value=[])):
        result = await web_search_node({"question": "q"})
    assert result["web_evidence"] == []


# ---------------------------------------------------------------------------
# Interact feature — scoped retrieval (searches ONLY the current session's
# uploaded documents, never the global Qdrant/Quickwit corpus).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_interact_retrieve_node_searches_session_store_scoped_to_session():
    from app.core.graph.nodes import interact_retrieve_node

    captured: dict = {}

    def fake_search(session_id, query, top_k=20):
        captured["session_id"] = session_id
        captured["query"] = query
        return [{"text": "your clause", "source": "my_upload.pdf", "page": 0, "score": 0.9}]

    class _FakeReranker:
        def rerank(self, question, chunks, top_k, as_of_date=None):
            return chunks

    with patch("app.core.retrieval.session_store.search", fake_search), \
         patch("app.core.graph.nodes.get_reranker", lambda: _FakeReranker()):
        result = await interact_retrieve_node(
            {"question": "what does clause 4 say?", "session_id": "sess-123"}
        )

    assert captured == {"session_id": "sess-123", "query": "what does clause 4 say?"}
    assert result["legal_chunks"][0]["source"] == "my_upload.pdf"


@pytest.mark.asyncio
async def test_interact_retrieve_node_invokes_on_step_for_start_and_done():
    observed: list[dict] = []

    class _FakeReranker:
        def rerank(self, question, chunks, top_k, as_of_date=None):
            assert [s["step"] for s in observed] == ["internal_retrieval_start"]
            return []

    with patch("app.core.retrieval.session_store.search", lambda *a, **k: []), \
         patch("app.core.graph.nodes.get_reranker", lambda: _FakeReranker()):
        from app.core.graph.nodes import interact_retrieve_node
        await interact_retrieve_node(
            {"question": "q", "session_id": "s1", "on_step": observed.append}
        )

    assert [s["step"] for s in observed] == [
        "internal_retrieval_start", "internal_retrieval_done",
    ]


@pytest.mark.asyncio
async def test_route_and_retrieve_interact_mode_skips_web_search_even_if_requested():
    """Interact mode must stay scoped strictly to the session's own uploads —
    it must never fan out to web search, even when use_web_search=True."""
    from app.core.graph.workflow import route_and_retrieve

    interact_mock = AsyncMock(return_value={"legal_chunks": [], "reasoning_steps": []})
    legal_mock = AsyncMock(return_value={"legal_chunks": [], "reasoning_steps": []})
    web_mock = AsyncMock(return_value={"web_evidence": [], "web_results": [], "reasoning_steps": []})

    with patch("app.core.graph.workflow.interact_retrieve_node", interact_mock), \
         patch("app.core.graph.workflow.legal_retrieve_node", legal_mock), \
         patch("app.core.graph.workflow.web_search_node", web_mock):
        await route_and_retrieve({
            "question": "q", "mode": "interact", "session_id": "s1", "use_web_search": True,
        })

    interact_mock.assert_called_once()
    legal_mock.assert_not_called()
    web_mock.assert_not_called()


@pytest.mark.asyncio
async def test_route_and_retrieve_ask_mode_uses_legal_retrieve_not_interact():
    """Regression: default (ask) mode must keep using legal_retrieve_node —
    adding interact mode must not change the default global-corpus path."""
    from app.core.graph.workflow import route_and_retrieve

    interact_mock = AsyncMock(return_value={"legal_chunks": [], "reasoning_steps": []})
    legal_mock = AsyncMock(return_value={"legal_chunks": [], "reasoning_steps": []})

    with patch("app.core.graph.workflow.interact_retrieve_node", interact_mock), \
         patch("app.core.graph.workflow.legal_retrieve_node", legal_mock):
        await route_and_retrieve({"question": "q", "use_web_search": False})

    legal_mock.assert_called_once()
    interact_mock.assert_not_called()


@pytest.mark.asyncio
async def test_evidence_merge_node_tags_session_domain_in_interact_mode():
    """merge_evidence always tags legal_chunks-derived items 'internal'; in
    interact mode these came from session_store, not the shared S3 corpus, so
    evidence_merge_node must relabel them 'session' or the frontend's document
    viewer 404s trying to fetch them from S3. Web items must stay 'web'."""
    from app.core.graph.nodes import evidence_merge_node

    state = {
        "mode": "interact",
        "legal_chunks": [{"text": "my clause", "source": "upload.pdf", "page": 0, "score": 0.9}],
        "web_evidence": [
            {"content": "web text", "title": "t", "url": "http://x", "source_type": "news", "authority_score": 0.9}
        ],
    }
    result = await evidence_merge_node(state)

    domains = {item["domain"] for item in result["merged_evidence"]}
    assert domains == {"session", "web"}


@pytest.mark.asyncio
async def test_evidence_merge_node_keeps_internal_domain_in_ask_mode():
    """Regression: default (ask) mode must not be affected by the interact
    domain relabeling."""
    from app.core.graph.nodes import evidence_merge_node

    state = {
        "legal_chunks": [{"text": "ipc text", "source": "ipc.pdf", "page": 0, "score": 0.9}],
        "web_evidence": [],
    }
    result = await evidence_merge_node(state)

    assert all(item["domain"] == "internal" for item in result["merged_evidence"])


def test_answer_format_instructions_differ_by_output_format():
    """CREAC/IRAC/BRIEF must each produce distinct, correctly-shaped section-header
    instructions — regression guard for output_format silently not affecting generation."""
    from app.core.graph.nodes import answer_format_instructions

    creac = answer_format_instructions("CREAC")
    irac = answer_format_instructions("IRAC")
    brief = answer_format_instructions("BRIEF")

    assert len({creac, irac, brief}) == 3
    for header in ("Conclusion", "Rule", "Explanation", "Application"):
        assert header in creac
    for header in ("Issue", "Rule", "Application", "Conclusion"):
        assert header in irac
    assert "##" not in brief
    # unknown/missing format falls back to CREAC rather than raising
    assert answer_format_instructions("bogus") == creac
    assert answer_format_instructions(None) == creac
