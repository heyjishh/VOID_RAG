import numpy as np
from unittest.mock import MagicMock, patch, AsyncMock
from app.core.retrieval.embedder import Embedder


def test_embedder_shape():
    with patch("sentence_transformers.SentenceTransformer") as MockST:
        m = MagicMock()
        m.encode.return_value = np.zeros((2, 384))
        MockST.return_value = m
        emb = Embedder(model_name="test")
        result = emb.embed(["a", "b"])
    assert len(result) == 2 and len(result[0]) == 384


def test_qdrant_store_search_maps_payload():
    with patch("app.core.retrieval.qdrant_store.QdrantClient") as MockQC:
        client = MagicMock()
        MockQC.return_value = client
        client.collection_exists.return_value = True
        from qdrant_client.models import ScoredPoint
        hit = ScoredPoint(
            id="1", version=1, score=0.95,
            payload={"text": "murder", "source": "ipc.pdf", "page": 0},
            vector=None,
        )
        query_response = MagicMock()
        query_response.points = [hit]
        client.query_points.return_value = query_response
        from app.core.retrieval.qdrant_store import QdrantStore
        store = QdrantStore(collection="test", url="http://localhost:6333")
        results = store.search([0.1] * 384, top_k=5)
    assert results[0]["text"] == "murder"
    assert results[0]["score"] == 0.95


def test_quickwit_search_parses_response():
    import httpx
    from app.core.retrieval.quickwit_store import QuickwitStore
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "hits": [
            {"text": "Section 302", "source": "ipc.pdf", "page": 0, "_score": 1.2}
        ]
    }
    mock_get = MagicMock()
    mock_get.status_code = 200  # index exists, skip creation
    with patch("httpx.Client.get", return_value=mock_get), \
         patch("httpx.Client.post", return_value=mock_response):
        store = QuickwitStore(index="test", url="http://localhost:7280")
        results = store.search("murder", top_k=5)
    assert results[0]["text"] == "Section 302"
