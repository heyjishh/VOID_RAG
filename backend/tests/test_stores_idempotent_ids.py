import json
from unittest.mock import MagicMock, patch

from app.core.retrieval.qdrant_store import QdrantStore
from app.core.retrieval.quickwit_store import QuickwitStore


def _bare_qdrant_store():
    """Construct without running __init__ (which talks to a real Qdrant server) —
    upsert() only touches self._client and self._embedder."""
    store = QdrantStore.__new__(QdrantStore)
    store.collection = "test"
    store._client = MagicMock()
    store._embedder = MagicMock()
    store._embedder.embed.side_effect = lambda texts: [[0.1, 0.2] for _ in texts]
    return store


def test_qdrant_upsert_id_is_deterministic_for_same_chunk():
    store = _bare_qdrant_store()
    chunk = {"text": "Section 302 IPC punishes murder.", "source": "ipc.pdf", "page": 5}

    store.upsert([chunk])
    first_id = store._client.upsert.call_args.kwargs["points"][0].id

    store.upsert([chunk])
    second_id = store._client.upsert.call_args.kwargs["points"][0].id

    assert first_id == second_id


def test_qdrant_upsert_id_differs_for_different_content():
    store = _bare_qdrant_store()
    store.upsert([{"text": "Text A", "source": "a.pdf", "page": 1}])
    id_a = store._client.upsert.call_args.kwargs["points"][0].id

    store.upsert([{"text": "Text B", "source": "a.pdf", "page": 1}])
    id_b = store._client.upsert.call_args.kwargs["points"][0].id

    assert id_a != id_b


def _upsert_quickwit_and_capture(chunk):
    store = QuickwitStore.__new__(QuickwitStore)
    store.index = "test"
    store.url = "http://fake"

    captured = {}

    def fake_post(url, content=None, **kwargs):
        captured["ndjson"] = content
        return MagicMock(raise_for_status=lambda: None)

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.post.side_effect = fake_post

    with patch("app.core.retrieval.quickwit_store.httpx.Client", return_value=mock_client):
        store.upsert([chunk])

    return json.loads(captured["ndjson"])["id"]


def test_quickwit_upsert_id_is_deterministic_for_same_chunk():
    chunk = {"text": "Section 302 IPC punishes murder.", "source": "ipc.pdf", "page": 5}
    assert _upsert_quickwit_and_capture(chunk) == _upsert_quickwit_and_capture(chunk)
