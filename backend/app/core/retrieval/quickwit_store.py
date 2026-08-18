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
                # Same content-addressed id scheme as QdrantStore.upsert, for a
                # consistent identity across both stores. Note: Quickwit's
                # ingest API is append-only — a matching id does not overwrite
                # an existing doc the way Qdrant's upsert does, so a re-ingest
                # still needs an explicit delete-by-id first to avoid
                # duplicates here specifically.
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{c['source']}|{c['page']}|{c['text']}")),
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

    def search(
        self, query: str, top_k: int = 20, source_filter: list[str] | None = None
    ) -> list[ScoredChunk]:
        if not query.strip():
            return []
        # Quickwit's query language needs per-field phrase escaping to filter
        # server-side; source filenames carry arbitrary punctuation (quotes,
        # apostrophes) that makes that escaping error-prone. Instead: pull a
        # wider candidate pool and filter in Python — exact, no injection
        # risk, and cheap since a handful of selected sources is the common
        # case.
        fetch_k = top_k * 4 if source_filter else top_k
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                f"{self.url}/api/v1/{self.index}/search",
                json={"query": query, "max_hits": fetch_k},
            )
        if resp.status_code != 200:
            return []
        hits = resp.json().get("hits", [])
        if source_filter:
            allowed = set(source_filter)
            hits = [h for h in hits if h["source"] in allowed]
        hits = hits[:top_k]
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
