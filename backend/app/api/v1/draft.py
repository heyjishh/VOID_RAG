"""POST /draft document drafting, plus GET /draft/recent list/detail.

v1 was direct-generation only (no retrieval grounding). This adds, all
optional so a brief-only request keeps working exactly as before:
  - document_type: adds a clause naming the document type in the prompt.
  - session_id + house_style_file_hash/input_document_file_hash: pulls
    exemplar/input text from the caller's session-scoped upload store
    (never the shared Qdrant/Quickwit corpus — see app.core.drafting.session_docs).
  - research_before_drafting (+ sources): read-only hybrid search + rerank
    against the shared corpus (see app.core.drafting.research), narrowed to
    `sources` when given. Populates DraftResponse.citations/source_chunks.
Every generated document is persisted as a DraftRun row (best-effort — a
DB blip never blocks the response, mirroring app.core.audit's fail-open
policy). user_id is attached when the caller sends a valid Bearer session;
POST /draft itself stays unauthenticated, matching the existing endpoint.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from langchain_core.messages import HumanMessage
from sqlalchemy import select

from app.api.schemas import DRAFT_DOCUMENT_TYPES, DraftRequest, DraftResponse, DraftRunOut
from app.api.v1.auth import get_current_user
from app.core import auth_store
from app.core.db import get_sessionmaker
from app.core.drafting.prompt import build_draft_prompt
from app.core.drafting.research import research_for_draft
from app.core.drafting.session_docs import get_document_text
from app.core.llm.provider import get_llm
from app.core.ratelimit import check_rate_limit
from app.core.retrieval.session_store import InvalidSessionId
from app.models.auth import User
from app.models.draft import DraftRun

router = APIRouter()

logger = logging.getLogger("juryai.draft")


def _client_id(http_request: Request) -> str:
    xff = http_request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return http_request.client.host if http_request.client else "unknown"


async def _optional_user(http_request: Request) -> User | None:
    authorization = http_request.headers.get("authorization")
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    return await auth_store.get_user_by_session(token)


def _source_chunks_out(chunks: list[dict]) -> list[dict]:
    return [
        {"text": c["text"], "source": c["source"], "page": c["page"], "score": c.get("score", 0.0), "index": i}
        for i, c in enumerate(chunks, 1)
    ]


def _citations_out(chunks: list[dict]) -> list[dict]:
    return [
        {
            "quote": c["text"][:280],
            "verified": False,
            "source": c["source"],
            "page": c["page"],
            "content_hash": c.get("content_hash", ""),
            "index": i,
        }
        for i, c in enumerate(chunks, 1)
    ]


async def _persist_draft_run(
    *, user_id: int | None, title: str, document_type: str, brief: str, content: str
) -> uuid.UUID | None:
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            run = DraftRun(
                user_id=user_id,
                title=title,
                document_type=document_type,
                brief=brief,
                content=content,
                status="completed",
            )
            session.add(run)
            await session.commit()
            return run.id
    except Exception as exc:  # noqa: BLE001 — persistence must never break drafting
        logger.warning("draft run persistence failed: %s", exc)
        return None


def _run_to_out(run: DraftRun) -> DraftRunOut:
    return DraftRunOut(
        id=str(run.id),
        title=run.title,
        document_type=run.document_type or None,
        status=run.status,
        created_at=run.created_at.isoformat(),
    )


@router.post("/draft", response_model=DraftResponse)
async def draft(request: DraftRequest, http_request: Request) -> DraftResponse:
    brief = request.brief.strip()
    if not brief:
        raise HTTPException(status_code=400, detail="brief must not be empty")
    if request.document_type and request.document_type not in DRAFT_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"document_type must be one of {sorted(DRAFT_DOCUMENT_TYPES)}",
        )
    if (request.house_style_file_hash or request.input_document_file_hash) and not request.session_id:
        raise HTTPException(
            status_code=400,
            detail="session_id is required when house_style_file_hash or input_document_file_hash is given",
        )

    result = await check_rate_limit(_client_id(http_request))
    if not result.allowed:
        raise HTTPException(status_code=429, detail={"retry_after": str(result.retry_after)})

    research_chunks: list[dict] = []
    if request.research_before_drafting:
        research_chunks = await research_for_draft(brief, sources=request.sources or None)

    try:
        house_style_text = (
            get_document_text(request.session_id, request.house_style_file_hash) or None
            if request.session_id and request.house_style_file_hash
            else None
        )
        input_document_text = (
            get_document_text(request.session_id, request.input_document_file_hash) or None
            if request.session_id and request.input_document_file_hash
            else None
        )
    except InvalidSessionId as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    prompt = build_draft_prompt(
        brief=brief,
        document_type=request.document_type,
        house_style_text=house_style_text,
        input_document_text=input_document_text,
        research_chunks=research_chunks,
    )
    resp = await get_llm().ainvoke([HumanMessage(content=prompt)])
    content = resp.content

    user = await _optional_user(http_request)
    run_id = await _persist_draft_run(
        user_id=user.id if user else None,
        title=brief[:120],
        document_type=request.document_type or "",
        brief=brief,
        content=content,
    )

    return DraftResponse(
        content=content,
        run_id=str(run_id) if run_id else None,
        citations=_citations_out(research_chunks),
        source_chunks=_source_chunks_out(research_chunks),
    )


@router.get("/draft/recent", response_model=list[DraftRunOut])
async def list_draft_runs(user: User = Depends(get_current_user)) -> list[DraftRunOut]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        rows = (
            await session.execute(
                select(DraftRun)
                .where(DraftRun.user_id == user.id)
                .order_by(DraftRun.created_at.desc())
                .limit(50)
            )
        ).scalars().all()
    return [_run_to_out(row) for row in rows]


@router.get("/draft/recent/{run_id}", response_model=DraftRunOut)
async def get_draft_run(run_id: str, user: User = Depends(get_current_user)) -> DraftRunOut:
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="run_id must be a valid UUID") from exc

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        row = await session.get(DraftRun, run_uuid)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Draft run not found")
    return _run_to_out(row)
