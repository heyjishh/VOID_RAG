from __future__ import annotations
from functools import lru_cache
from sentence_transformers import CrossEncoder
from app.config.settings import settings
from app.core.retrieval.qdrant_store import ScoredChunk
from app.core.retrieval.authority_scorer import get_authority_scorer, temporal_relevance


class Reranker:
    def __init__(
        self,
        model_name: str | None = None,
        prefilter_top_k: int | None = None,
        enable_cache: bool = True,
    ):
        # Small cross-encoder (22M params) — 5x faster than bge-reranker-v2-m3
        self._model = CrossEncoder(
            model_name or settings.RERANKER_MODEL,
            max_length=settings.RERANKER_MAX_LENGTH,
        )
        self._batch_size = settings.RERANKER_BATCH_SIZE
        # Pre-filter: only cross-encode top N from initial retrieval (default 15 of 20)
        self._prefilter_top_k = prefilter_top_k or min(15, settings.TOP_K_RETRIEVE)
        self._enable_cache = enable_cache
        self._cache: dict[str, list[float]] = {} if enable_cache else None

    def _truncate(self, text: str) -> str:
        """Rough pre-truncation to the token budget (~3.6 chars/token)."""
        budget = settings.RERANKER_MAX_LENGTH * 4
        return text if len(text) <= budget else text[:budget]

    def _prefilter(self, chunks: list[ScoredChunk]) -> list[ScoredChunk]:
        """Pre-filter chunks by initial retrieval score to reduce cross-encoder calls."""
        if len(chunks) <= self._prefilter_top_k:
            return chunks
        # Sort by initial retrieval score (vector similarity) descending
        return sorted(chunks, key=lambda c: c.get("score", 0.0), reverse=True)[:self._prefilter_top_k]

    def _make_cache_key(self, query: str, texts: list[str]) -> str:
        """Create a cache key for query+texts combination."""
        import hashlib
        content = query + "\x00" + "\x00".join(texts)
        return hashlib.md5(content.encode()).hexdigest()

    def score_pairs(self, query: str, texts: list[str]) -> list[float]:
        """Raw cross-encoder relevance scores for (query, text) pairs."""
        if not texts:
            return []

        if self._enable_cache:
            key = self._make_cache_key(query, texts)
            if key in self._cache:
                return self._cache[key]

        pairs = [[query, self._truncate(t)] for t in texts]
        scores = [float(s) for s in self._model.predict(pairs, batch_size=self._batch_size)]

        if self._enable_cache:
            self._cache[key] = scores
            # Simple cache size limit
            if len(self._cache) > 128:
                # Remove oldest entries (simple FIFO)
                keys_to_remove = list(self._cache.keys())[:-64]
                for k in keys_to_remove:
                    del self._cache[k]

        return scores

    def rerank(
        self,
        query: str,
        chunks: list[ScoredChunk],
        top_k: int | None = None,
        as_of_date: str | None = None,
    ) -> list[ScoredChunk]:
        if not chunks:
            return []
        top_k = top_k or settings.TOP_K_FINAL

        # Pre-filter by initial retrieval score to reduce cross-encoder calls
        chunks_to_rerank = self._prefilter(chunks)

        scores = self.score_pairs(query, [c["text"] for c in chunks_to_rerank])
        ranked = sorted(zip(chunks_to_rerank, scores), key=lambda x: x[1], reverse=True)[:top_k]

        scorer = get_authority_scorer()
        scorer.build_graph([c for c, _ in ranked])
        result: list[ScoredChunk] = []
        for c, s in ranked:
            authority_score = scorer.score(c, query_relevance=s)
            if as_of_date:
                authority_score *= temporal_relevance(c["text"], as_of_date)
            result.append({**c, "score": s, "authority_score": authority_score})
        return result


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    return Reranker()