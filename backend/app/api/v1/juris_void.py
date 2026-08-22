from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import time
from functools import lru_cache
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from sqlalchemy import delete, select, text

from app.api.schemas import (
    ChatRequest, SourceChunkOut, CitationOut,
    InteractDocumentOut, JurisVoidUploadOut, OcrStatusOut,
)
from app.config.settings import settings
from app.core.db import get_sessionmaker
from app.core.graph.nodes import (
    web_search_node, evidence_merge_node,
    generate_answer_node, answer_format_instructions, as_of_clause,
)
from app.core.graph.state import JuryAIState
from app.core.graph.verifier import verify_answer, _build_evidence_text
from app.core.graph.gate import gate_answer
from app.core.prompts.juris_void import JV_DRAFT_PROMPT
from app.core.retrieval.citation import derive_citations, verified_content_hashes, cited_indices
from app.core.llm.provider import get_juris_void_llm, reset_juris_void_llm
from app.core.memory import load_history, append_turn
from app.core.graph.evidence_merger import ensure_content_hashes
from app.core.graph.jv_agents import (
    run_collaborative_pipeline, spice_full_search,
)
from app.core.ingestion.parser import parse_bytes
from app.models.juris_void_doc import JurisVoidChunk

router = APIRouter()
logger = logging.getLogger("juryai.juris_void")

SPICE_TIMEOUT = 15.0


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@lru_cache(maxsize=1)
def _ocr_available() -> bool:
    """Whether the OCR stack is actually usable — modules importable AND the
    tesseract binary reachable. Cached: availability is fixed for the process
    and get_tesseract_version() shells out, so probe once."""
    if importlib.util.find_spec("pytesseract") is None or importlib.util.find_spec("pdf2image") is None:
        return False
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _ocr_status() -> OcrStatusOut:
    return OcrStatusOut(
        enabled=settings.OCR_ENABLED,
        available=_ocr_available(),
        lang=settings.OCR_LANG,
        dpi=settings.OCR_DPI,
        min_chars_per_page=settings.OCR_MIN_CHARS_PER_PAGE,
    )


async def _spice_available() -> bool:
    if not settings.SPICE_ENABLED:
        return False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.SPICE_HTTP_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False


async def _spice_get(path: str, fallback=None):
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.SPICE_HTTP_URL}{path}")
            if resp.status_code == 200:
                return resp.json() or fallback
    except Exception:
        pass
    return fallback if fallback is not None else []


def _source_chunks_from_evidence(
    evidence: list[dict], verified_hashes: set[str],
    cited_idx: set[int] = frozenset(), citations: list[dict] | None = None,
) -> list[SourceChunkOut]:
    citation_quotes = {}
    if citations:
        for cit in citations:
            if cit.get("index") and cit.get("quote"):
                citation_quotes[cit["index"]] = cit["quote"]

    chunks: list[SourceChunkOut] = []
    for i, item in enumerate(evidence, 1):
        text_content = item.get("text") or item.get("content") or ""
        if not text_content:
            continue
        source = item.get("source") or item.get("title") or item.get("url") or ""
        domain = item.get("domain", "internal")
        chunks.append(
            SourceChunkOut(
                text=text_content,
                source=source,
                page=item.get("page", 0),
                score=round(item.get("final_score", item.get("score", 0.0)), 4),
                verified=bool(item.get("content_hash")) and item.get("content_hash") in verified_hashes,
                cited=i in cited_idx,
                domain=domain,
                url=item.get("url") if domain == "web" else None,
                index=i,
                citation_quote=citation_quotes.get(i, ""),
                preview=text_content[:200] + ("..." if len(text_content) > 200 else ""),
                doc_id=item.get("doc_id"),
                chunk_id=item.get("chunk_id"),
                found_by=item.get("found_by"),
            )
        )
    return chunks


