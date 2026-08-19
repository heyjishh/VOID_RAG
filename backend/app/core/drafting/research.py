"""Research retrieval for the Draft feature.

Runs the same pipeline as /ask: internal corpus hybrid search + web search
in parallel, then merges via evidence_merger (authority-scored, deduplicated,
top-N). The prompt builder receives a unified list of chunks tagged with
domain=internal or domain=web so it can cite both.
"""
from __future__ import annotations

import asyncio

from app.config.settings import settings
from app.core.graph.evidence_merger import ensure_content_hashes, merge_evidence
from app.core.graph.nodes import _build_web_query
from app.core.retrieval.hybrid import hybrid_search
from app.core.retrieval.reranker import get_reranker
from app.core.web_search.searcher import web_search


async def _corpus_search(query: str, sources: list[str] | None) -> list[dict]:
    from app.core.retrieval.qdrant_store import QdrantStore
    from app.core.retrieval.quickwit_store import QuickwitStore

    def _sync():
        chunks = hybrid_search(
            query, top_k=settings.TOP_K_RETRIEVE * 2,
            qdrant=QdrantStore(), quickwit=QuickwitStore(),
        )
        if sources:
            chunks = [c for c in chunks if c.get("source") in sources]
        return get_reranker().rerank(query, chunks, top_k=settings.TOP_K_FINAL * 2)

    return ensure_content_hashes(await asyncio.to_thread(_sync))


async def _web_research(query: str) -> list[dict]:
    web_query = _build_web_query(query, "legal")
    results = await web_search(web_query, max_results=settings.WEB_SEARCH_MAX_RESULTS)
    return results


def _to_prompt_chunks(merged: list[dict]) -> list[dict]:
    """Normalise merged evidence into the shape build_draft_prompt expects."""
    out = []
    for item in merged:
        if item.get("domain") == "web":
            out.append({
                "text": item.get("content", ""),
                "source": item.get("title") or item.get("url", "web"),
                "page": 0,
                "score": item.get("final_score", 0.0),
                "content_hash": item.get("content_hash", ""),
                "domain": "web",
                "url": item.get("url", ""),
            })
        else:
            out.append({
                "text": item.get("text", ""),
                "source": item.get("source", ""),
                "page": item.get("page", 0),
                "score": item.get("final_score", 0.0),
                "content_hash": item.get("content_hash", ""),
                "domain": "internal",
            })
    return out


async def research_for_draft(query: str, sources: list[str] | None = None) -> list[dict]:
    """Corpus + web search, merged and authority-scored — same pipeline as /ask."""
    corpus_chunks, web_evidence = await asyncio.gather(
        _corpus_search(query, sources),
        _web_research(query),
    )

    merged = merge_evidence(corpus_chunks, web_evidence, settings)
    return _to_prompt_chunks(merged)
