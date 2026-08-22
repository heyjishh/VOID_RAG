from __future__ import annotations
import uuid
from typing import TypedDict
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchAny
from app.config.settings import settings
from app.core.retrieval.embedder import get_embedder
from app.core.retrieval.source_type import detect_source_type
from app.core.ingestion.parser import Chunk


class _ScoredChunkRequired(TypedDict):
    text: str
    source: str
    page: int
    score: float


class ScoredChunk(_ScoredChunkRequired, total=False):
    """Scored retrieval result.  ``source_type`` and ``authority_score`` are
    populated by the retrieval/rerank pipeline; absent until then."""
    source_type: str
    authority_score: float


class QdrantStore:
    def __init__(self, collection: str | None = None, url: str | None = None, api_key: str | None = None):
        self.collection = collection or settings.QDRANT_COLLECTION
        self._client = QdrantClient(
            url=url or settings.QDRANT_URL,
            api_key=api_key or settings.QDRANT_API_KEY,
            # Default (None) falls back to a short internal timeout — large
            # Acts (Companies Act 2013, Income-tax Act 1961, etc.) produce
            # big upsert batches whose request body transmission routinely
            # exceeded it under load, failing with httpcore.WriteTimeout on
            # every retry regardless of content, not transient flakiness.
            timeout=60,
        )
        self._embedder = get_embedder()
        self._ensure_collection()

    def _ensure_collection(self):
        expected_size = self._embedder.dimension
        if self._client.collection_exists(self.collection):
            existing = self._client.get_collection(self.collection)
            actual_size = getattr(existing.config.params.vectors, "size", None)
            if actual_size != expected_size:
                import logging
                logging.getLogger("juryai").warning(
                    "Qdrant collection %r has wrong vector size %s; expected %s. Recreating.",
                    self.collection, actual_size, expected_size,
                )
                self._client.delete_collection(self.collection)
                self._clear_manifest()
        if not self._client.collection_exists(self.collection):
            self._client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=expected_size, distance=Distance.COSINE),
            )

    @staticmethod
    def _clear_manifest():
        try:
            from app.core.ingestion.manifest import Manifest
            Manifest().clear()
        except Exception:
            pass

    def upsert(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        vecs = self._embedder.embed([c["text"] for c in chunks])
        points = [
            PointStruct(
                # Content-addressed, not random — re-ingesting the same source
                # (a killed/resumed sync, a re-run over unchanged S3 keys)
                # overwrites the same point instead of piling up duplicates.
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{c['source']}|{c['page']}|{c['text']}")),
                vector=vec,
                payload={"text": c["text"], "source": c["source"], "page": c["page"]},
            )
            for c, vec in zip(chunks, vecs)
        ]
        self._client.upsert(collection_name=self.collection, points=points)
        return len(points)

    def search(
        self, query_vec: list[float], top_k: int = 20, source_filter: list[str] | None = None
    ) -> list[ScoredChunk]:
        query_filter = (
            Filter(must=[FieldCondition(key="source", match=MatchAny(any=source_filter))])
            if source_filter else None
        )
        results = self._client.query_points(
            collection_name=self.collection,
            query=query_vec,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )
        chunks: list[ScoredChunk] = []
        for h in results.points:
            source: str = h.payload["source"]
            chunks.append({
                "text": h.payload["text"],
                "source": source,
                "page": h.payload["page"],
                "score": h.score,
                # Tag with source type from filename (S3 internal doc path)
                "source_type": detect_source_type(url="", filename=source),
                # Authority score is 0.0 here; filled by AuthorityScorer after reranking
                "authority_score": 0.0,
            })
        return chunks