async def _juris_void_stream(request: ChatRequest, client_id: str, use_sub_agents: bool = False) -> AsyncGenerator[str, None]:
    start_time = time.monotonic()
    conversation_id = request.conversation_id or __import__("uuid").uuid4().hex

    logger.info("Juris-VOID stream: use_sub_agents=%s, use_web_search=%s", use_sub_agents, request.use_web_search)
    yield _sse("reasoning_step", {
        "step": "intent_classification",
        "detail": f"Juris-VOID {'multi-agent pipeline' if use_sub_agents else 'single pipeline (Void-Space direct)'} initializing",
    })

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
        "streaming": True,
        "mode": request.mode or "ask",
        "output_format": request.output_format or "CREAC",
        "as_of_date": request.as_of_date,
        "source_filter": request.sources,
    }

    if use_sub_agents:
        queue: asyncio.Queue = asyncio.Queue()
        agent_task = asyncio.create_task(
            run_collaborative_pipeline(request.question, state, queue, request.session_id)
        )

        while not agent_task.done():
            try:
                step = await asyncio.wait_for(queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            yield _sse("reasoning_step", {**step})

        try:
            agent_results = agent_task.result()
        except Exception as exc:
            logger.exception("Juris-VOID collaborative pipeline failed")
            yield _sse("error", {"message": str(exc)})
            yield _sse("done", {
                "conversation_id": conversation_id,
                "intent": "error",
                "sources_used": 0,
                "error": str(exc),
            })
            return

        while not queue.empty():
            step = queue.get_nowait()
            yield _sse("reasoning_step", {**step})

        merged = agent_results.get("merged_evidence", [])
        gen_state = dict(state)
        gen_state["merged_evidence"] = merged
        gen_state["legal_chunks"] = agent_results.get("legal_chunks", [])
        gen_state["web_evidence"] = agent_results.get("web_evidence", [])
        gen_state["web_results"] = agent_results.get("web_evidence", [])
    else:
        yield _sse("reasoning_step", {
            "step": "spice_search",
            "detail": "Querying Void-Space for corpus + uploaded documents",
        })
        spice_results = []
        try:
            spice_results = await spice_full_search(
                request.question,
                lambda s: None,
                request.session_id,
            )
        except Exception as exc:
            logger.warning("SpiceAI search failed: %s", exc)

        if request.use_web_search:
            yield _sse("reasoning_step", {"step": "web_search", "detail": "Searching the web"})
            try:
                state_copy = dict(state)
                state_copy["on_step"] = lambda s: None
                web_result = await web_search_node(state_copy)
                state["web_evidence"] = web_result.get("web_evidence", [])
            except Exception as exc:
                logger.warning("Web search failed: %s", exc)

        all_chunks = ensure_content_hashes(spice_results) if spice_results else []
        yield _sse("reasoning_step", {
            "step": "spice_done",
            "detail": f"Void-Space: {len(all_chunks)} chunks, Web: {len(state.get('web_evidence', []))} sources",
        })

        merge_state = dict(state)
        merge_state["legal_chunks"] = all_chunks
        merge_state["web_evidence"] = state.get("web_evidence", [])
        merge_result = await evidence_merge_node(merge_state)

        merged = merge_result.get("merged_evidence", [])
        gen_state = dict(state)
        gen_state["merged_evidence"] = merged
        gen_state["legal_chunks"] = all_chunks
        gen_state["web_evidence"] = state.get("web_evidence", [])
        gen_state["web_results"] = state.get("web_evidence", [])

    verify_evidence = merged

    source_chunks = _source_chunks_from_evidence(verify_evidence, set())
    for chunk in source_chunks:
        yield _sse("source_chunk", chunk.model_dump())

    gen_state["streaming"] = True
    gen_result = await generate_answer_node(gen_state)

    answer_prompt = gen_result.get("answer_prompt", "")
    full_answer = ""
    usage: dict = {}

    if answer_prompt:
        try:
            async for llm_chunk in get_juris_void_llm().astream([HumanMessage(content=answer_prompt)]):
                token = getattr(llm_chunk, "content", "") or ""
                if token:
                    full_answer += token
                    yield _sse("answer_token", {"token": token})
                chunk_meta = getattr(llm_chunk, "response_metadata", None) or {}
                if chunk_meta.get("usage"):
                    usage.update(chunk_meta["usage"])
        except Exception as exc:
            logger.warning("LLM stream failed: %s", exc, exc_info=True)
            yield _sse("reasoning_step", {
                "step": "stream_interrupted",
                "detail": "Answer generation interrupted; verifier gate will handle.",
            })

    yield _sse("reasoning_step", {
        "step": "verifying_answer",
        "detail": "Verifying answer groundedness against all retrieved evidence",
    })
    verification = await verify_answer(full_answer, verify_evidence)

    if settings.VERIFIER_GATE_ENABLED and verify_evidence:
        gate_rounds: list[dict] = []
        gated = await gate_answer(
            request.question, full_answer, verify_evidence,
            _build_evidence_text(verify_evidence), verification,
            on_round=gate_rounds.append,
        )
        for round_info in gate_rounds:
            yield _sse("reasoning_step", {"step": "gate_correction_round", **round_info})
        verification = dict(gated.verification)
        verification["blocked"] = gated.blocked
        verification["regenerated"] = gated.regenerated
        verification["correction_rounds"] = gated.rounds
        if gated.answer != full_answer:
            full_answer = gated.answer
            yield _sse("gate", {
                "answer": full_answer,
                "blocked": gated.blocked,
                "regenerated": gated.regenerated,
                "rounds": gated.rounds,
            })

    yield _sse("verification", verification)

    final_citations = derive_citations(verification, verify_evidence, full_answer)
    v_hashes = verified_content_hashes(final_citations)
    final_source_chunks = _source_chunks_from_evidence(
        verify_evidence, v_hashes, cited_indices(final_citations),
    )

    yield _sse("done", {
        "conversation_id": conversation_id,
        "intent": "legal",
        "answer": full_answer,
        "sources_used": len(final_source_chunks),
        "verification": verification,
        "source_chunks": [sc.model_dump() for sc in final_source_chunks],
        "citations": [CitationOut(**c).model_dump() for c in final_citations],
        "elapsed_seconds": round(time.monotonic() - start_time, 1),
        "usage": usage,
    })

    if full_answer.strip() and not verification.get("blocked"):
        await append_turn(request.conversation_id, request.question, full_answer)


class JVChatRequest(ChatRequest):
    use_sub_agents: bool = False


@router.post("/juris-void/chat/stream")
async def juris_void_stream_endpoint(request: JVChatRequest, http_request: Request) -> StreamingResponse:
    client_id = http_request.client.host if http_request.client else "unknown"
    return StreamingResponse(
        content=_juris_void_stream(request, client_id, use_sub_agents=request.use_sub_agents),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/juris-void/upload", response_model=JurisVoidUploadOut)
async def juris_void_upload(
    session_id: str = Form(...),
    file: UploadFile = File(...),
) -> JurisVoidUploadOut:
    data = await file.read()
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 50 MB)")

    file_hash = JurisVoidChunk.hash_content(data)
    filename = file.filename or "upload"

    chunks = parse_bytes(data, filename)
    if not chunks:
        # A scanned/image-only PDF yields no chunks when OCR is off or the
        # tesseract stack is missing — surface OCR status so the caller can
        # tell an empty document apart from a fixable OCR gap.
        raise HTTPException(
            422,
            detail={
                "message": "Could not extract text from file",
                "ocr": _ocr_status().model_dump(),
            },
        )

    session = get_sessionmaker()
    async with session() as db:
        existing = await db.execute(
            select(JurisVoidChunk.id)
            .where(JurisVoidChunk.session_id == session_id)
            .where(JurisVoidChunk.file_hash == file_hash)
            .limit(1)
        )
        if existing.scalar_one_or_none():
            return JurisVoidUploadOut(
                document=InteractDocumentOut(
                    file_hash=file_hash, filename=filename,
                    chunk_count=0, duplicate=True,
                ),
                ocr=_ocr_status(),
            )

        for i, chunk in enumerate(chunks):
            db.add(JurisVoidChunk(
                session_id=session_id,
                file_hash=file_hash,
                filename=filename,
                chunk_text=chunk["text"],
                chunk_index=i,
                page=chunk.get("page", 0),
            ))
        await db.commit()

    return JurisVoidUploadOut(
        document=InteractDocumentOut(
            file_hash=file_hash, filename=filename,
            chunk_count=len(chunks), duplicate=False,
        ),
        ocr=_ocr_status(),
    )


@router.get("/juris-void/documents")
async def juris_void_list_documents(session_id: str):
    session = get_sessionmaker()
    async with session() as db:
        rows = await db.execute(
            text(
                "SELECT file_hash, filename, COUNT(*) as chunk_count "
                "FROM juris_void_chunks "
                "WHERE session_id = :sid "
                "GROUP BY file_hash, filename "
                "ORDER BY MIN(created_at) DESC"
            ),
            {"sid": session_id},
        )
        docs = [
            {"file_hash": r.file_hash, "filename": r.filename, "chunk_count": r.chunk_count}
            for r in rows
        ]
    return {"documents": docs}


@router.delete("/juris-void/documents/{file_hash}")
async def juris_void_delete_document(file_hash: str, session_id: str):
    session = get_sessionmaker()
    async with session() as db:
        await db.execute(
            delete(JurisVoidChunk)
            .where(JurisVoidChunk.session_id == session_id)
            .where(JurisVoidChunk.file_hash == file_hash)
        )
        await db.commit()
    return {"deleted": True}


@router.get("/juris-void/ocr/status", response_model=OcrStatusOut)
async def juris_void_ocr_status() -> OcrStatusOut:
    return _ocr_status()


@router.get("/juris-void/status")
async def juris_void_status():
    corpus_ok = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.QDRANT_URL}/collections")
            corpus_ok = resp.status_code == 200
    except Exception:
        pass

    spice_ok = await _spice_available()

    spice_info: dict = {}
    if spice_ok:
        datasets, models_list, runtime = await asyncio.gather(
            _spice_get("/v1/datasets", []),
            _spice_get("/v1/models", []),
            _spice_get("/v1/status", {}),
            return_exceptions=True,
        )
        spice_info = {
            "datasets": datasets if isinstance(datasets, list) else [],
            "models": models_list if isinstance(models_list, list) else [],
            "runtime": runtime if isinstance(runtime, dict) else {},
        }

    chain = settings.llm_provider_chain
    llm_configured = bool(chain)
    llm_provider = chain[0]["provider_name"] if chain else "none"

    jv_chain = settings.juris_void_provider_chain
    jv_provider = jv_chain[0]["provider_name"] if jv_chain else "none"
    jv_model = jv_chain[0]["model"] if jv_chain else ""

    return {
        "corpus_connected": corpus_ok,
        "llm_configured": llm_configured,
        "llm_provider": llm_provider,
        "web_search_provider": settings.web_search_provider,
        "web_search_available": bool(settings.web_search_provider),
        "spice_available": spice_ok,
        "spice_info": spice_info,
        "juris_void_provider": jv_provider,
        "juris_void_model": jv_model,
        "global_provider": settings.active_global_provider,
        "juris_void_provider_info": settings.active_juris_void_provider,
        "available_providers": settings.available_providers,
    }


