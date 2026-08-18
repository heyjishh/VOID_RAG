from __future__ import annotations
from functools import lru_cache
from typing import Optional
import sentence_transformers
from app.config.settings import settings
from app.core.llm.provider import get_llm


class Embedder:
    def __init__(self, model_name: Optional[str] = None):
        self._model = sentence_transformers.SentenceTransformer(
            model_name or settings.EMBED_MODEL
        )
        # Use the new method name (get_embedding_dimension) with fallback
        self._dim = getattr(self._model, "get_embedding_dimension",
                           self._model.get_sentence_embedding_dimension)()

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        """Embed a list of texts (documents/chunks)."""
        return self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        ).tolist()

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query with optional HyDE expansion."""
        if not settings.HYDE_ENABLED:
            return self.embed([query])[0]

        # HyDE: Generate hypothetical document, embed both, average
        try:
            llm = get_llm()
            hyde_prompt = (
                "Write a precise legal passage that directly answers the question. "
                "Include specific statutes, sections, or case names if applicable.\n\n"
                f"Question: {query}\n\nPassage:"
            )
            # Use a quick, deterministic completion for HyDE
            from langchain_core.messages import HumanMessage
            resp = llm.invoke([HumanMessage(content=hyde_prompt)])
            hyde_text = getattr(resp, "content", "") or ""

            if hyde_text.strip():
                vecs = self._model.encode(
                    [query, hyde_text],
                    batch_size=2,
                    show_progress_bar=False,
                    normalize_embeddings=True,
                )
                # Average the query and hypothetical doc embeddings
                return ((vecs[0] + vecs[1]) / 2).tolist()
        except Exception:
            pass

        return self.embed([query])[0]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return Embedder()