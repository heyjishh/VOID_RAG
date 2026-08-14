from __future__ import annotations
import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    CitationOut,
    SourceChunkOut,
    VerificationOut,
)
from app.config.settings import settings
from app.core.graph.workflow import get_workflow, get_streaming_workflow
from app.core.graph.state import JuryAIState
from app.core.graph.verifier import verify_answer, _build_evidence_text
from app.core.graph.gate import gate_answer
from app.core.retrieval.citation import derive_citations, verified_content_hashes, cited_indices
from app.core.llm.provider import get_llm
from app.core.cache import answer_cache_get, answer_cache_set
from app.core.memory import load_history, append_turn
from app.core.ratelimit import check_rate_limit
from app.core.audit import build_turn_record, schedule_record_turn

router = APIRouter()

logger = logging.getLogger("juryai.chat")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sse(event: str, data: dict) -> str:
    """Format a single SSE message."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _client_id(http_request: Request) -> str:
    """Best-effort client identifier for rate limiting.

    ponytail: trusts X-Forwarded-For's first hop — fine behind our own reverse
    proxy; tighten (trusted-proxy allowlist) if exposed directly to clients.
    """
    xff = http_request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return http_request.client.host if http_request.client else "unknown"


def _validate_mode(request: ChatRequest) -> None:
    """Interact mode needs a session_id to scope retrieval to — reject early
    with a 400 rather than silently falling through to an empty/global
    search that would defeat the per-user isolation the feature promises."""
    if request.mode == "interact" and not request.session_id:
        raise HTTPException(status_code=400, detail="session_id is required when mode='interact'")


async def _enforce_rate_limit(http_request: Request) -> None:
    result = await check_rate_limit(_client_id(http_request))
    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please slow down and try again.",
            headers={"Retry-After": str(result.retry_after)},
        )


def _build_source_chunks(result: dict) -> tuple[list[SourceChunkOut], set[str]]:
    """Return (source_chunk_list, verified_content_hash_set) from workflow result.

    ``result["legal_chunks"]`` is populated solely by ``legal_retrieve_node``
    (hybrid_search + reranker) and never passes through ``merge_evidence`` —
    it therefore never carries a ``domain`` key. Hardcoding "internal" here
    (rather than ``chunk.get("domain", "internal")``) reflects that these
    items are always internal-corpus chunks, not a guess.
    """
    verified_hashes = verified_content_hashes(result.get("citations", []))
    chunks = [
        SourceChunkOut(
            text=chunk.get("text", ""),
            source=chunk.get("source", ""),
            page=chunk.get("page", 0),
            score=round(chunk.get("score", 0.0), 4),
            verified=bool(chunk.get("content_hash")) and chunk.get("content_hash") in verified_hashes,
            domain="internal",
            index=i,
        )
        for i, chunk in enumerate(result.get("legal_chunks", []), 1)
        if chunk.get("text") and chunk.get("source") is not None
    ]
    return chunks, verified_hashes


def _source_chunks_from_evidence(
    evidence: list[dict], verified_hashes: set[str], cited_idx: set[int] = frozenset()
) -> list[SourceChunkOut]:
    """Build the final, post-verification SourceChunkOut list for an evidence list.

    Shared by the streaming path's end-of-turn correction and the non-streaming
    path's response — both need the same content_hash → verified mapping.
    Items here may originate from ``merge_evidence`` and carry a "domain" key
    ("internal"/"web"); default to "internal" for callers that pass pre-merge,
    internal-only evidence (e.g. the legacy POST /chat evidence list).

    Web-domain items are WebEvidence-shaped ("content"/"title", not
    "text"/"source") — fall back the same way ``_build_evidence_text`` and
    ``derive_citations`` already do, so merged web evidence renders here too
    instead of being silently dropped for having the "wrong" key names.
    """
    chunks: list[SourceChunkOut] = []
    for i, item in enumerate(evidence, 1):
        text = item.get("text") or item.get("content") or ""
        if not text:
            continue
        source = item.get("source")
        if source is None:
            source = item.get("title") or item.get("url") or ""
        domain = item.get("domain", "internal")
        chunks.append(
            SourceChunkOut(
                text=text,
                source=source,
                page=item.get("page", 0),
                score=round(item.get("final_score", item.get("score", 0.0)), 4),
                verified=bool(item.get("content_hash")) and item.get("content_hash") in verified_hashes,
                cited=i in cited_idx,
                domain=domain,
                # Internal chunks never have a genuine navigable URL — the
                # source/title fallback above is a display label, not a link.
                url=item.get("url") if domain == "web" else None,
                # i is this item's 1-based position in `evidence` — the same
                # list/order generate_answer_node numbers [N] markers from and
                # derive_citations() builds citations[] from. Skipped
                # (empty-text) items above don't shift it.
                index=i,
            )
        )
    return chunks


# ---------------------------------------------------------------------------
# POST /chat — non-streaming
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, http_request: Request):
    await _enforce_rate_limit(http_request)
    _validate_mode(request)
    conversation_id = request.conversation_id or str(uuid.uuid4())

    # Answer cache: identical (normalized) question + web flag → replay instantly.
    # Skipped for interact mode — the cache key doesn't carry session_id, so a
    # shared key would leak one session's answer (grounded in their uploads)
    # to any other session asking the same question text.
    cached = (
        await answer_cache_get(request.question, request.use_web_search, scope="post")
        if request.mode != "interact" else None
    )
    if cached is not None:
        cached["conversation_id"] = conversation_id
        cached_citations = cached.get("citations", [])
        schedule_record_turn(
            build_turn_record(
                conversation_id=conversation_id,
                question=request.question,
                answer=cached.get("answer", ""),
                citations=cached_citations,
                verification=cached.get("verification") or {},
                evidence=cached_citations,
                model_provider="",
                model_name="",
                client_id=_client_id(http_request),
                streaming=False,
                cache_hit=True,
            )
        )
        return ChatResponse(**cached)

    history = await load_history(request.conversation_id)

    graph = get_workflow()
    state: JuryAIState = {
        "question": request.question,
        "history": history,
        "intent": "",
        "legal_chunks": [],
        "web_results": [],
        "citations": [],
        "answer": "",
        "error": None,
        "use_web_search": request.use_web_search,
        "mode": request.mode,
        "session_id": request.session_id,
    }
    result = await graph.ainvoke(state)

    answer = result.get("answer", "")
    verification = dict(result.get("verification") or {})
    citations_raw = result.get("citations", [])
    merged = result.get("merged_evidence") or []
    evidence = list(merged) if merged else list(result.get("legal_chunks") or [])
    model_provider = result.get("model_provider", "")
    model_name = result.get("model_name", "")

    # Verifier gate: regenerate ungrounded answers once; block if still unsupported.
    if settings.VERIFIER_GATE_ENABLED and evidence:
        gated = await gate_answer(
            request.question, answer, evidence, _build_evidence_text(evidence), verification
        )
        if gated.answer != answer:
            answer = gated.answer
            citations_raw = derive_citations(gated.verification, evidence, answer)
            if gated.model_provider:
                model_provider, model_name = gated.model_provider, gated.model_name
        verification = dict(gated.verification)
        verification["blocked"] = gated.blocked
        verification["regenerated"] = gated.regenerated

    verified_hashes = verified_content_hashes(citations_raw)
    citations = [CitationOut(**c) for c in citations_raw]
    source_chunks = _source_chunks_from_evidence(evidence, verified_hashes, cited_indices(citations_raw))

    response = ChatResponse(
        answer=answer,
        citations=citations,
        source_chunks=source_chunks,
        conversation_id=conversation_id,
        intent=result.get("intent", "legal"),
        sources_used=len(source_chunks),
        verification=VerificationOut(**verification),
    )

    await append_turn(request.conversation_id, request.question, answer)
    if request.mode != "interact":
        await answer_cache_set(
            request.question, request.use_web_search, response.model_dump(), scope="post"
        )

    schedule_record_turn(
        build_turn_record(
            conversation_id=conversation_id,
            question=request.question,
            answer=answer,
            citations=citations_raw,
            verification=verification,
            evidence=evidence,
            model_provider=model_provider,
            model_name=model_name,
            client_id=_client_id(http_request),
            streaming=False,
        )
    )
    return response


# ---------------------------------------------------------------------------
# SSE streaming endpoint
# ---------------------------------------------------------------------------

async def _stream_generator(request: ChatRequest, client_id: str) -> AsyncGenerator[str, None]:
    """Drive the streaming LangGraph workflow and emit SSE events.

    Order: reasoning_step* → source_chunk* → answer_token* → verification →
    (gate, only if the answer was regenerated/blocked) → done.

    The ``source_chunk`` events fire before the answer exists, so their
    ``verified`` flag is necessarily provisional (always False — grounding
    can't be known until the claim-level verifier has run against the full
    answer). ``done`` carries the corrected, post-verification ``source_chunks``
    and ``citations`` — the frontend already prefers ``done.source_chunks``
    over the accumulated per-event chunks (see ChatPanel.jsx), so this is the
    authoritative signal without any SSE contract change.
    """
    conversation_id = request.conversation_id or str(uuid.uuid4())

    # Step 1: emit intent classification immediately (before graph runs)
    yield _sse("reasoning_step", {
        "step": "intent_classification",
        "detail": "Classifying query intent and selecting retrieval strategy",
    })

    # Answer cache: replay a cached answer as SSE without re-running the pipeline.
    # Skipped for interact mode — see _validate_mode's docstring: the cache key
    # doesn't carry session_id, so sharing it would leak across sessions.
    cached = (
        await answer_cache_get(request.question, request.use_web_search, scope="stream")
        if request.mode != "interact" else None
    )
    if cached is not None:
        cached_chunks = cached.get("source_chunks", [])
        for sc in cached_chunks:
            yield _sse("source_chunk", sc)
        answer_text = cached.get("answer", "")
        words = answer_text.split(" ") if answer_text else []
        for i, word in enumerate(words):
            token = word if i == len(words) - 1 else word + " "
            yield _sse("answer_token", {"token": token})
        verification = cached.get("verification") or {}
        cached_citations = cached.get("citations", [])
        yield _sse("verification", verification)
        yield _sse("done", {
            "conversation_id": conversation_id,
            "intent": cached.get("intent", "legal"),
            "sources_used": len(cached_chunks),
            "verification": verification,
            "source_chunks": cached_chunks,
            "citations": cached_citations,
            "cached": True,
        })
        schedule_record_turn(
            build_turn_record(
                conversation_id=conversation_id,
                question=request.question,
                answer=answer_text,
                citations=cached_citations,
                verification=verification,
                evidence=cached_citations,
                model_provider="",
                model_name="",
                client_id=client_id,
                streaming=True,
                cache_hit=True,
            )
        )
        return

    history = await load_history(request.conversation_id)
    state: JuryAIState = {
        "question": request.question,
        "history": history,
        "intent": "",
        "legal_chunks": [],
        "web_results": [],
        "citations": [],
        "answer": "",
        "error": None,
        "use_web_search": request.use_web_search,
        "reasoning_steps": [],
        "web_evidence": [],
        "merged_evidence": [],
        # Streaming mode: generate_answer_node stores the prompt but skips LLM;
        # the SSE generator calls get_llm().astream() for real token streaming.
        "streaming": True,
        "mode": request.mode,
        "session_id": request.session_id,
    }

    try:
        graph = get_streaming_workflow()

        # Not astream_events: langgraph is unpinned (>=0.2.0) so its event
        # schema isn't guaranteed stable, and route_and_retrieve fans out to
        # legal_retrieve_node/web_search_node via asyncio.gather under one
        # outer "retrieve" node — node-level events couldn't see those inner
        # sub-steps anyway. A plain callback threaded through state (queued
        # here, drained below) reports the moment each step actually happens
        # regardless of graph structure or LangGraph version.
        queue: asyncio.Queue = asyncio.Queue()
        state["on_step"] = queue.put_nowait
        task = asyncio.create_task(graph.ainvoke(state))

        while not task.done():
            try:
                step = await asyncio.wait_for(queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            yield _sse("reasoning_step", {**step})

        result = await task
        while not queue.empty():
            step = queue.get_nowait()
            yield _sse("reasoning_step", {**step})

        # Emit source chunks — prefer merged_evidence (full mixed-domain
        # evidence), else fall back to legal_chunks for backward compat with
        # mocked tests. verified is always False here (provisional — see
        # docstring above).
        merged = result.get("merged_evidence", [])
        if merged:
            verify_evidence = merged
            source_chunks = _source_chunks_from_evidence(verify_evidence, set())
        else:
            verify_evidence = result.get("legal_chunks", [])
            source_chunks, _ = _build_source_chunks(result)

        for chunk in source_chunks:
            yield _sse("source_chunk", chunk.model_dump())

        # Stream answer tokens (real token streaming when a prompt is available).
        answer_prompt: str = result.get("answer_prompt", "")
        full_answer = ""
        model_provider = ""
        model_name = ""
        if answer_prompt:
            try:
                async for llm_chunk in get_llm().astream([HumanMessage(content=answer_prompt)]):
                    token: str = getattr(llm_chunk, "content", "") or ""
                    if token:
                        full_answer += token
                        yield _sse("answer_token", {"token": token})
                    chunk_meta = getattr(llm_chunk, "response_metadata", None) or {}
                    if chunk_meta.get("model_provider"):
                        model_provider = chunk_meta["model_provider"]
                        model_name = chunk_meta.get("model_name", "")
            except Exception as exc:
                # Real gateway failures mid-stream were previously silent — the
                # verifier gate below catches the resulting low-groundedness
                # answer and regenerates, but without this the root cause of a
                # recurring gateway issue would be undiagnosable.
                logger.warning(
                    "LLM stream failed for conversation_id=%s: %s",
                    conversation_id, exc, exc_info=True,
                )
                yield _sse("reasoning_step", {
                    "step": "stream_interrupted",
                    "detail": "Answer generation was interrupted; the verifier gate below will regenerate or block this answer.",
                })
        else:
            answer: str = result.get("answer", "")
            full_answer = answer
            words = answer.split(" ") if answer else []
            for i, word in enumerate(words):
                token = word if i == len(words) - 1 else word + " "
                yield _sse("answer_token", {"token": token})

        # Meta-verification against the full merged evidence (verify_evidence
        # was already resolved above, when the provisional source_chunks were
        # built); _build_evidence_text still prioritizes internal-domain items.
        yield _sse("reasoning_step", {
            "step": "verifying_answer",
            "detail": "Verifying answer groundedness against retrieved evidence",
        })
        verification = await verify_answer(full_answer, verify_evidence)

        # Verifier gate: regenerate / block if the streamed answer is ungrounded.
        # Common case (answer passes) is a no-op, so streaming stays fast.
        if settings.VERIFIER_GATE_ENABLED and verify_evidence:
            gated = await gate_answer(
                request.question, full_answer, verify_evidence,
                _build_evidence_text(verify_evidence), verification,
            )
            verification = dict(gated.verification)
            verification["blocked"] = gated.blocked
            verification["regenerated"] = gated.regenerated
            if gated.answer != full_answer:
                # Answer changed after release — tell the client to replace it.
                full_answer = gated.answer
                if gated.model_provider:
                    model_provider, model_name = gated.model_provider, gated.model_name
                yield _sse("gate", {
                    "answer": full_answer,
                    "blocked": gated.blocked,
                    "regenerated": gated.regenerated,
                })

        yield _sse("verification", verification)

        # Final, post-verification citations/sources — the unified signal,
        # now that the claim-level verdict for the (possibly gated) answer exists.
        final_citations = derive_citations(verification, verify_evidence, full_answer)
        verified_hashes = verified_content_hashes(final_citations)
        final_source_chunks = _source_chunks_from_evidence(
            verify_evidence, verified_hashes, cited_indices(final_citations)
        )

        yield _sse("done", {
            "conversation_id": conversation_id,
            "intent": result.get("intent", "legal"),
            "answer": full_answer,
            "sources_used": len(final_source_chunks),
            "verification": verification,
            "source_chunks": [sc.model_dump() for sc in final_source_chunks],
            "citations": [CitationOut(**c).model_dump() for c in final_citations],
        })

        # Audit every resolved turn — including blocked/empty ones, since those
        # are exactly what a compliance review needs a record of. Unlike the
        # cache/memory writes below, this is never conditioned on the answer
        # having shipped successfully.
        schedule_record_turn(
            build_turn_record(
                conversation_id=conversation_id,
                question=request.question,
                answer=full_answer,
                citations=final_citations,
                verification=verification,
                evidence=verify_evidence,
                model_provider=model_provider,
                model_name=model_name,
                client_id=client_id,
                streaming=True,
            )
        )

        # Persist + cache the FINAL (post-gate) answer. Skip empties/blocked.
        if full_answer.strip() and not verification.get("blocked"):
            await append_turn(request.conversation_id, request.question, full_answer)
        if full_answer.strip() and not verification.get("blocked") and request.mode != "interact":
            await answer_cache_set(
                request.question,
                request.use_web_search,
                {
                    "answer": full_answer,
                    "source_chunks": [sc.model_dump() for sc in final_source_chunks],
                    "citations": [CitationOut(**c).model_dump() for c in final_citations],
                    "verification": verification,
                    "intent": result.get("intent", "legal"),
                },
                scope="stream",
            )
    except Exception as e:
        yield _sse("done", {
            "conversation_id": conversation_id,
            "intent": "error",
            "sources_used": 0,
            "error": str(e),
        })


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, http_request: Request) -> StreamingResponse:
    """SSE endpoint — streams reasoning steps, source chunks, answer tokens, and done."""
    await _enforce_rate_limit(http_request)
    _validate_mode(request)
    return StreamingResponse(
        content=_stream_generator(request, _client_id(http_request)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
