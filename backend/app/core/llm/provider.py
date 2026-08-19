from __future__ import annotations
from functools import lru_cache
import json
import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from app.config.settings import settings

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


def _to_openai_messages(messages):
    return [
        {
            "role": "user" if m.type == "human" else ("assistant" if m.type == "ai" else m.type),
            "content": m.content,
        }
        for m in messages
    ]


def _to_anthropic_payload(messages):
    """Anthropic's Messages API takes system prompts separately from the
    user/assistant turn list — pull any system messages out and join them."""
    system_parts = [m.content for m in messages if m.type == "system"]
    turns = [
        {"role": "user" if m.type == "human" else "assistant", "content": m.content}
        for m in messages
        if m.type != "system"
    ]
    return "\n\n".join(system_parts), turns


async def _openai_complete(client: httpx.AsyncClient, provider: dict, messages: list, max_tokens: int | None = None) -> tuple[str, dict]:
    payload: dict = {"model": provider["model"], "messages": messages}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    resp = await client.post(
        f"{provider['base_url']}/chat/completions",
        headers={"Authorization": f"Bearer {provider['api_key']}"} if provider["api_key"] else {},
        json=payload,
    )
    resp.raise_for_status()
    body = resp.json()
    usage = body.get("usage") or {}
    return body["choices"][0]["message"]["content"] or "", _normalize_openai_usage(usage)


async def _openai_stream(client: httpx.AsyncClient, provider: dict, messages: list, max_tokens: int | None = None):
    """Yields (delta_text, usage) — usage is {} until the final usage-only
    chunk (enabled via stream_options.include_usage), which carries no delta."""
    headers = {"Authorization": f"Bearer {provider['api_key']}"} if provider["api_key"] else {}
    payload: dict = {
        "model": provider["model"], "messages": messages, "stream": True,
        "stream_options": {"include_usage": True},
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    async with client.stream(
        "POST",
        f"{provider['base_url']}/chat/completions",
        headers=headers,
        json=payload,
    ) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = line[len("data: "):].strip()
            if data == "[DONE]":
                return
            event = json.loads(data)
            usage = event.get("usage") or {}
            choices = event.get("choices") or []
            delta = choices[0]["delta"].get("content") if choices else None
            if delta or usage:
                yield delta or "", _normalize_openai_usage(usage)


def _normalize_openai_usage(usage: dict) -> dict:
    if not usage:
        return {}
    return {"input_tokens": usage.get("prompt_tokens", 0), "output_tokens": usage.get("completion_tokens", 0)}


async def _anthropic_complete(client: httpx.AsyncClient, provider: dict, messages: list, max_tokens: int | None = None) -> tuple[str, dict]:
    system, turns = _to_anthropic_payload(messages)
    resp = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": provider["api_key"], "anthropic-version": "2023-06-01"},
        json={"model": provider["model"], "max_tokens": max_tokens or 4096, "system": system, "messages": turns},
    )
    resp.raise_for_status()
    body = resp.json()
    blocks = body.get("content", [])
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    usage = body.get("usage") or {}
    return text, {"input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0)}


async def _anthropic_stream(client: httpx.AsyncClient, provider: dict, messages: list, max_tokens: int | None = None):
    """Yields (delta_text, usage) — usage accumulates as Anthropic reports it:
    input_tokens on message_start, output_tokens on message_delta."""
    system, turns = _to_anthropic_payload(messages)
    headers = {"x-api-key": provider["api_key"], "anthropic-version": "2023-06-01"}
    payload = {"model": provider["model"], "max_tokens": max_tokens or 4096, "system": system, "messages": turns, "stream": True}
    usage: dict = {}
    async with client.stream("POST", "https://api.anthropic.com/v1/messages", headers=headers, json=payload) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[len("data: "):].strip())
            etype = event.get("type")
            if etype == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta" and delta.get("text"):
                    yield delta["text"], {}
            elif etype == "message_start":
                input_tokens = event.get("message", {}).get("usage", {}).get("input_tokens")
                if input_tokens is not None:
                    usage["input_tokens"] = input_tokens
                    yield "", dict(usage)
            elif etype == "message_delta":
                output_tokens = event.get("usage", {}).get("output_tokens")
                if output_tokens is not None:
                    usage["output_tokens"] = output_tokens
                    yield "", dict(usage)


class DirectApiChat(BaseChatModel):
    """Calls each configured provider's HTTP API directly (Groq primary, with
    fallbacks) — no litellm indirection. OpenAI-compatible providers (Groq,
    the local gateway, Mistral, OpenAI, Ollama) share one calling path since
    they all speak the same chat/completions dialect; Anthropic's Messages
    API has its own request/response shape."""

    @property
    def _llm_type(self) -> str:
        return "direct-api"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise NotImplementedError("Use async")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        chain = settings.llm_provider_chain
        last_exc = None
        max_tokens = kwargs.get("max_tokens")
        base_timeout = kwargs.get("timeout", 30.0)
        for provider in chain:
            timeout = httpx.Timeout(base_timeout, connect=5.0)
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    if provider["kind"] == "anthropic":
                        text, usage = await _anthropic_complete(client, provider, messages, max_tokens=max_tokens)
                    else:
                        text, usage = await _openai_complete(client, provider, _to_openai_messages(messages), max_tokens=max_tokens)
                    return ChatResult(generations=[ChatGeneration(message=AIMessage(
                        content=text,
                        response_metadata={
                            "model_provider": provider["provider_name"], "model_name": provider["model"],
                            "usage": usage,
                        },
                    ))])
            except Exception as exc:
                last_exc = exc
                continue
        raise RuntimeError(f"All LLM providers failed. Last error: {last_exc}")

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        chain = settings.llm_provider_chain
        last_exc = None
        max_tokens = kwargs.get("max_tokens")
        stream_timeout = kwargs.get("timeout", 600.0)
        for provider in chain:
            timeout = httpx.Timeout(stream_timeout, connect=5.0)
            meta = {"model_provider": provider["provider_name"], "model_name": provider["model"]}
            try:
                got_chunk = False
                async with httpx.AsyncClient(timeout=timeout) as client:
                    if provider["kind"] == "anthropic":
                        gen = _anthropic_stream(client, provider, messages, max_tokens=max_tokens)
                    else:
                        gen = _openai_stream(client, provider, _to_openai_messages(messages), max_tokens=max_tokens)
                    async for delta, usage in gen:
                        got_chunk = True
                        chunk_meta = {**meta, "usage": usage} if usage else meta
                        yield ChatGenerationChunk(message=AIMessageChunk(content=delta, response_metadata=chunk_meta))
                if got_chunk:
                    return
            except Exception as exc:
                last_exc = exc
                continue
        # Every provider's streamed request failed outright (seen in practice with
        # free-tier gateways whose streaming path is flakier than their plain
        # completion path — the gateway serves a full non-streamed reply fine but
        # drops the connection mid-stream). Fall back to one non-streamed call and
        # simulate token chunks from it, rather than surfacing a hard failure that
        # the verifier gate would then have to regenerate/block around.
        result = await self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
        message = result.generations[0].message
        words = message.content.split(" ") if message.content else []
        for i, word in enumerate(words):
            token = word if i == len(words) - 1 else word + " "
            yield ChatGenerationChunk(message=AIMessageChunk(content=token, response_metadata=message.response_metadata))


@lru_cache(maxsize=1)
def get_llm() -> DirectApiChat:
    return DirectApiChat()
