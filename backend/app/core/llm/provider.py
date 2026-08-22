from __future__ import annotations
from collections import Counter
from functools import lru_cache
import json
import os
import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from app.config.settings import settings

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


_DEFAULT_JURISDICTION_LABELS: dict[str, str] = {
    "supreme_court_judgment": "Supreme Court of India",
    "high_court_judgment": "High Court",
    "constitutional": "Constitution of India",
    "statute": "Central statute",
    "government_notification": "Government notification",
    "case_doc": "Case document",
    "legal_news": "Legal news",
    "blog": "Commentary/blog",
    "forum": "Forum discussion",
    "unknown": "Unclassified source",
}

_DEFAULT_TUNING_TEMPLATES: dict[str, str] = {
    "web_heavy": (
        "{web_pct}% of the retrieved context comes from web sources rather than the primary "
        "corpus. Lean on statutory/precedential text where it exists and flag any claim that "
        "rests only on secondary web commentary."
    ),
    "low_authority": (
        "The retrieved sources are low-authority on average (mean authority {authority_mean}). "
        "Be conservative — state conclusions as tentative and surface the weak evidentiary basis "
        "instead of overstating certainty."
    ),
    "high_authority": (
        "The retrieved sources are high-authority (mean authority {authority_mean}), dominated by "
        "{dominant_label}. Quote the primary text directly and reason from it."
    ),
    "single_type": (
        "{dominant_pct}% of the context is {dominant_label}. Tailor the analysis to that source "
        "type and note explicitly if a fuller answer would need other kinds of authority "
        "(e.g. case law vs. bare statute)."
    ),
    "jurisdiction_mix": (
        "The context spans multiple jurisdictional tiers ({jurisdiction_list}). Attribute each "
        "proposition to the right court/tier and do not blur binding precedent with persuasive or "
        "lower-tier material."
    ),
}


def _tuning_enabled() -> bool:
    v = os.getenv("CORPUS_TUNING_ENABLED")
    return True if v is None else v.strip().lower() in ("1", "true", "yes", "on")


def _tuning_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _tuning_json(name: str, default):
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return default
    return parsed if isinstance(parsed, type(default)) else default


def _safe_format(template: str, ctx: dict) -> str:
    try:
        return template.format(**ctx)
    except (KeyError, IndexError, ValueError):
        return template


def corpus_composition(evidence: list[dict] | None) -> dict:
    items = [e for e in (evidence or []) if isinstance(e, dict)]
    total = len(items)
    if not total:
        return {
            "total": 0, "doc_types": {}, "jurisdictions": {},
            "authority_mean": 0.0, "internal_share": 0.0, "web_share": 0.0,
            "dominant_type": None, "dominant_share": 0.0,
        }
    labels = _tuning_json("CORPUS_JURISDICTION_LABELS", _DEFAULT_JURISDICTION_LABELS)
    unknown_label = labels.get("unknown", "Unclassified source")
    types = [(e.get("source_type") or "unknown") for e in items]
    type_counts = Counter(types)
    juris_counts = Counter(labels.get(t, unknown_label) for t in types)
    authorities = [
        float(e.get("authority_score", e.get("final_score", e.get("score", 0.0))) or 0.0)
        for e in items
    ]
    web = sum(1 for e in items if e.get("domain") == "web")
    dominant_type, dominant_n = type_counts.most_common(1)[0]
    return {
        "total": total,
        "doc_types": dict(type_counts),
        "jurisdictions": dict(juris_counts),
        "authority_mean": round(sum(authorities) / total, 3),
        "internal_share": round((total - web) / total, 3),
        "web_share": round(web / total, 3),
        "dominant_type": dominant_type,
        "dominant_share": round(dominant_n / total, 3),
    }


