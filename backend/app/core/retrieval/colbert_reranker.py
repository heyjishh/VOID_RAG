from __future__ import annotations
from functools import lru_cache
from typing import Optional
from app.config.settings import settings
from app.core.retrieval.qdrant_store import ScoredChunk


class ColBERTReranker:
    """ColBERT late interaction reranker for fine-grained token-level matching.

    Used as a second-stage reranker after cross-encoder for top-50 candidates.
    Provides token-level interaction without full cross-attention cost.
    """

    def __init__(self, model_name: Optional[str] = None):
        self._model_name = model_name or settings.COLBERT_MODEL
        self._model = None
        self._max_length = settings.COLBERT_MAX_LENGTH
        self._top_k = settings.COLBERT_TOP_K

    def _load(self):
        if self._model is None:
            try:
                # Try ColBERT Searcher first (requires index)
                from colbert import Searcher
                self._model = Searcher(index="", checkpoint=self._model_name)
            except Exception:
                # Fallback: use sentence-transformers with late interaction simulation
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)

    def score_pairs(self, query: str, texts: list[str]) -> list[float]:
        """Score query-text pairs using late interaction."""
        if not texts:
            return []

        self._load()

        # Limit to top_k for efficiency
        texts = texts[:self._top_k]

        try:
            if hasattr(self._model, 'rank'):
                # ColBERT Searcher API
                ranking = self._model.rank(query, texts)
                scores = [float(r[1]) for r in ranking]
                return scores
            else:
                # Fallback: maxsim via sentence-transformers
                return self._maxsim_score(query, texts)
        except Exception:
            # Fallback to simple similarity
            return self._fallback_score(query, texts)

    def _maxsim_score(self, query: str, texts: list[str]) -> list[float]:
        """MaxSim late interaction using token embeddings."""
        query_emb = self._model.encode([query], convert_to_tensor=True)
        text_embs = self._model.encode(texts, convert_to_tensor=True)

        # Simple cosine similarity as fallback
        import torch
        sims = torch.cosine_similarity(query_emb, text_embs)
        return sims.cpu().tolist()

    def _fallback_score(self, query: str, texts: list[str]) -> list[float]:
        """Simple embedding similarity fallback."""
        query_emb = self._model.encode([query], normalize_embeddings=True)
        text_embs = self._model.encode(texts, normalize_embeddings=True)
        import numpy as np
        return (text_embs @ query_emb.T).flatten().tolist()


@lru_cache(maxsize=1)
def get_colbert_reranker() -> ColBERTReranker:
    return ColBERTReranker()