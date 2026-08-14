"""Tests POST /api/v1/draft (app.api.v1.draft) — direct-generation drafting."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import create_app


def _mock_llm(content: str) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=resp)
    return llm


@pytest.mark.asyncio
async def test_draft_returns_generated_document():
    app = create_app()
    llm = _mock_llm("# Reply to Notice\n\nDear Sir/Madam, ...")

    with patch("app.api.v1.draft.get_llm", return_value=llm):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/v1/draft", json={"brief": "reply to a legal notice from X"})

    assert r.status_code == 200
    assert r.json()["content"] == "# Reply to Notice\n\nDear Sir/Madam, ..."
    llm.ainvoke.assert_awaited_once()
    prompt = llm.ainvoke.await_args.args[0][0].content
    assert "reply to a legal notice from X" in prompt


@pytest.mark.asyncio
async def test_draft_rejects_empty_brief():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/draft", json={"brief": "   "})

    assert r.status_code == 400