def composition_tuning_clause(stats: dict | None) -> str:
    if not stats or not stats.get("total") or not _tuning_enabled():
        return ""
    labels = _tuning_json("CORPUS_JURISDICTION_LABELS", _DEFAULT_JURISDICTION_LABELS)
    templates = _tuning_json("CORPUS_TUNING_TEMPLATES", _DEFAULT_TUNING_TEMPLATES)
    unknown_label = labels.get("unknown", "Unclassified source")
    dominant_label = labels.get(stats.get("dominant_type") or "unknown", unknown_label)
    ctx = {
        "web_pct": round(stats["web_share"] * 100),
        "authority_mean": stats["authority_mean"],
        "dominant_label": dominant_label,
        "dominant_pct": round(stats["dominant_share"] * 100),
        "jurisdiction_list": ", ".join(sorted(stats["jurisdictions"])),
    }
    signals = [
        ("web_heavy", stats["web_share"] >= _tuning_float("CORPUS_WEB_HEAVY_RATIO", 0.5)),
        ("low_authority", stats["authority_mean"] < _tuning_float("CORPUS_AUTHORITY_LOW", 0.5)),
        ("high_authority", stats["authority_mean"] >= _tuning_float("CORPUS_AUTHORITY_HIGH", 0.85)),
        ("single_type", stats["dominant_share"] >= _tuning_float("CORPUS_SINGLE_TYPE_DOMINANCE", 0.8)),
        ("jurisdiction_mix", len(stats["jurisdictions"]) >= int(_tuning_float("CORPUS_JURISDICTION_MIX_MIN", 2))),
    ]
    lines = [
        _safe_format(templates[key], ctx)
        for key, fired in signals
        if fired and key in templates
    ]
    if not lines:
        return ""
    return (
        "\n\nCorpus-composition tuning (auto-derived from the retrieved sources):\n"
        + "\n".join(f"- {ln}" for ln in lines)
    )


def _to_openai_messages(messages):
    out = []
    for m in messages:
        if m.type == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content or ""})
            continue
        role = "user" if m.type == "human" else ("assistant" if m.type == "ai" else m.type)
        entry = {"role": role, "content": m.content or ""}
        if m.type == "ai" and getattr(m, "tool_calls", None):
            entry["tool_calls"] = [
                {
                    "id": tc["id"], "type": "function",
                    "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])},
                }
                for tc in m.tool_calls
            ]
            # OpenAI-compatible APIs require content to be null (not "") on an
            # assistant turn that's purely a tool call, or some providers reject it.
            entry["content"] = m.content or None
        out.append(entry)
    return out


def _to_anthropic_payload(messages):
    """Anthropic's Messages API takes system prompts separately from the
    user/assistant turn list — pull any system messages out and join them.
    Tool calls/results use Anthropic's own content-block shapes (tool_use on
    the assistant turn, tool_result on a user turn), not OpenAI's tool_calls
    field — a plain text-content turn can't carry either."""
    system_parts = [m.content for m in messages if m.type == "system"]
    turns = []
    for m in messages:
        if m.type == "system":
            continue
        if m.type == "tool":
            turns.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content or ""}],
            })
        elif m.type == "ai" and getattr(m, "tool_calls", None):
            blocks = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for tc in m.tool_calls:
                blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["args"]})
            turns.append({"role": "assistant", "content": blocks})
        else:
            turns.append({"role": "user" if m.type == "human" else "assistant", "content": m.content})
    return "\n\n".join(system_parts), turns


def _openai_tool_schemas(tools) -> list[dict]:
    return [convert_to_openai_tool(t) for t in tools]


