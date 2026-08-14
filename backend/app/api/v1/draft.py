"""POST /draft — direct-generation document drafting.

v1: no retrieval grounding. The existing retrieval pipeline (hybrid
qdrant/quickwit search + reranker) is built around answering a question from
matched chunks, not around producing a full drafted document from a brief —
wiring it in cleanly is a follow-up, not this first version.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import HumanMessage

from app.api.schemas import DraftRequest, DraftResponse
from app.core.llm.provider import get_llm
from app.core.ratelimit import check_rate_limit

router = APIRouter()

logger = logging.getLogger("juryai.draft")

_DRAFT_PROMPT = """You are a legal drafting assistant. Write a complete, ready-to-use \
legal document in Markdown based on the brief below.

Brief:
{brief}

Use clear section headings and numbered clauses/paragraphs where the document type \
calls for them, and professional legal drafting language. Output only the document \
itself — no commentary, no preamble like "Here is your document"."""


def _client_id(http_request: Request) -> str:
    xff = http_request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return http_request.client.host if http_request.client else "unknown"


@router.post("/draft", response_model=DraftResponse)
async def draft(request: DraftRequest, http_request: Request) -> DraftResponse:
    if not request.brief.strip():
        raise HTTPException(status_code=400, detail="brief must not be empty")

    result = await check_rate_limit(_client_id(http_request))
    if not result.allowed:
        raise HTTPException(status_code=429, detail={"retry_after": str(result.retry_after)})

    prompt = _DRAFT_PROMPT.format(brief=request.brief.strip())
    resp = await get_llm().ainvoke([HumanMessage(content=prompt)])
    return DraftResponse(content=resp.content)
