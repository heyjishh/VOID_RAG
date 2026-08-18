import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from langchain_core.messages import HumanMessage

from app.core.llm.provider import DirectApiChat

_RealAsyncClient = httpx.AsyncClient


def _openai_chain(name="groq"):
    return [{"kind": "openai", "provider_name": name, "base_url": "https://fake/v1", "api_key": "k", "model": "m"}]


def _sse(*data_lines: str) -> bytes:
    return ("".join(f"data: {d}\n\n" for d in data_lines)).encode()


@pytest.mark.asyncio
async def test_agenerate_parses_openai_response():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})

    with patch("app.core.llm.provider.settings", SimpleNamespace(llm_provider_chain=_openai_chain())):
        with patch("httpx.AsyncClient", lambda **kw: _RealAsyncClient(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != "transport"})):
            result = await DirectApiChat()._agenerate([HumanMessage(content="hi")])

    msg = result.generations[0].message
    assert msg.content == "hello"
    assert msg.response_metadata["model_provider"] == "groq"


@pytest.mark.asyncio
async def test_astream_yields_multiple_openai_chunks():
    body = _sse(
        json.dumps({"choices": [{"delta": {"content": "Hel"}}]}),
        json.dumps({"choices": [{"delta": {"content": "lo"}}]}),
        "[DONE]",
    )

    def handler(request):
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    with patch("app.core.llm.provider.settings", SimpleNamespace(llm_provider_chain=_openai_chain())):
        with patch("httpx.AsyncClient", lambda **kw: _RealAsyncClient(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != "transport"})):
            chunks = [c async for c in DirectApiChat()._astream([HumanMessage(content="hi")])]

    assert [c.message.content for c in chunks] == ["Hel", "lo"]


@pytest.mark.asyncio
async def test_astream_falls_back_to_agenerate_when_streaming_fails():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if request.url.path.endswith("/chat/completions") and b'"stream": true' in request.content:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "one two three"}}]})

    with patch("app.core.llm.provider.settings", SimpleNamespace(llm_provider_chain=_openai_chain())):
        with patch("httpx.AsyncClient", lambda **kw: _RealAsyncClient(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != "transport"})):
            chunks = [c.message.content async for c in DirectApiChat()._astream([HumanMessage(content="hi")])]

    assert "".join(chunks) == "one two three"
    assert len(chunks) == 3  # word-simulated streaming from the fallback


@pytest.mark.asyncio
async def test_agenerate_falls_back_to_next_provider_on_failure():
    chain = [
        {"kind": "openai", "provider_name": "groq", "base_url": "https://fake/v1", "api_key": "k", "model": "m"},
        {"kind": "openai", "provider_name": "gateway", "base_url": "https://fake2/v1", "api_key": "k2", "model": "m2"},
    ]

    def handler(request):
        if "fake/v1" in str(request.url):
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "from gateway"}}]})

    with patch("app.core.llm.provider.settings", SimpleNamespace(llm_provider_chain=chain)):
        with patch("httpx.AsyncClient", lambda **kw: _RealAsyncClient(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k != "transport"})):
            result = await DirectApiChat()._agenerate([HumanMessage(content="hi")])

    assert result.generations[0].message.content == "from gateway"
    assert result.generations[0].message.response_metadata["model_provider"] == "gateway"
