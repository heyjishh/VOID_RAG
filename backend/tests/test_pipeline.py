"""End-to-end tests for the dual-domain RAG pipeline.

Tests cover:
1. route_and_retrieve — legal_chunks populated when internal retrieval is mocked
2. merge_evidence — internal premium applied; authoritative web types exempt from
   penalty; items sorted by final_score descending; deduplication by content_hash
3. evidence_merge_node — writes merged_evidence to state; appends reasoning step
4. Full streaming workflow (mocked) — 3-node graph path
"""
from __future__ import annotations

import asyncio
import hashlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.graph.evidence_merger import merge_evidence
from app.core.graph.nodes import evidence_merge_node, legal_retrieve_node, web_search_node
from app.core.graph.workflow import route_and_retrieve


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk(text: str, source: str = "ipc.pdf", page: int = 1, score: float = 0.9,
                authority_score: float = 0.8) -> dict:
    return {
        "text": text,
        "source": source,
        "page": page,
        "score": score,
        "authority_score": authority_score,
    }


def _make_web_ev(url: str = "https://example.com", title: str = "Example",
                 content: str = "web content", score: float = 0.5,
                 authority_score: float = 0.7,
                 source_type: str = "legal_news") -> dict:
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
    return {
        "title": title,
        "url": url,
        "content": content,
        "score": score,
        "authority_score": authority_score,
        "source_type": source_type,
        "published_at": "",
        "retrieved_at": "",
        "content_hash": content_hash,
        "citation_id": "web-0",
    }