class ModelSelectRequest(BaseModel):
    provider: str
    model: str | None = None


@router.post("/juris-void/model")
async def set_juris_void_model(req: ModelSelectRequest):
    settings.JURIS_VOID_MODEL_PROVIDER = req.provider
    if req.model:
        settings.JURIS_VOID_MODEL = req.model
    reset_juris_void_llm()
    jv_chain = settings.juris_void_provider_chain
    return {
        "provider": jv_chain[0]["provider_name"] if jv_chain else "none",
        "model": jv_chain[0]["model"] if jv_chain else "",
    }


@router.get("/models/available")
async def list_available_models():
    return {
        "providers": settings.available_providers,
        "global": settings.active_global_provider,
        "juris_void": settings.active_juris_void_provider,
    }


class JVDraftRequest(BaseModel):
    answer: str
    question: str
    citations: list[dict] = []
    source_chunks: list[dict] = []
    document_type: str = "Opinion/memo"


@router.post("/juris-void/draft")
async def juris_void_draft(req: JVDraftRequest):
    prompt = JV_DRAFT_PROMPT.format(
        document_type=req.document_type, question=req.question, answer=req.answer,
    )
    try:
        resp = await get_juris_void_llm().ainvoke([HumanMessage(content=prompt)])
        draft_content = resp.content.strip()
    except Exception as exc:
        logger.warning("Draft generation failed: %s", exc)
        draft_content = req.answer

    return {"draft": draft_content, "document_type": req.document_type}
