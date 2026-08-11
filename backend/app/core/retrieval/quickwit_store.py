from __future__ import annotations
import uuid
import json
import httpx
from app.config.settings import settings
from app.core.ingestion.parser import Chunk
from app.core.retrieval.qdrant_store import ScoredChunk

_INDEX_CONFIG = {
    "version": "0.8",
    "index_id": "juryai_legal",
    "doc_mapping": {
        "field_mappings": [
            {"name": "id", "type": "text", "tokenizer": "raw"},
            {"name": "text", "type": "text", "tokenizer": "en_stem", "record": "position"},
            {"name": "source", "type": "text", "tokenizer": "raw"},
            {"name": "page", "type": "i64"},
        ]
    },
    "search_settings": {"default_search_fields": ["text"]},
    "indexing_settings": {"commit_timeout_secs": 5},
}


class QuickwitStore:
    def __init__(self, index: str | None = None, url: str | None = None):
        self.index = index or settings.QUICKWIT_INDEX
        self.url = (url or settings.QUICKWIT_URL).rstrip("/")
        self._ensure_index()

    def _ensure_index(self):
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{self.url}/api/v1/indexes/{self.index}")
            if resp.status_code == 404:
                cfg = dict(_INDEX_CONFIG)
                cfg["index_id"] = self.index
                create_resp = client.post(f"{self.url}/api/v1/indexes", json=cfg)
                create_resp.raise_for_status()

    def upsert(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        ndjson = "\n".join(
            json.dumps({
                "id": str(uuid.uuid4()),
                "text": c["text"],
                "source": c["source"],
                "page": c["page"],
            })
            for c in chunks
        )
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{self.url}/api/v1/{self.index}/ingest?commit=force",
                content=ndjson,
                headers={"Content-Type": "application/x-ndjson"},
            )
            resp.raise_for_status()
        return len(chunks)

    def search(self, query: str, top_k: int = 20) -> list[ScoredChunk]:
        if not query.strip():
            return []
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                f"{self.url}/api/v1/{self.index}/search",
                json={"query": query, "max_hits": top_k},
            )
        if resp.status_code != 200:
            return []
        hits = resp.json().get("hits", [])
        max_score = max((h.get("_score", 0) for h in hits), default=1.0) or 1.0
        return [
            {
                "text": h["text"],
                "source": h["source"],
                "page": h["page"],
                "score": float(h.get("_score", 0) / max_score),
            }
            for h in hits
        ]
