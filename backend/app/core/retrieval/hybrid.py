from __future__ import annotations
from app.core.retrieval.qdrant_store import ScoredChunk, QdrantStore
from app.core.retrieval.quickwit_store import QuickwitStore
from app.core.retrieval.embedder import get_embedder

RRF_K = 60


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


def hybrid_search(
    query: str,
    top_k: int = 20,
    qdrant: QdrantStore | None = None,
    quickwit: QuickwitStore | None = None,
) -> list[ScoredChunk]:
    lists = []
    if qdrant is not None:
        vec = get_embedder().embed([query])[0]
        lists.append(qdrant.search(vec, top_k=top_k))
    if quickwit is not None:
        lists.append(quickwit.search(query, top_k=top_k))
    return reciprocal_rank_fusion(lists, top_k=top_k) if lists else []
