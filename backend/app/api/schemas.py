from datetime import date
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any


# ============================================================================
# Chat Request/Response Schemas
# ============================================================================

class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    use_web_search: bool = False
    web_search_max_results: int = 5
    mode: str = "ask"  # "ask" | "interact"
    session_id: Optional[str] = None
    output_format: str = "CREAC"  # "CREAC" | "IRAC" | "BRIEF"
    # Source filenames (as returned by GET /documents) to scope retrieval to.
    # None/empty = search the full corpus, unchanged from prior behavior.
    sources: Optional[List[str]] = None
    # Date ("YYYY-MM-DD") to answer as of; defaults to today via default_factory
    # so it's computed per-request, not frozen at import time. Pass an explicit
    # date to ask about a historical point in time instead.
    as_of_date: Optional[str] = Field(default_factory=lambda: date.today().isoformat())


class LlmStatusOut(BaseModel):
    """Which provider in settings.llm_provider_chain is actually active —
    the first entry, since that's the one every request tries first."""
    provider: str
    model: str
    base_url: Optional[str] = None
    configured: bool
    web_search_provider: Optional[str] = None


class ChatRequestAnalyze(BaseModel):
    question: str
    use_web_search: bool = False


class CitationOut(BaseModel):
    quote: str
    verified: bool
    cited: bool = False
    source: str
    page: int
    content_hash: str = ""
    index: int = 0


class SourceChunkOut(BaseModel):
    text: str
    source: str
    page: int
    score: float
    verified: bool = False
    cited: bool = False
    domain: str = "internal"
    url: Optional[str] = None
    index: int = 0
    citation_quote: str = ""
    preview: str = ""
    doc_id: Optional[str] = None
    chunk_id: Optional[str] = None
    found_by: Optional[str] = None


ScoredChunkOut = SourceChunkOut


class WebEvidenceOut(BaseModel):
    title: str
    url: str
    content: str
    score: float
    authority_score: float = 0.0
    source_type: str = "web"
    published_at: str = ""
    retrieved_at: str = ""
    content_hash: str = ""
    citation_id: str = ""


class SupportedClaimOut(BaseModel):
    claim: str
    content_hash: str = ""


class VerificationOut(BaseModel):
    groundedness_score: float = 0.0
    verdict: str = "unsupported"
    supported_claims: List[SupportedClaimOut] = []
    unsupported_claims: List[str] = []
    summary: str = ""
    blocked: bool = False
    regenerated: bool = False


class QueryAnalysisOut(BaseModel):
    score: int = 5
    gaps: List[str] = []
    suggested_rewrite: str = ""
    improvement_reason: str = ""


class ChatResponse(BaseModel):
    answer: str
    citations: List[CitationOut]
    source_chunks: List[SourceChunkOut] = []
    conversation_id: str
    intent: str
    sources_used: int
    verification: Optional[VerificationOut] = None
    run_id: Optional[str] = None
    output_format: str = "CREAC"
    query_analysis: Optional[QueryAnalysisOut] = None
    reasoning_steps: List[Dict[str, Any]] = []


class ChatAnalyzeResponse(BaseModel):
    original_question: str
    analysis: QueryAnalysisOut
    should_improve: bool


class ChatImproveResponse(BaseModel):
    original_question: str
    improved_question: str
    analysis: QueryAnalysisOut
    was_improved: bool


class DevilsAdvocateRequest(BaseModel):
    run_id: str


class DevilsAdvocateResponse(BaseModel):
    counterargument: str


class ChatDownloadPdfRequest(BaseModel):
    question: str
    answer: str
    citations: List[Dict[str, Any]] = []
    source_chunks: List[Dict[str, Any]] = []
    verification: Optional[Dict[str, Any]] = None
    include_citations: bool = True


# ============================================================================
# Draft Schemas
# ============================================================================

DRAFT_DOCUMENT_TYPES: tuple[str, ...] = (
    "Opinion/memo",
    "Plaint",
    "Written statement/Counter",
    "Petition (writ/SLP/review)",
    "Written submissions",
    "Application (IA/bail/misc.)",
    "Order/Judgment",
    "Notice/letter",
    "Reply notice",
    "Agreement",
    "Affidavit",
    "Other",
)


class DraftRequest(BaseModel):
    brief: str
    document_type: Optional[str] = None
    house_style_file_hash: Optional[str] = None
    input_document_file_hash: Optional[str] = None
    sources: Optional[List[str]] = None
    research_before_drafting: bool = False
    session_id: Optional[str] = None

    @field_validator("document_type")
    @classmethod
    def _default_unknown_document_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v if v in DRAFT_DOCUMENT_TYPES else "Other"


