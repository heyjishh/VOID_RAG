import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from app.main import create_app


@pytest.mark.asyncio
async def test_get_run_returns_saved_run():
    app = create_app()
    run_payload = {
        "run_id": "testrun1",
        "conversation_id": "c1",
        "question": "Q?",
        "answer": "A.",
        "citations": [],
        "source_chunks": [],
        "verification": {"verdict": "grounded", "groundedness_score": 0.9},
        "output_format": "CREAC",
        "reasoning_steps": [],
        "intent": "legal",
        "sources_used": 2,
        "created_at": "2026-08-15T00:00:00",
    }
    with patch("app.api.v1.chat.load_run", new_callable=AsyncMock, return_value=run_payload):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/v1/runs/testrun1")
    assert r.status_code == 200
    assert r.json()["run_id"] == "testrun1"


@pytest.mark.asyncio
async def test_get_run_404_when_missing():
    app = create_app()
    with patch("app.api.v1.chat.load_run", new_callable=AsyncMock, return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/v1/runs/missing")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_follow_up_run():
    app = create_app()
    parent = {"run_id": "parent1", "conversation_id": "c1", "output_format": "CREAC"}
    followup_response = {
        "answer": "Follow-up answer.",
        "citations": [],
        "source_chunks": [],
        "verification": {"verdict": "grounded", "groundedness_score": 1.0},
        "conversation_id": "c1",
        "run_id": "child1",
        "output_format": "CREAC",
        "intent": "legal",
        "sources_used": 1,
        "reasoning_steps": [],
    }
    with patch("app.api.v1.chat.load_run", new_callable=AsyncMock, return_value=parent):
        with patch("app.api.v1.chat._run_enhanced_chat", new_callable=AsyncMock, return_value=followup_response):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                r = await c.post("/api/v1/runs/parent1/followup", json={"question": "Follow-up?", "use_web_search": False})
    assert r.status_code == 200
    assert r.json()["answer"] == "Follow-up answer."


@pytest.mark.asyncio
async def test_source_action_view():
    app = create_app()
    run_payload = {
        "run_id": "r1",
        "source_chunks": [
            {"text": "chunk text", "source": "doc.pdf", "page": 2, "citation_quote": "quote"}
        ],
    }
    with patch("app.api.v1.chat.load_run", new_callable=AsyncMock, return_value=run_payload):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/runs/r1/sources/0/actions", json={"action": "view"})
    assert r.status_code == 200
    assert r.json()["chunk"]["text"] == "chunk text"


@pytest.mark.asyncio
async def test_source_action_copy_citation():
    app = create_app()
    run_payload = {
        "run_id": "r1",
        "source_chunks": [
            {"text": "chunk text", "source": "doc.pdf", "page": 2, "citation_quote": "quote"}
        ],
    }
    with patch("app.api.v1.chat.load_run", new_callable=AsyncMock, return_value=run_payload):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/runs/r1/sources/0/actions", json={"action": "copy_citation"})
    assert r.status_code == 200
    assert "quote" in r.json()["citation"]


@pytest.mark.asyncio
async def test_source_action_download():
    app = create_app()
    run_payload = {
        "run_id": "r1",
        "source_chunks": [
            {"text": "download me", "source": "my_doc", "page": 0}
        ],
    }
    with patch("app.api.v1.chat.load_run", new_callable=AsyncMock, return_value=run_payload):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/runs/r1/sources/0/actions", json={"action": "download"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert r.text == "download me"


@pytest.mark.asyncio
async def test_source_action_404_on_bad_index():
    app = create_app()
    run_payload = {"run_id": "r1", "source_chunks": []}
    with patch("app.api.v1.chat.load_run", new_callable=AsyncMock, return_value=run_payload):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/runs/r1/sources/5/actions", json={"action": "view"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_run_source():
    app = create_app()
    run_payload = {
        "run_id": "r1",
        "source_chunks": [
            {"text": "chunk one", "source": "doc.pdf", "page": 2},
            {"text": "chunk two", "source": "doc2.pdf", "page": 5},
        ],
    }
    with patch("app.api.v1.chat.load_run", new_callable=AsyncMock, return_value=run_payload):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/v1/runs/r1/source/0")
    assert r.status_code == 200
    assert r.json()["text"] == "chunk one"


@pytest.mark.asyncio
async def test_get_run_source_404():
    app = create_app()
    run_payload = {"run_id": "r1", "source_chunks": []}
    with patch("app.api.v1.chat.load_run", new_callable=AsyncMock, return_value=run_payload):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/v1/runs/r1/source/0")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_run_source_file():
    app = create_app()
    run_payload = {
        "run_id": "r1",
        "source_chunks": [
            {"text": "file content", "source": "my_doc", "page": 0},
        ],
    }
    with patch("app.api.v1.chat.load_run", new_callable=AsyncMock, return_value=run_payload):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/v1/runs/r1/source/0/file")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert r.text == "file content"


@pytest.mark.asyncio
async def test_source_action_read_chunk():
    app = create_app()
    run_payload = {
        "run_id": "r1",
        "source_chunks": [
            {"text": "read me", "source": "doc.pdf", "page": 1},
        ],
    }
    with patch("app.api.v1.chat.load_run", new_callable=AsyncMock, return_value=run_payload):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/runs/r1/sources/0/actions", json={"action": "read_chunk"})
    assert r.status_code == 200
    assert r.json()["text"] == "read me"


@pytest.mark.asyncio
async def test_source_action_copy_chunk():
    app = create_app()
    run_payload = {
        "run_id": "r1",
        "source_chunks": [
            {"text": "copy me", "source": "doc.pdf", "page": 1},
        ],
    }
    with patch("app.api.v1.chat.load_run", new_callable=AsyncMock, return_value=run_payload):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/runs/r1/sources/0/actions", json={"action": "copy_chunk"})
    assert r.status_code == 200
    assert r.json()["text"] == "copy me"


@pytest.mark.asyncio
async def test_source_action_open_window():
    app = create_app()
    run_payload = {
        "run_id": "r1",
        "source_chunks": [
            {"text": "text", "source": "doc.pdf", "page": 1, "url": "http://example.com/doc"},
        ],
    }
    with patch("app.api.v1.chat.load_run", new_callable=AsyncMock, return_value=run_payload):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/runs/r1/sources/0/actions", json={"action": "open_window"})
    assert r.status_code == 200
    assert r.json()["url"] == "http://example.com/doc"


@pytest.mark.asyncio
async def test_download_run_returns_pdf():
    app = create_app()
    run_payload = {
        "run_id": "r1",
        "question": "Q?",
        "answer": "A.",
        "citations": [],
        "source_chunks": [],
        "verification": {"verdict": "grounded", "groundedness_score": 0.9},
    }
    with patch("app.api.v1.chat.load_run", new_callable=AsyncMock, return_value=run_payload):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/runs/r1/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith('attachment; filename="run-r1.pdf"')


@pytest.mark.asyncio
async def test_download_run_404_when_missing():
    app = create_app()
    with patch("app.api.v1.chat.load_run", new_callable=AsyncMock, return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/runs/missing/download")
    assert r.status_code == 404