def _anthropic_tool_schemas(tools) -> list[dict]:
    """Anthropic's tool schema is OpenAI's `function` object with `parameters`
    renamed to `input_schema` and the `type: function` wrapper dropped."""
    schemas = []
    for t in tools:
        fn = convert_to_openai_tool(t)["function"]
        schemas.append({
            "name": fn["name"], "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return schemas


def _parse_openai_tool_calls(raw: list[dict] | None) -> list[dict]:
    if not raw:
        return []
    calls = []
    for tc in raw:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except (TypeError, ValueError):
            args = {}
        calls.append({"name": fn.get("name", ""), "args": args, "id": tc.get("id", ""), "type": "tool_call"})
    return calls


def _parse_anthropic_tool_calls(blocks: list[dict]) -> list[dict]:
    return [
        {"name": b.get("name", ""), "args": b.get("input") or {}, "id": b.get("id", ""), "type": "tool_call"}
        for b in blocks if b.get("type") == "tool_use"
    ]


async def _openai_complete(
    client: httpx.AsyncClient, provider: dict, messages: list,
    max_tokens: int | None = None, tools: list[dict] | None = None,
) -> tuple[str, dict, list[dict]]:
    payload: dict = {"model": provider["model"], "messages": messages}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    resp = await client.post(
        f"{provider['base_url']}/chat/completions",
        headers={"Authorization": f"Bearer {provider['api_key']}"} if provider["api_key"] else {},
        json=payload,
    )
    resp.raise_for_status()
    body = resp.json()
    usage = body.get("usage") or {}
    message = body["choices"][0]["message"]
    tool_calls = _parse_openai_tool_calls(message.get("tool_calls"))
    return message.get("content") or "", _normalize_openai_usage(usage), tool_calls


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


async def _anthropic_complete(
    client: httpx.AsyncClient, provider: dict, messages: list,
    max_tokens: int | None = None, tools: list[dict] | None = None,
) -> tuple[str, dict, list[dict]]:
    system, turns = _to_anthropic_payload(messages)
    payload = {"model": provider["model"], "max_tokens": max_tokens or 4096, "system": system, "messages": turns}
    if tools:
        payload["tools"] = tools
    resp = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": provider["api_key"], "anthropic-version": "2023-06-01"},
        json=payload,
    )
    resp.raise_for_status()
    body = resp.json()
    blocks = body.get("content", [])
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    tool_calls = _parse_anthropic_tool_calls(blocks)
    usage = body.get("usage") or {}
    return text, {"input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0)}, tool_calls


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

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        """Store the raw LangChain tools via .bind() rather than converting to
        a provider schema here — the provider actually used is only known
        once the fallback chain is walked in _agenerate, and OpenAI-compatible
        vs. Anthropic providers need different schema shapes for the SAME
        bound tools."""
        return self.bind(tools=tools, **kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise NotImplementedError("Use async")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        chain = settings.llm_provider_chain
        last_exc = None
        max_tokens = kwargs.get("max_tokens")
        base_timeout = kwargs.get("timeout", 30.0)
        tools = kwargs.get("tools")
        for provider in chain:
            timeout = httpx.Timeout(base_timeout, connect=5.0)
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    if provider["kind"] == "anthropic":
                        provider_tools = _anthropic_tool_schemas(tools) if tools else None
                        text, usage, tool_calls = await _anthropic_complete(
                            client, provider, messages, max_tokens=max_tokens, tools=provider_tools,
                        )
                    else:
                        provider_tools = _openai_tool_schemas(tools) if tools else None
                        text, usage, tool_calls = await _openai_complete(
                            client, provider, _to_openai_messages(messages), max_tokens=max_tokens, tools=provider_tools,
                        )
                    return ChatResult(generations=[ChatGeneration(message=AIMessage(
                        content=text,
                        tool_calls=tool_calls,
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


class JurisVoidChat(DirectApiChat):
    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        chain = settings.juris_void_provider_chain
        last_exc = None
        max_tokens = kwargs.get("max_tokens")
        base_timeout = kwargs.get("timeout", 30.0)
        tools = kwargs.get("tools")
        for provider in chain:
            timeout = httpx.Timeout(base_timeout, connect=5.0)
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    if provider["kind"] == "anthropic":
                        provider_tools = _anthropic_tool_schemas(tools) if tools else None
                        text, usage, tool_calls = await _anthropic_complete(
                            client, provider, messages, max_tokens=max_tokens, tools=provider_tools,
                        )
                    else:
                        provider_tools = _openai_tool_schemas(tools) if tools else None
                        text, usage, tool_calls = await _openai_complete(
                            client, provider, _to_openai_messages(messages), max_tokens=max_tokens, tools=provider_tools,
                        )
                    return ChatResult(generations=[ChatGeneration(message=AIMessage(
                        content=text,
                        tool_calls=tool_calls,
                        response_metadata={
                            "model_provider": provider["provider_name"], "model_name": provider["model"],
                            "usage": usage,
                        },
                    ))])
            except Exception as exc:
                last_exc = exc
                continue
        raise RuntimeError(f"All Juris-VOID LLM providers failed. Last error: {last_exc}")

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        chain = settings.juris_void_provider_chain
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
        result = await self._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)
        message = result.generations[0].message
        words = message.content.split(" ") if message.content else []
        for i, word in enumerate(words):
            token = word if i == len(words) - 1 else word + " "
            yield ChatGenerationChunk(message=AIMessageChunk(content=token, response_metadata=message.response_metadata))


_jv_llm: JurisVoidChat | None = None


def get_juris_void_llm() -> JurisVoidChat:
    global _jv_llm
    if _jv_llm is None:
        _jv_llm = JurisVoidChat()
    return _jv_llm


def reset_juris_void_llm():
    global _jv_llm
    _jv_llm = None