class DraftResponse(BaseModel):
    content: str
    run_id: Optional[str] = None
    citations: List[CitationOut] = []
    source_chunks: List[SourceChunkOut] = []


class DraftRunOut(BaseModel):
    id: str
    title: str
    document_type: Optional[str] = None
    author: Optional[str] = None
    status: str = "complete"
    created_at: str

    class Config:
        from_attributes = True


# ============================================================================
# Ingestion Schemas
# ============================================================================

class IngestRequest(BaseModel):
    prefix_filter: str = ""
    sync_only: bool = True


class IngestResponse(BaseModel):
    ingested: int
    failed: int
    skipped: int = 0
    total_keys: int
    running: bool = False
    processed: int = 0
    total: int = 0
    current_key: str = ""
    already_running: bool = False


class LastSyncOut(BaseModel):
    """Summary of the most recently completed run — persisted to disk so it
    survives a backend restart or the user closing and reopening the app."""
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    ingested: int = 0
    failed: int = 0
    skipped: int = 0
    total: int = 0
    error: Optional[str] = None


class SyncStatusResponse(BaseModel):
    total_on_s3: int
    ingested: int
    pending: int
    pending_keys: List[str] = []
    running: bool = False
    processed: int = 0
    total: int = 0
    failed: int = 0
    skipped: int = 0
    current_key: str = ""
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    concurrency: int = 0
    cpu_percent: float = 0.0
    last_sync: Optional[LastSyncOut] = None


# ============================================================================
# Interact Schemas
# ============================================================================

class InteractDocumentOut(BaseModel):
    file_hash: str
    filename: str
    chunk_count: int
    duplicate: bool = False


class InteractAttachDeviceResponse(BaseModel):
    session_id: str
    document: InteractDocumentOut


class InteractReuseRequest(BaseModel):
    session_id: str
    source_session_id: str
    file_hash: str


class InteractDocumentsOut(BaseModel):
    session_id: str
    documents: List[InteractDocumentOut] = []


# ============================================================================
# Juris-VOID Upload / OCR Schemas
# ============================================================================

class OcrStatusOut(BaseModel):
    """OCR subsystem status. Field names mirror the OCR_* settings so the
    frontend can explain why a scanned/image-only PDF may extract no text.
    `available` is whether the pytesseract/pdf2image stack (and the tesseract
    binary) is actually importable/callable, independent of `enabled`."""
    enabled: bool
    available: bool
    lang: str
    dpi: int
    min_chars_per_page: int


class JurisVoidUploadOut(BaseModel):
    document: InteractDocumentOut
    ocr: OcrStatusOut


# ============================================================================
# Auth Schemas
# ============================================================================

class OtpSendRequest(BaseModel):
    via: str
    email: Optional[str] = None
    phone: Optional[str] = None
    intent: str
    name: Optional[str] = None


class ForgotRequest(BaseModel):
    via: str
    email: Optional[str] = None
    phone: Optional[str] = None


class OtpSendResponse(BaseModel):
    sent: bool
    delivery: str
    target: str = ""
    dev_otp: Optional[str] = None
    expires_in: int = 600
    exists: bool = False


class OtpVerifyRequest(BaseModel):
    via: str
    email: Optional[str] = None
    phone: Optional[str] = None
    otp: str
    intent: str
    name: Optional[str] = None


class AuthUserOut(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    org: str = ""
    email_verified: bool = False
    phone_verified: bool = False


class OtpVerifySuccessOut(BaseModel):
    ok: bool
    intent: str
    user: Optional[AuthUserOut] = None
    token: Optional[str] = None
    reset_token: Optional[str] = None


class RegisterRequest(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    password: str


class LoginRequest(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    password: str


class ResetRequest(BaseModel):
    via: str
    email: Optional[str] = None
    phone: Optional[str] = None
    otp: str
    new_password: str


class AuthResponse(BaseModel):
    user: AuthUserOut
    token: str


# ============================================================================
# SSE Event Schemas
# ============================================================================

class SSEProgressEvent(BaseModel):
    type: str = "progress"
    step: str
    message: str
    detail: Optional[str] = None


class SSERTokenEvent(BaseModel):
    type: str = "token"
    content: str


class SSECompleteEvent(BaseModel):
    type: str = "complete"
    answer: str
    citations: List[Dict[str, Any]]
    source_chunks: List[Dict[str, Any]]
    verification: Dict[str, Any]
    intent: str
    sources_used: Dict[str, Any]
    conversation_id: str


SSEEvent = SSEProgressEvent | SSERTokenEvent | SSECompleteEvent
