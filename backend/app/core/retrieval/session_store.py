"""Per-session document store for the Interact feature.

Interact chat is scoped to ONLY the current user's uploaded documents — kept
fully separate from the global Qdrant/Quickwit corpus so uploading a document
never pollutes another user's (or another session's) /ask search results.

ponytail: linear in-process cosine scan over a JSON file persisted per
session on disk (SESSION_DOC_STORE_DIR). Session corpora are a handful of
user-uploaded documents, so this is simplest-correct; move to sqlite-vec or a
per-session Qdrant collection if a session's corpus grows large enough for a
linear scan to matter.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from app.config.settings import settings
from app.core.ingestion.parser import parse_bytes
from app.core.retrieval.embedder import get_embedder

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class InvalidSessionId(ValueError):
    """Raised when a session_id fails the safe-for-filesystem-path check."""


def _validate_session_id(session_id: str) -> str:
    if not _SESSION_ID_RE.match(session_id or ""):
        raise InvalidSessionId(f"Invalid session_id: {session_id!r}")
    return session_id


def _store_path(session_id: str) -> Path:
    return Path(settings.SESSION_DOC_STORE_DIR) / f"{_validate_session_id(session_id)}.json"


def _load(session_id: str) -> dict:
    path = _store_path(session_id)
    if not path.exists():
        return {"files": {}, "chunks": []}
    return json.loads(path.read_text())


def _save(session_id: str, store: dict) -> None:
    path = _store_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store))


def add_document(session_id: str, filename: str, data: bytes) -> dict:
    """Parse, embed, and add an uploaded file's chunks to a session's store.

    Idempotent: re-uploading bytes already seen in this session (same content
    hash) is a no-op that returns the existing record with duplicate=True
    instead of re-parsing/re-embedding or storing a second copy.
    """
    store = _load(session_id)
    file_hash = hashlib.sha256(data).hexdigest()
    existing = store["files"].get(file_hash)
    if existing is not None:
        return {**existing, "file_hash": file_hash, "duplicate": True}

    chunks = parse_bytes(data, filename)
    vectors = get_embedder().embed([c["text"] for c in chunks]) if chunks else []
    for chunk, vector in zip(chunks, vectors):
        store["chunks"].append({**chunk, "file_hash": file_hash, "vector": vector})

    record = {"filename": filename, "chunk_count": len(chunks)}
    store["files"][file_hash] = record
    _save(session_id, store)
    return {**record, "file_hash": file_hash, "duplicate": False}


def list_documents(session_id: str) -> list[dict]:
    """List uploaded documents for a session (no chunk text/vectors)."""
    store = _load(session_id)
    return [{**record, "file_hash": file_hash} for file_hash, record in store["files"].items()]


def remove_document(session_id: str, file_hash: str) -> bool:
    """Remove one uploaded document (and its chunks) from a session's store."""
    store = _load(session_id)
    if file_hash not in store["files"]:
        return False
    del store["files"][file_hash]
    store["chunks"] = [c for c in store["chunks"] if c["file_hash"] != file_hash]
    _save(session_id, store)
    return True


def clear_session(session_id: str) -> None:
    """Delete a session's entire store (all uploaded documents)."""
    path = _store_path(session_id)
    path.unlink(missing_ok=True)


def _cosine(a: list[float], b: list[float]) -> float:
    # get_embedder() normalizes embeddings, so dot product == cosine similarity.
    return sum(x * y for x, y in zip(a, b))


def search(session_id: str, query: str, top_k: int = 20) -> list[dict]:
    """Return the session's chunks ranked by similarity to ``query``.

    Returns ScoredChunk-shaped dicts (text/source/page/score) — no vectors —
    ready to feed into the same reranker legal_retrieve_node uses.
    """
    store = _load(session_id)
    chunks = store["chunks"]
    if not chunks:
        return []
    query_vector = get_embedder().embed([query])[0]
    scored = [
        {
            "text": c["text"],
            "source": c["source"],
            "page": c["page"],
            "score": _cosine(query_vector, c["vector"]),
        }
        for c in chunks
    ]
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[:top_k]
