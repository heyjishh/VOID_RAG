"""Session-scoped document helpers for the Draft feature.

Thin wrapper around app.core.retrieval.session_store — the same
session-isolated local JSON store the Interact chat feature uses. Drafting
reuses it for house-style exemplars and input documents so an uploaded draft
attachment never touches the shared Qdrant/Quickwit corpus. No new isolation
logic here; session_id validation and the on-disk layout stay owned by
session_store.
"""
from __future__ import annotations

from app.core.retrieval import session_store


def add_session_document(session_id: str, filename: str, data: bytes) -> dict:
    return session_store.add_document(session_id, filename, data)


def remove_session_document(session_id: str, file_hash: str) -> bool:
    return session_store.remove_document(session_id, file_hash)


def search_session_documents(session_id: str, query: str, top_k: int = 20) -> list[dict]:
    return session_store.search(session_id, query, top_k=top_k)


def get_document_text(session_id: str, file_hash: str, max_chars: int = 20_000) -> str:
    """Full text of one uploaded document, chunks joined in stored order.

    ponytail: reaches into session_store._load (module-private, but already
    used directly by tests/test_session_store.py) rather than adding a new
    public accessor there — same JSON-file store, just filtered by
    file_hash instead of ranked by a query. Promote to a public
    session_store.get_document(...) if a second caller needs this.
    """
    store = session_store._load(session_id)
    text = "\n\n".join(c["text"] for c in store["chunks"] if c["file_hash"] == file_hash)
    return text[:max_chars]
