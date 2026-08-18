from __future__ import annotations
from app.core.retrieval.qdrant_store import ScoredChunk, QdrantStore
from app.core.retrieval.quickwit_store import QuickwitStore
from app.core.retrieval.embedder import get_embedder
from app.core.retrieval.colbert_reranker import get_colbert_reranker
from app.config.settings import settings

RRF_K = 50  # Lower = more vector influence (was 60)
COLBERT_WEIGHT = 0.3  # Weight for ColBERT scores in final fusion


def reciprocal_rank_fusion(
    ranked_lists: list[list[ScoredChunk]], top_k: int = 20,
) -> list[ScoredChunk]:
    rrf: dict[str, float] = {}
    chunk_map: dict[str, ScoredChunk] = {}
    for lst in ranked_lists:
        for rank, chunk in enumerate(lst):
            key = f"{chunk['source']}::{chunk['page']}::{chunk['text'][:50]}"
            rrf[key] = rrf.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)
            chunk_map[key] = chunk
    top = sorted(rrf.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [{**chunk_map[k], "score": round(s, 6)} for k, s in top]


def _normalize_scores(chunks: list[ScoredChunk]) -> list[ScoredChunk]:
    """Min-max normalize scores to [0,1] for fair fusion."""
    if not chunks:
        return chunks
    scores = [c.get("score", 0.0) for c in chunks]
    min_s, max_s = min(scores), max(scores)
    if max_s <= min_s:
        return chunks
    for c in chunks:
        c["score"] = (c.get("score", 0.0) - min_s) / (max_s - min_s)
    return chunks


def _fuse_scores(
    vector_chunks: list[ScoredChunk],
    bm25_chunks: list[ScoredChunk],
    colbert_chunks: list[ScoredChunk] | None,
    top_k: int,
) -> list[ScoredChunk]:
    """Fuse vector, BM25, and optional ColBERT scores via weighted RRF."""
    # Normalize each list's scores
    vector_chunks = _normalize_scores(vector_chunks)
    bm25_chunks = _normalize_scores(bm25_chunks)
    if colbert_chunks:
        colbert_chunks = _normalize_scores(colbert_chunks)

    # Combine all unique chunks
    all_chunks: dict[str, ScoredChunk] = {}
    for c in vector_chunks + bm25_chunks + (colbert_chunks or []):
        key = f"{c['source']}::{c['page']}::{c['text'][:50]}"
        if key not in all_chunks:
            all_chunks[key] = c

    # Weighted score fusion
    fused = []
    for chunk in all_chunks.values():
        v_score = chunk.get("score", 0.0)
        # Start with vector score
        fused_score = v_score

        # Add BM25 component if present
        bm25_match = next((c for c in bm25_chunks
                          if f"{c['source']}::{c['page']}::{c['text'][:50]}" ==
                             f"{chunk['source']}::{chunk['page']}::{chunk['text'][:50]}"), None)
        if bm25_match:
            fused_score = 0.6 * fused_score + 0.4 * bm25_match.get("score", 0.0)

        # Add ColBERT component if present
        if colbert_chunks:
            colbert_match = next((c for c in colbert_chunks
                                 if f"{c['source']}::{c['page']}::{c['text'][:50]}" ==
                                    f"{chunk['source']}::{chunk['page']}::{chunk['text'][:50]}"), None)
            if colbert_match:
                fused_score = (1 - COLBERT_WEIGHT) * fused_score + COLBERT_WEIGHT * colbert_match.get("score", 0.0)

        fused.append({**chunk, "score": fused_score})

    return sorted(fused, key=lambda x: x["score"], reverse=True)[:top_k]


def _fuse_scores_intent(
    vector_chunks: list[ScoredChunk],
    bm25_chunks: list[ScoredChunk],
    colbert_chunks: list[ScoredChunk] | None,
    top_k: int,
    alpha: float = 0.6,
) -> list[ScoredChunk]:
    """Fuse vector, BM25, and optional ColBERT scores with intent-aware weights."""
    vector_chunks = _normalize_scores(vector_chunks)
    bm25_chunks = _normalize_scores(bm25_chunks)
    if colbert_chunks:
        colbert_chunks = _normalize_scores(colbert_chunks)

    all_chunks: dict[str, ScoredChunk] = {}
    for c in vector_chunks + bm25_chunks + (colbert_chunks or []):
        key = f"{c['source']}::{c['page']}::{c['text'][:50]}"
        if key not in all_chunks:
            all_chunks[key] = c

    fused = []
    for chunk in all_chunks.values():
        v_score = chunk.get("score", 0.0)
        fused_score = alpha * v_score

        bm25_match = next((c for c in bm25_chunks
                          if f"{c['source']}::{c['page']}::{c['text'][:50]}" ==
                             f"{chunk['source']}::{chunk['page']}::{chunk['text'][:50]}"), None)
        if bm25_match:
            fused_score += (1 - alpha) * bm25_match.get("score", 0.0)

        if colbert_chunks:
            colbert_match = next((c for c in colbert_chunks
                                 if f"{c['source']}::{c['page']}::{c['text'][:50]}" ==
                                    f"{chunk['source']}::{chunk['page']}::{chunk['text'][:50]}"), None)
            if colbert_match:
                fused_score = 0.7 * fused_score + 0.3 * colbert_match.get("score", 0.0)

        fused.append({**chunk, "score": fused_score})

    return sorted(fused, key=lambda x: x["score"], reverse=True)[:top_k]


def hybrid_search(
    query: str,
    top_k: int = 20,
    qdrant: QdrantStore | None = None,
    quickwit: QuickwitStore | None = None,
    intent: str = "unknown",
    source_filter: list[str] | None = None,
) -> list[ScoredChunk]:
    """Hybrid search with vector + BM25 + optional ColBERT late interaction.

    Intent-aware weights:
    - statute_lookup: BM25-heavy (0.3 vector, 0.7 BM25) — exact section matches
    - case_law_search: vector-heavy (0.7 vector, 0.3 BM25) — semantic similarity
    - procedural_query: balanced (0.5 vector, 0.5 BM25)
    - default: standard (0.6 vector, 0.4 BM25)

    source_filter, when given, scopes both legs to just those source
    filenames (as returned by GET /documents) — the answer is then grounded
    only in the documents the user explicitly selected.
    """
    intent = intent or "unknown"
    if intent == "statute_lookup":
        alpha = 0.3
    elif intent in ("case_law_search", "precedent_analysis"):
        alpha = 0.7
    elif intent == "procedural_query":
        alpha = 0.5
    else:
        alpha = 0.6

    # 1. Vector search (with HyDE query expansion)
    embedder = get_embedder()
    query_vec = embedder.embed_query(query)

    vector_chunks: list[ScoredChunk] = []
    if qdrant is not None:
        vector_chunks = qdrant.search(query_vec, top_k=settings.TOP_K_RETRIEVE, source_filter=source_filter)

    # 2. BM25 search
    bm25_chunks: list[ScoredChunk] = []
    if quickwit is not None:
        bm25_chunks = quickwit.search(query, top_k=settings.TOP_K_RETRIEVE, source_filter=source_filter)

    # 3. ColBERT late interaction (second-stage, top-50 candidates)
    colbert_chunks: list[ScoredChunk] | None = None
    if settings.COLBERT_MODEL and (vector_chunks or bm25_chunks):
        candidate_pool = vector_chunks + bm25_chunks
        seen = set()
        unique_candidates = []
        for c in candidate_pool:
            key = f"{c['source']}::{c['page']}::{c['text'][:50]}"
            if key not in seen:
                seen.add(key)
                unique_candidates.append(c)
            if len(unique_candidates) >= settings.COLBERT_TOP_K:
                break

        if unique_candidates:
            colbert = get_colbert_reranker()
            texts = [c["text"] for c in unique_candidates]
            colbert_scores = colbert.score_pairs(query, texts)
            colbert_chunks = [
                {**c, "score": s} for c, s in zip(unique_candidates, colbert_scores)
            ]

    # 4. Fuse all scores with intent-aware weights
    return _fuse_scores_intent(vector_chunks, bm25_chunks, colbert_chunks, top_k, alpha)