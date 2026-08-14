from app.core.retrieval.hybrid import reciprocal_rank_fusion
from app.core.retrieval.citation import derive_citations, cited_indices
from app.api.v1.chat import _build_source_chunks, _source_chunks_from_evidence
from unittest.mock import patch, MagicMock


def test_rrf_boosts_shared_items():
    list1 = [
        {"text": "murder", "source": "a.pdf", "page": 0, "score": 0.9},
        {"text": "theft", "source": "b.pdf", "page": 0, "score": 0.7},
    ]
    list2 = [
        {"text": "murder", "source": "a.pdf", "page": 0, "score": 0.85},
        {"text": "fraud", "source": "c.pdf", "page": 0, "score": 0.6},
    ]
    merged = reciprocal_rank_fusion([list1, list2], top_k=4)
    assert merged[0]["text"] == "murder"
    assert len(merged) == 3  # murder, theft, fraud


def test_citation_verified_when_claim_grounds_matching_content_hash():
    evidence = [{
        "text": "life imprisonment or death is the punishment for murder",
        "source": "ipc.pdf", "page": 5, "score": 0.9, "content_hash": "hash-murder",
    }]
    verification = {
        "supported_claims": [
            {"claim": "Murder is punishable by life imprisonment or death.", "content_hash": "hash-murder"}
        ],
    }
    results = derive_citations(verification, evidence)
    assert any(r["verified"] for r in results)


def test_citation_unverified_when_no_claim_references_content_hash():
    evidence = [{
        "text": "contract requires offer and acceptance",
        "source": "law.pdf", "page": 0, "score": 0.7, "content_hash": "hash-contract",
    }]
    verification = {"supported_claims": []}
    results = derive_citations(verification, evidence)
    assert all(not r["verified"] for r in results)


def test_citation_cited_reflects_bracket_marker_independent_of_verified():
    """A chunk can be cited ([N] appears in the answer) without being verified
    (no supported_claims reference its content_hash), and vice versa."""
    evidence = [
        {"text": "cited but ungrounded", "source": "a.pdf", "page": 0, "content_hash": "h1"},
        {"text": "grounded but never cited", "source": "b.pdf", "page": 0, "content_hash": "h2"},
    ]
    verification = {"supported_claims": [{"claim": "x", "content_hash": "h2"}]}
    results = derive_citations(verification, evidence, answer="Only [1] is mentioned here.")

    assert results[0]["cited"] is True and results[0]["verified"] is False
    assert results[1]["cited"] is False and results[1]["verified"] is True
    assert cited_indices(results) == {1}


def test_citation_cited_defaults_false_without_answer_text():
    evidence = [{"text": "x", "source": "a.pdf", "page": 0, "content_hash": "h1"}]
    results = derive_citations({"supported_claims": []}, evidence)
    assert results[0]["cited"] is False


def test_reranker_orders_by_cross_encoder_score():
    import numpy as np
    with patch("app.core.retrieval.reranker.CrossEncoder") as MockCE:
        m = MagicMock()
        MockCE.return_value = m
        m.predict.return_value = np.array([0.2, 0.9, 0.1])
        from app.core.retrieval.reranker import Reranker
        r = Reranker(model_name="test")
        chunks = [
            {"text": "contract", "source": "a.pdf", "page": 0, "score": 0.8},
            {"text": "Section 302 punishment", "source": "b.pdf", "page": 1, "score": 0.6},
            {"text": "civil law", "source": "c.pdf", "page": 0, "score": 0.5},
        ]
        result = r.rerank("punishment under 302", chunks, top_k=2)
    assert result[0]["source"] == "b.pdf"
    assert len(result) == 2


def test_build_source_chunks_hardcodes_internal_domain():
    """legal_chunks never carry a 'domain' key (pre-merge) — _build_source_chunks
    must still tag every SourceChunkOut as domain='internal'."""
    result = {
        "legal_chunks": [
            {"text": "murder is defined here", "source": "ipc.pdf", "page": 5, "score": 0.9},
        ],
        "citations": [],
    }
    chunks, _ = _build_source_chunks(result)
    assert len(chunks) == 1
    assert chunks[0].domain == "internal"


def test_source_chunks_from_evidence_forwards_domain_per_item():
    """_source_chunks_from_evidence must forward each item's own 'domain', not
    a single hardcoded value — proving mixed internal/web evidence splits
    correctly for the frontend's Internal vs WEB SOURCES panels."""
    evidence = [
        {"text": "internal statute text", "source": "ipc.pdf", "page": 1, "score": 0.9,
         "domain": "internal"},
        {"text": "web article text", "source": "https://example.com/article", "page": 0,
         "score": 0.6, "domain": "web"},
    ]
    chunks = _source_chunks_from_evidence(evidence, set())
    by_domain = {c.source: c.domain for c in chunks}
    assert by_domain["ipc.pdf"] == "internal"
    assert by_domain["https://example.com/article"] == "web"
    assert {c.domain for c in chunks} == {"internal", "web"}


def test_source_chunks_from_evidence_defaults_to_internal_when_domain_absent():
    """Callers passing pre-merge evidence (no 'domain' key) get 'internal',
    matching the legacy POST /chat path where legal_chunks is internal-only."""
    evidence = [{"text": "text", "source": "ipc.pdf", "page": 0, "score": 0.5}]
    chunks = _source_chunks_from_evidence(evidence, set())
    assert chunks[0].domain == "internal"


def test_source_chunks_from_evidence_index_survives_dropped_items():
    """A [N] marker in the answer maps to citations[N-1], where citations is
    derived from the same `evidence` list with no items skipped. But
    _source_chunks_from_evidence DOES skip empty-text items, so the frontend's
    array position for a chunk can drift from N-1 once an earlier item is
    dropped. `index` must carry the item's true 1-based position in `evidence`
    so the frontend can key off it instead of array position, or the citation
    linking silently points at the wrong SourceCard."""
    evidence = [
        {"text": "first", "source": "a.pdf", "page": 0, "score": 0.9},
        {"text": "", "source": "b.pdf", "page": 0, "score": 0.8},  # dropped
        {"text": "third", "source": "c.pdf", "page": 0, "score": 0.7},
    ]
    chunks = _source_chunks_from_evidence(evidence, set())
    assert len(chunks) == 2
    assert [c.index for c in chunks] == [1, 3]


def test_build_source_chunks_index_survives_dropped_items():
    """Same contract as _source_chunks_from_evidence, for the legacy
    _build_source_chunks path (used by the legal_chunks-only fallback)."""
    result = {
        "legal_chunks": [
            {"text": "first", "source": "a.pdf", "page": 0, "score": 0.9},
            {"text": "", "source": "b.pdf", "page": 0, "score": 0.8},  # dropped
            {"text": "third", "source": "c.pdf", "page": 0, "score": 0.7},
        ],
        "citations": [],
    }
    chunks, _ = _build_source_chunks(result)
    assert len(chunks) == 2
    assert [c.index for c in chunks] == [1, 3]
