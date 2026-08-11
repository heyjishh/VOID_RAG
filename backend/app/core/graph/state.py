from __future__ import annotations
from typing import Callable, TypedDict, Optional, NotRequired


class HistoryMsg(TypedDict):
    role: str
    content: str


class ReasoningStep(TypedDict):
    step: str
    detail: str


class WebResult(TypedDict):
    title: str
    url: str
    content: str
    score: float


class WebEvidence(TypedDict):
    title: str
    url: str
    content: str
    score: float
    authority_score: float
    source_type: str
    published_at: str
    retrieved_at: str
    content_hash: str
    citation_id: str


class _ScoredChunkBase(TypedDict):
    text: str
    source: str
    page: int
    score: float


class ScoredChunk(_ScoredChunkBase, total=False):
    source_type: str
    authority_score: float
    content_hash: str


class SupportedClaim(TypedDict):
    claim: str
    content_hash: str


# Canonical citation-verification shape — the single source of truth for what
# "verified" means across both the legacy and streaming chat paths. Defined
# here (not in app.core.retrieval.citation) since it mirrors other state-shape
# TypedDicts and citation.py already depends on this module.
class CitationResult(TypedDict):
    quote: str
    verified: bool
    source: str
    page: int
    content_hash: str


class JuryAIState(TypedDict):
    question: str
    history: list[HistoryMsg]
    intent: str
    legal_chunks: list[ScoredChunk]
    web_results: list[WebResult]
    citations: list[CitationResult]
    answer: str
    error: NotRequired[Optional[str]]
    # New fields added for RAG overhaul
    reasoning_steps: NotRequired[list[ReasoningStep]]
    web_evidence: NotRequired[list[WebEvidence]]
    use_web_search: NotRequired[bool]
    merged_evidence: NotRequired[list[dict]]
    # Streaming support
    streaming: NotRequired[bool]
    answer_prompt: NotRequired[str]
    # Meta-verification layer
    verification: NotRequired[dict]
    # Which provider in settings.llm_provider_chain actually served the answer
    model_provider: NotRequired[str]
    model_name: NotRequired[str]
    # Per-request live step sink (never cached on the compiled graph — set fresh
    # in _stream_generator so concurrent requests don't cross-talk on one callback).
    on_step: NotRequired[Callable[[ReasoningStep], None]]