def _base_state(**overrides) -> dict:
    state = {
        "question": "What is murder under IPC?",
        "history": [],
        "intent": "",
        "legal_chunks": [],
        "web_results": [],
        "citations": [],
        "answer": "",
        "error": None,
        "reasoning_steps": [],
        "web_evidence": [],
        "merged_evidence": [],
        "use_web_search": False,
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# merge_evidence unit tests
# ---------------------------------------------------------------------------

class _FakeSettings:
    INTERNAL_CORPUS_PREMIUM = 1.2
    WEB_CORPUS_PENALTY = 0.8
    EVIDENCE_MIN_SCORE = 0.35


_settings = _FakeSettings()


def test_merge_evidence_internal_premium_applied():
    """Internal chunks get their authority_score multiplied by INTERNAL_CORPUS_PREMIUM."""
    chunk = _make_chunk("Murder is defined here", authority_score=0.8)
    result = merge_evidence([chunk], [], _settings)
    assert len(result) == 1
    expected_score = 0.8 * 1.2
    assert abs(result[0]["final_score"] - expected_score) < 1e-9
    assert result[0]["domain"] == "internal"


def test_merge_evidence_web_penalty_applied():
    """Non-authoritative web evidence gets authority_score multiplied by WEB_CORPUS_PENALTY."""
    ev = _make_web_ev(source_type="legal_news", authority_score=0.7)
    result = merge_evidence([], [ev], _settings)
    assert len(result) == 1
    expected_score = 0.7 * 0.8
    assert abs(result[0]["final_score"] - expected_score) < 1e-9
    assert result[0]["domain"] == "web"


def test_merge_evidence_authoritative_web_no_penalty():
    """Supreme court / statute / constitutional / government / high court web sources skip the penalty."""
    for src_type in (
        "supreme_court_judgment",
        "statute",
        "constitutional",
        "government_notification",
        "high_court_judgment",
    ):
        ev = _make_web_ev(
            url=f"https://sci.gov.in/{src_type}",
            content=f"content-{src_type}",
            source_type=src_type,
            authority_score=0.9,
        )
        result = merge_evidence([], [ev], _settings)
        assert len(result) == 1, f"Expected 1 item for source_type={src_type}"
        assert abs(result[0]["final_score"] - 0.9) < 1e-9, (
            f"Authoritative web type {src_type} should not be penalised"
        )


def test_merge_evidence_sorted_descending():
    """Items are returned sorted by final_score descending."""
    chunk_low = _make_chunk("Low priority", authority_score=0.3, score=0.3)
    chunk_high = _make_chunk("High priority", authority_score=0.9, score=0.9)
    result = merge_evidence([chunk_low, chunk_high], [], _settings)
    assert result[0]["final_score"] >= result[1]["final_score"]


def test_merge_evidence_deduplication_keeps_highest():
    """When two items share a content_hash, the one with higher final_score wins."""
    content = "shared legal text"
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    # Internal chunk with medium score
    chunk = _make_chunk(content, authority_score=0.5)
    chunk["content_hash"] = content_hash

    # Web evidence with same hash but after penalty: 0.4 * 0.8 = 0.32 < 0.5 * 1.2 = 0.6
    ev = _make_web_ev(content=content, authority_score=0.4, source_type="forum")
    ev["content_hash"] = content_hash

    result = merge_evidence([chunk], [ev], _settings)
    # Only 1 item should remain (the internal one with higher final_score)
    assert len(result) == 1
    assert result[0]["domain"] == "internal"


def test_merge_evidence_top_10_limit():
    """Output is capped at 10 items."""
    chunks = [_make_chunk(f"text-{i}", authority_score=0.5 + i * 0.01) for i in range(15)]
    result = merge_evidence(chunks, [], _settings)
    assert len(result) <= 10


def test_merge_evidence_domain_tagged():
    """Every returned item has a 'domain' key of 'internal' or 'web'."""
    chunk = _make_chunk("legal text")
    ev = _make_web_ev(content="unique web text")
    result = merge_evidence([chunk], [ev], _settings)
    for item in result:
        assert item["domain"] in ("internal", "web"), f"Unexpected domain: {item['domain']}"


def test_merge_evidence_drops_items_below_min_score():
    """A low-scoring, unclassifiable web item is dropped rather than surviving
    purely because a top-10 slot was otherwise empty."""
    good = _make_chunk("Murder is defined here", authority_score=0.8)
    junk = _make_web_ev(
        content="unrelated forum chatter", authority_score=0.15, source_type="unknown"
    )
    # junk final_score = 0.15 * 0.8 = 0.12, below EVIDENCE_MIN_SCORE (0.35)
    result = merge_evidence([good], [junk], _settings)
    assert len(result) == 1
    assert result[0]["domain"] == "internal"


def test_merge_evidence_min_score_boundary_is_inclusive():
    """An item scoring exactly EVIDENCE_MIN_SCORE is kept, not dropped."""
    ev = _make_web_ev(authority_score=_settings.EVIDENCE_MIN_SCORE / _settings.WEB_CORPUS_PENALTY,
                       source_type="legal_news")
    result = merge_evidence([], [ev], _settings)
    assert len(result) == 1


def test_merge_evidence_tags_superseded_statute_after_transition():
    """A chunk citing the Indian Penal Code is tagged superseded_by BNS when
    as_of_date is after the 2024-07-01 transition."""
    chunk = _make_chunk("Under the Indian Penal Code, murder is Section 302", authority_score=0.8)
    result = merge_evidence([chunk], [], _settings, as_of_date="2024-08-01")
    assert result[0]["superseded_by"] == "Bharatiya Nyaya Sanhita"


def test_merge_evidence_no_tag_before_transition():
    """Same chunk, but as_of_date is before the transition — old law still valid."""
    chunk = _make_chunk("Under the Indian Penal Code, murder is Section 302", authority_score=0.8)
    result = merge_evidence([chunk], [], _settings, as_of_date="2024-01-01")
    assert "superseded_by" not in result[0]


def test_merge_evidence_no_tag_when_as_of_date_omitted():
    """Backward compatible: omitting as_of_date never adds superseded_by."""
    chunk = _make_chunk("Under the Indian Penal Code, murder is Section 302", authority_score=0.8)
    result = merge_evidence([chunk], [], _settings)
    assert "superseded_by" not in result[0]


# ---------------------------------------------------------------------------
# evidence_merge_node tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_evidence_merge_node_writes_merged_evidence():
    """evidence_merge_node populates state['merged_evidence']."""
    chunk = _make_chunk("IPC section text", authority_score=0.85)
    ev = _make_web_ev(content="web evidence text", authority_score=0.6)
    state = _base_state(legal_chunks=[chunk], web_evidence=[ev])
    # Real settings are fine here (INTERNAL_CORPUS_PREMIUM=1.2 by default)
    result = await evidence_merge_node(state)
    assert "merged_evidence" in result
    assert isinstance(result["merged_evidence"], list)
    assert len(result["merged_evidence"]) >= 1


@pytest.mark.asyncio
async def test_evidence_merge_node_appends_reasoning_step():
    """evidence_merge_node appends 'evidence_merged' to reasoning_steps."""
    state = _base_state(legal_chunks=[_make_chunk("text")], reasoning_steps=[
        {"step": "internal_retrieval_done", "detail": "1 chunks retrieved from corpus"}
    ])
    result = await evidence_merge_node(state)
    steps = result["reasoning_steps"]
    step_names = [s["step"] for s in steps]
    assert "evidence_merged" in step_names

    merged_step = next(s for s in steps if s["step"] == "evidence_merged")
    assert "ranked by authority" in merged_step["detail"]


# ---------------------------------------------------------------------------
# legal_retrieve_node tests (mocked retrieval)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_legal_retrieve_node_populates_legal_chunks():
    """legal_retrieve_node returns legal_chunks from mocked hybrid_search + reranker.

    QdrantStore and QuickwitStore are bypassed by passing qdrant/quickwit directly
    as parameters — the node only instantiates them when they are None.
    """
    fake_chunks = [
        _make_chunk("Section 302 IPC defines murder", authority_score=0.9),
        _make_chunk("Punishment for murder is life imprisonment", authority_score=0.85),
    ]

    mock_reranker = MagicMock()
    mock_reranker.rerank.return_value = fake_chunks

    # hybrid_search is imported at module level in nodes.py, so patch there.
    # get_reranker is also at module level.
    # qdrant/quickwit are passed directly so no need to patch QdrantStore.
    with patch("app.core.graph.nodes.hybrid_search", return_value=fake_chunks), \
         patch("app.core.graph.nodes.get_reranker", return_value=mock_reranker):
        state = _base_state()
        result = await legal_retrieve_node(state, qdrant=MagicMock(), quickwit=MagicMock())

    assert "legal_chunks" in result
    assert len(result["legal_chunks"]) == 2
    assert result["legal_chunks"][0]["text"] == "Section 302 IPC defines murder"


@pytest.mark.asyncio
async def test_legal_retrieve_node_appends_reasoning_steps():
    """legal_retrieve_node adds internal_retrieval_start and _done reasoning steps."""
    fake_chunks = [_make_chunk("text")]
    mock_reranker = MagicMock()
    mock_reranker.rerank.return_value = fake_chunks

    with patch("app.core.graph.nodes.hybrid_search", return_value=fake_chunks), \
         patch("app.core.graph.nodes.get_reranker", return_value=mock_reranker):
        state = _base_state()
        result = await legal_retrieve_node(state, qdrant=MagicMock(), quickwit=MagicMock())

    step_names = [s["step"] for s in result["reasoning_steps"]]
    assert "internal_retrieval_start" in step_names
    assert "internal_retrieval_done" in step_names


# ---------------------------------------------------------------------------
# route_and_retrieve integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_route_and_retrieve_legal_chunks_populated():
    """route_and_retrieve returns legal_chunks when internal retrieval is mocked."""
    fake_chunks = [
        _make_chunk("Section 302 IPC text", authority_score=0.9),
        _make_chunk("Bail provisions text", authority_score=0.8),
    ]
    fake_legal_result = {
        "legal_chunks": fake_chunks,
        "reasoning_steps": [
            {"step": "internal_retrieval_start", "detail": "Searching internal legal corpus"},
            {"step": "internal_retrieval_done", "detail": "2 chunks retrieved from corpus"},
        ],
    }
    # Patch the node as referenced inside workflow.py (where route_and_retrieve lives)
    with patch("app.core.graph.workflow.legal_retrieve_node", AsyncMock(return_value=fake_legal_result)):
        state = _base_state(question="What is Section 302 IPC?", use_web_search=False)
        result = await route_and_retrieve(state)

    assert "legal_chunks" in result
    assert len(result["legal_chunks"]) == 2
    assert result.get("intent") in ("legal", "web", "both")


@pytest.mark.asyncio
async def test_route_and_retrieve_no_web_search_when_flag_false():
    """route_and_retrieve skips web_search_node when use_web_search=False."""
    fake_legal_result = {
        "legal_chunks": [_make_chunk("legal text")],
        "reasoning_steps": [
            {"step": "internal_retrieval_start", "detail": "start"},
            {"step": "internal_retrieval_done", "detail": "done"},
        ],
    }
    mock_web_node = AsyncMock()
    with patch("app.core.graph.workflow.legal_retrieve_node", AsyncMock(return_value=fake_legal_result)), \
         patch("app.core.graph.workflow.web_search_node", mock_web_node):
        state = _base_state(use_web_search=False)
        await route_and_retrieve(state)

    mock_web_node.assert_not_called()


@pytest.mark.asyncio
async def test_route_and_retrieve_web_search_triggered_when_flag_true():
    """route_and_retrieve calls web_search_node when use_web_search=True."""
    fake_legal_result = {
        "legal_chunks": [_make_chunk("legal text")],
        "reasoning_steps": [
            {"step": "internal_retrieval_start", "detail": "start"},
            {"step": "internal_retrieval_done", "detail": "done"},
        ],
    }
    fake_web = [_make_web_ev()]
    fake_web_result = {
        "web_evidence": fake_web,
        "web_results": fake_web,
        "reasoning_steps": [
            {"step": "web_search_start", "detail": "start"},
            {"step": "web_search_done", "detail": "1 web sources retrieved"},
        ],
    }
    with patch("app.core.graph.workflow.legal_retrieve_node", AsyncMock(return_value=fake_legal_result)), \
         patch("app.core.graph.workflow.web_search_node", AsyncMock(return_value=fake_web_result)):
        state = _base_state(use_web_search=True)
        result = await route_and_retrieve(state)

    assert len(result.get("web_evidence", [])) == 1


@pytest.mark.asyncio
async def test_route_and_retrieve_reasoning_steps_merged_from_parallel_tasks():
    """reasoning_steps from both parallel tasks are concatenated in the result."""
    fake_legal_result = {
        "legal_chunks": [_make_chunk("text")],
        "reasoning_steps": [
            {"step": "internal_retrieval_start", "detail": "Searching internal legal corpus"},
            {"step": "internal_retrieval_done", "detail": "1 chunks retrieved from corpus"},
        ],
    }
    fake_web = [_make_web_ev()]
    fake_web_result = {
        "web_evidence": fake_web,
        "web_results": fake_web,
        "reasoning_steps": [
            {"step": "web_search_start", "detail": "Searching web for current legal information"},
            {"step": "web_search_done", "detail": "1 web sources retrieved"},
        ],
    }
    with patch("app.core.graph.workflow.legal_retrieve_node", AsyncMock(return_value=fake_legal_result)), \
         patch("app.core.graph.workflow.web_search_node", AsyncMock(return_value=fake_web_result)):
        state = _base_state(use_web_search=True)
        result = await route_and_retrieve(state)

    step_names = [s["step"] for s in result.get("reasoning_steps", [])]
    assert "internal_retrieval_start" in step_names
    assert "internal_retrieval_done" in step_names
    assert "web_search_start" in step_names
    assert "web_search_done" in step_names
