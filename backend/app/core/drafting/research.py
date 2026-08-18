"""Read-only research retrieval for the Draft feature.

Mirrors app.core.graph.nodes.legal_retrieve_node's hybrid search + rerank
against the shared corpus, optionally narrowed to a caller-given source
allowlist. Never writes to Qdrant/Quickwit and never touches the ingestion
pipeline — retrieval only.
"""
from __future__ import annotations

import asyncio

from app.config.settings import settings
from app.core.graph.evidence_merger import ensure_content_hashes
from app.core.retrieval.hybrid import hybrid_search
from app.core.retrieval.reranker import get_reranker


async def research_for_draft(query: str, sources: list[str] | None = None) -> list[dict]:
    """ScoredChunk-shaped dicts (text/source/page/score/content_hash), reranked.

    ``sources`` — when non-empty — restricts results to chunks whose
    ``source`` filename is in the list, applied before reranking so the
    cross-encoder only scores the caller-narrowed candidate pool.
    """
    from app.core.retrieval.qdrant_store import QdrantStore
    from app.core.retrieval.quickwit_store import QuickwitStore

    def _sync_retrieve():
        chunks = hybrid_search(
            query, top_k=settings.TOP_K_RETRIEVE, qdrant=QdrantStore(), quickwit=QuickwitStore()
        )
        if sources:
            chunks = [c for c in chunks if c.get("source") in sources]
        return get_reranker().rerank(query, chunks, top_k=settings.TOP_K_FINAL)

    return ensure_content_hashes(await asyncio.to_thread(_sync_retrieve))
