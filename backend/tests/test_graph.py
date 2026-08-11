import pytest
from unittest.mock import AsyncMock, patch
from app.core.graph.intent import classify_intent
from app.core.graph.nodes import legal_retrieve_node, verify_answer_node, web_search_node
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

    async def fake_search(question, max_results=5):
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
        def rerank(self, question, chunks, top_k):
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
