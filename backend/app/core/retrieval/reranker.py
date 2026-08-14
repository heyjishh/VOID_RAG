from __future__ import annotations
from functools import lru_cache
from sentence_transformers import CrossEncoder
from app.config.settings import settings
from app.core.retrieval.qdrant_store import ScoredChunk
from app.core.retrieval.authority_scorer import get_authority_scorer


class Reranker:
    def __init__(self, model_name: str | None = None):
        # max_length caps the cross-encoder context at RERANKER_MAX_LENGTH
        # tokens per pair — without it the tokenizer defaults to the model's
        # 8192-token window, which costs minutes of CPU inference for web
        # evidence. Ranking long legal text only needs a faithful window,
        # not the full document.
        self._model = CrossEncoder(
            model_name or settings.RERANKER_MODEL,
            max_length=settings.RERANKER_MAX_LENGTH,
        )
        self._batch_size = settings.RERANKER_BATCH_SIZE

    def _truncate(self, text: str) -> str:
        """Rough pre-truncation to the token budget (~3.6 chars/token).

        Keeps the raw text for citation/evidence, but ranking only reads the
        leading window, cutting CPU time ~8× on multi-hundred-KB documents.
        """
        budget = settings.RERANKER_MAX_LENGTH * 4
        return text if len(text) <= budget else text[:budget]

    def score_pairs(self, query: str, texts: list[str]) -> list[float]:
        """Raw cross-encoder relevance scores for (query, text) pairs, in
        input order. Shared by `rerank()` and by callers (e.g. web search)
        that need genuine semantic relevance without the authority-scoring
        and top_k truncation `rerank()` also does.
        """
        if not texts:
            return []
        pairs = [[query, self._truncate(t)] for t in texts]
        return [float(s) for s in self._model.predict(pairs, batch_size=self._batch_size)]

    def rerank(self, query: str, chunks: list[ScoredChunk], top_k: int | None = None) -> list[ScoredChunk]:
        if not chunks:
            return []
        top_k = top_k or settings.TOP_K_FINAL
        scores = self.score_pairs(query, [c["text"] for c in chunks])
        ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)[:top_k]
        scorer = get_authority_scorer()
        result: list[ScoredChunk] = []
        for c, s in ranked:
            authority_score = scorer.score(c, query_relevance=s)
            result.append({**c, "score": s, "authority_score": authority_score})
        return result


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    return Reranker()
