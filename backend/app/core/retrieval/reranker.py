from __future__ import annotations
from functools import lru_cache
from sentence_transformers import CrossEncoder
from app.config.settings import settings
from app.core.retrieval.qdrant_store import ScoredChunk
from app.core.retrieval.authority_scorer import get_authority_scorer


class Reranker:
    def __init__(self, model_name: str | None = None):
        self._model = CrossEncoder(model_name or settings.RERANKER_MODEL)

    def rerank(self, query: str, chunks: list[ScoredChunk], top_k: int | None = None) -> list[ScoredChunk]:
        if not chunks:
            return []
        top_k = top_k or settings.TOP_K_FINAL
        scores = self._model.predict([[query, c["text"]] for c in chunks])
        ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)[:top_k]
        scorer = get_authority_scorer()
        result: list[ScoredChunk] = []
        for c, s in ranked:
            rerank_score = float(s)
            authority_score = scorer.score(c, query_relevance=rerank_score)
            result.append({**c, "score": rerank_score, "authority_score": authority_score})
        return result


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    return Reranker()
