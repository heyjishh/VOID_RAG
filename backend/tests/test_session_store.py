import pytest

from app.config.settings import settings
from app.core.retrieval import session_store


class _FakeEmbedder:
    """Deterministic bag-of-words embedder — cosine similarity favors text
    sharing more vocabulary words with the query, good enough to test ranking
    without loading a real sentence-transformers model."""

    _VOCAB = ["murder", "contract", "clause", "punishment", "offer", "acceptance"]

    def embed(self, texts):
        return [self._vec(t) for t in texts]

    def _vec(self, text):
        t = text.lower()
        return [float(t.count(w)) for w in self._VOCAB]


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SESSION_DOC_STORE_DIR", str(tmp_path))
    monkeypatch.setattr(session_store, "get_embedder", lambda: _FakeEmbedder())


def test_add_document_parses_and_stores_chunks():
    result = session_store.add_document("session-a", "notes.txt", b"# Contract\nAn offer must be accepted.")
    assert result["duplicate"] is False
    assert result["chunk_count"] >= 1
    docs = session_store.list_documents("session-a")
    assert docs[0]["filename"] == "notes.txt"
    assert docs[0]["file_hash"] == result["file_hash"]


def test_add_document_is_idempotent_by_content_hash():
    data = b"Section 302 defines the punishment for murder."
    first = session_store.add_document("session-b", "law.txt", data)
    second = session_store.add_document("session-b", "law.txt", data)

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert second["file_hash"] == first["file_hash"]
    assert len(session_store.list_documents("session-b")) == 1

    store = session_store._load("session-b")
    assert len(store["chunks"]) == first["chunk_count"]  # no duplicate chunks appended


def test_reupload_under_different_filename_still_dedupes_on_content():
    data = b"Section 302 defines the punishment for murder."
    session_store.add_document("session-c", "a.txt", data)
    second = session_store.add_document("session-c", "b.txt", data)

    assert second["duplicate"] is True
    assert len(session_store.list_documents("session-c")) == 1


def test_search_is_scoped_to_session_and_ranks_by_relevance():
    session_store.add_document("session-d", "murder.txt", b"Section 302 defines the punishment for murder.")
    session_store.add_document("session-d", "contract.txt", b"An offer must be accepted to form a contract.")
    # Uploaded to a different session — must never leak into session-d's results.
    session_store.add_document("session-e", "other.txt", b"murder murder murder punishment")

    results = session_store.search("session-d", "punishment for murder", top_k=5)

    assert results, "expected at least one match"
    assert results[0]["source"] == "murder.txt"
    assert all(r["source"] != "other.txt" for r in results)


def test_search_empty_session_returns_no_results():
    assert session_store.search("session-empty", "anything") == []


def test_remove_document_deletes_its_chunks():
    record = session_store.add_document("session-f", "notes.txt", b"An offer must be accepted.")

    assert session_store.remove_document("session-f", record["file_hash"]) is True
    assert session_store.list_documents("session-f") == []
    assert session_store.search("session-f", "offer") == []


def test_remove_document_returns_false_for_unknown_hash():
    assert session_store.remove_document("session-g", "not-a-real-hash") is False


def test_invalid_session_id_rejected():
    with pytest.raises(session_store.InvalidSessionId):
        session_store.add_document("../../etc/passwd", "x.txt", b"data")
