from __future__ import annotations
from functools import lru_cache
import sentence_transformers
from app.config.settings import settings


class Embedder:
    def __init__(self, model_name: str | None = None):
        self._model = sentence_transformers.SentenceTransformer(model_name or settings.EMBED_MODEL)

    def embed(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        return self._model.encode(
            texts, batch_size=batch_size,
            show_progress_bar=False, normalize_embeddings=True,
        ).tolist()


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return Embedder()
