from __future__ import annotations
import json
import re
from typing import Optional
from pydantic import computed_field, field_validator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_GOVERNMENT_SEARCH_DOMAINS: list[str] = [
    "indiacode.nic.in",
    "legislative.gov.in",
    "egazette.gov.in",
    "sci.gov.in",
    "ecourts.gov.in",
    "judis.nic.in",
    "indiankanoon.org",
]

_DEFAULT_AUTHORITY_TABLE: dict[str, float] = {
    # Keys are `source_type` categories as returned by detect_source_type()
    # (see app/core/retrieval/source_type.py) — NOT raw domain names. The
    # scorer's lookup (`AuthorityScorer._authority`) matches on source_type,
    # so a domain-keyed table here would never match and every lookup would
    # silently fall through to "default" regardless of true source quality.
    "supreme_court_judgment": 1.0,
    "constitutional": 1.0,
    "statute": 0.95,
    "high_court_judgment": 0.90,
    "government_notification": 0.85,
    "case_doc": 0.70,
    "legal_news": 0.65,
    "blog": 0.35,
    "forum": 0.20,
    "unknown": 0.15,
    "default": 0.60,
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""  # supply via .env / environment — never hardcode
    POSTGRES_DB: str = "juryai"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    # A dedicated schema keeps JuryAI's tables isolated if this Postgres
    # instance is ever shared with another application.
    POSTGRES_SCHEMA: str = "juryai"

    @field_validator("POSTGRES_SCHEMA")
    @classmethod
    def validate_postgres_schema(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", v):
            raise ValueError(f"Invalid POSTGRES_SCHEMA: {v!r}")
        return v

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Audit log (Postgres-backed, durable — NOT best-effort; see app.core.audit).
    # A silently-lost compliance record is a liability, unlike the Valkey caches
    # below, so this gets real retry-with-backoff instead of fail-open/fail-soft.
    AUDIT_LOG_ENABLED: bool = True
    AUDIT_LOG_MAX_ATTEMPTS: int = 3
    AUDIT_LOG_RETRY_BASE_SECONDS: float = 0.25
    AUDIT_LOG_WRITE_TIMEOUT_SECONDS: float = 5.0

    # Valkey (Redis-protocol compatible) — datastore for answer cache, memory,
    # rate-limit counters. redis-py 8.x is the client; it speaks the Valkey wire
    # protocol, so the URL scheme stays redis:// (rediss:// for TLS).
    VALKEY_URL: str = "redis://localhost:6379/1"
    # Secrets have NO baked-in default — supply via .env / environment.
    SECRET_KEY: str = ""

    # Answer cache (Valkey-backed, best-effort — never blocks the request path)
    ANSWER_CACHE_ENABLED: bool = True
    VALKEY_TIMEOUT_SECONDS: float = 0.5
    VALKEY_BREAKER_COOLDOWN_SECONDS: float = 30.0

    # Verifier gate — block ungrounded answers, regenerate once (LexLegis-style)
    VERIFIER_GATE_ENABLED: bool = True
    GROUNDEDNESS_MIN: float = 0.5          # verdict "unsupported" (< this) fails the gate
    GATE_BLOCKED_MESSAGE: str = (
        "I could not produce an answer grounded in the retrieved legal sources. "
        "Rather than risk an unsupported statement, I'm declining to answer — "
        "please rephrase, narrow the question, or add source documents."
    )

    # Conversation memory (Valkey-backed, best-effort)
    CONVERSATION_MEMORY_ENABLED: bool = True
    CONVERSATION_MAX_TURNS: int = 6        # trailing turns injected into the prompt
    CONVERSATION_TTL_SECONDS: int = 86400  # 24h

    # Run storage (Valkey-backed, best-effort)
    RUN_STORAGE_ENABLED: bool = True
    RUN_TTL_SECONDS: int = 604800          # 7 days

    # Rate limiting (Valkey fixed-window, fail-open if store is down)
    RATELIMIT_ENABLED: bool = True
    RATELIMIT_MAX_REQUESTS: int = 30
    RATELIMIT_WINDOW_SECONDS: int = 60

    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "ap-south-1"
    S3_BUCKET_NAME: Optional[str] = None
    S3_DOCUMENT_PREFIX: str = "documents"
    # Comma-separated list of bucket names; falls back to S3_BUCKET_NAME if unset
    S3_BUCKET_NAMES: Optional[str] = None

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "juryai_legal"
    QDRANT_API_KEY: Optional[str] = None

    QUICKWIT_URL: str = "http://localhost:7280"
    QUICKWIT_INDEX: str = "juryai_legal"

    # === Superior Retrieval Stack (Option B + Legal Embedder) ===
    # Retrieval-tuned embedder (110M params, 768 dim)
    EMBED_MODEL: str = "BAAI/bge-base-en-v1.5"
    EMBED_DIM: int = 768

    # Small cross-encoder reranker (22M params) — distilled quality, 5x faster
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L6-v2"
    RERANKER_MAX_LENGTH: int = 512
    RERANKER_BATCH_SIZE: int = 16

    # ColBERT late interaction (optional second-stage reranker)
    COLBERT_MODEL: str = "colbert-ir/colbertv2.0"
    COLBERT_MAX_LENGTH: int = 180
    COLBERT_TOP_K: int = 50

    # HyDE query expansion
    HYDE_ENABLED: bool = True

    # RapidOCR for scanned PDFs
    OCR_ENABLED: bool = True
    OCR_DPI: int = 150
    OCR_MIN_CHARS_PER_PAGE: int = 100

    EMBED_CACHE_SIZE: int = 128

    # Per-call intra-op thread cap for torch/BLAS (legal-bert, reranker, ColBERT).
    # Unbounded, each concurrent inference call spins up its own OpenMP thread
    # team sized to the full core count — a handful of concurrent calls (chat +
    # ingestion running together) multiplies into hundreds of OS threads and
    # everything thrashes on context switches instead of computing. Low and
    # fixed keeps total threads bounded no matter how many calls overlap.
    ML_NUM_THREADS: int = 2

    # Free-LLM Gateway (24+ providers, OpenAI-compatible)
    GATEWAY_URL: str = "http://localhost:8080/v1"
    GATEWAY_KEY: Optional[str] = None
    # Gateway model alias — gateway auto-routes to best available provider
    GATEWAY_MODEL: str = "llama-3.3-70b"

    # Direct provider keys (fallback if gateway is down)
    GROQ_API_KEY: Optional[str] = None
    NVIDIA_API_KEY: Optional[str] = None
    MISTRAL_API_KEY: Optional[str] = None
    MISTRAL_KEY: Optional[str] = None
    GOOGLE_GEMINI_KEY: Optional[str] = None
    SAMBANOVA_KEY: Optional[str] = None
    CLOUDFLARE_KEY: Optional[str] = None
    CLOUDFLARE_ACCOUNT_ID: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    TAVILY_API_KEY: Optional[str] = None
    BRAVE_SEARCH_API_KEY: Optional[str] = None

    WEB_SEARCH_MAX_RESULTS: int = 8
    WEB_SEARCH_GOVERNMENT_MAX_RESULTS: int = 5

    INTERACT_MAX_UPLOAD_MB: int = 20
    INTERACT_MAX_DOCS_PER_SESSION: int = 20

    # Government/judiciary domain-scoped web search pass — stored as JSON
    # string env var, parsed on load (mirrors AUTHORITY_TABLE's pattern)
    GOVERNMENT_SEARCH_DOMAINS: list[str] = Field(
        default_factory=lambda: list(_DEFAULT_GOVERNMENT_SEARCH_DOMAINS)
    )

    @field_validator("GOVERNMENT_SEARCH_DOMAINS", mode="before")
    @classmethod
    def parse_government_search_domains(cls, v: object) -> list[str]:
        if isinstance(v, str):
            parsed = json.loads(v)
            if not isinstance(parsed, list):
                raise ValueError("GOVERNMENT_SEARCH_DOMAINS must be a JSON array of domain strings")
            return parsed
        if isinstance(v, list):
            return v
        raise ValueError("GOVERNMENT_SEARCH_DOMAINS must be a JSON string or list")

    HYBRID_ALPHA: float = 0.5
    TOP_K_RETRIEVE: int = 20
    # Reranked chunks handed to the answer prompt. 5 starved multi-issue
    # questions (each sub-issue competes for the same 5 slots); 10 covers
    # ~2-3 distinct issues at 3-4 chunks each while staying well under
    # TOP_K_RETRIEVE's candidate pool and the LLM context/latency budget.
    TOP_K_FINAL: int = 10
    CACHE_TTL_SECONDS: int = 1800

    # Document-view basename->{key,bucket} index cache (Valkey-backed, best-effort).
    # Deliberately separate from CACHE_TTL_SECONDS (the answer cache's TTL) —
    # this index should refresh often enough that newly-ingested S3 keys become
    # resolvable without a long wait, which is a different tradeoff than the
    # answer cache's.
    DOCUMENT_INDEX_CACHE_TTL_SECONDS: int = 600

    # Document-view disk cache for downloaded PDF bytes — distinct from
    # MultiS3Loader's local_root (a fallback source of truth when no S3 bucket
    # is configured at all); this is a cache of things already fetched from S3.
    DOCUMENT_CACHE_DIR: str = "/tmp/juryai-document-cache"

    # Interact feature: per-session store for user-uploaded documents (see
    # app.core.retrieval.session_store) — kept fully separate from the
    # DOCUMENT_CACHE_DIR/Qdrant global corpus so uploads never leak between
    # sessions or pollute /ask's search results.
    SESSION_DOC_STORE_DIR: str = "/tmp/juryai-session-docs"

    # Web search scraping backends
    WIGOLO_URL: str = "http://127.0.0.1:3333"
    WIGOLO_ENABLED: bool = True
    LIGHTPANDA_BINARY: str = "lightpanda"
    LIGHTPANDA_PORT: int = 9222

    # Evidence scoring weights
    INTERNAL_CORPUS_PREMIUM: float = 1.2
    WEB_CORPUS_PENALTY: float = 0.8
    AUTHORITY_SCORE_ALPHA: float = 0.50   # relevance weight
    AUTHORITY_SCORE_BETA: float = 0.25    # authority weight
    AUTHORITY_SCORE_GAMMA: float = 0.15   # recency weight
    AUTHORITY_SCORE_DELTA: float = 0.10   # citation quality weight
    RECENCY_DECAY_LAMBDA: float = 0.05
    # Recency credit given when published_at is missing or unparseable.
    # Previously hardcoded to 1.0 (full credit) — that gave undated forum/
    # blog junk the same recency score as a same-day publication.
    RECENCY_UNKNOWN_DATE_SCORE: float = 0.5
    # Evidence below this final_score is dropped in merge_evidence() rather
    # than surviving purely by filling an otherwise-empty top-10 slot.
    # Lowered to avoid dropping all retrieved chunks when authority scores are
    # modest; v1 had no such floor, so we keep the bar permissive.
    EVIDENCE_MIN_SCORE: float = 0.1

    # Auto-sync: periodic background ingestion from S3 (minutes). 0 disables.
    AUTO_SYNC_INTERVAL_MINUTES: int = 5

    # Ingestion CPU governor — caps the sync's own CPU footprint so a large
    # batch never starves chat/API request handling on the same process.
    # The governor only ever throttles concurrency down to
    # _INGEST_MIN_CONCURRENT, never to zero — the pipeline stays alive.
    INGEST_CPU_BUDGET_PERCENT: float = 50.0
    INGEST_CPU_SAMPLE_INTERVAL_SECONDS: float = 2.0
    # How long a /ingest/status snapshot (which lists all configured S3
    # buckets) is reused before re-listing. Decouples expensive S3 listing
    # from how often the frontend polls, instead of a client-side promise.
    INGEST_STATUS_CACHE_TTL_SECONDS: float = 8.0
    # Per-file safety net only — not a run deadline. A single hung S3
    # download/parse gets killed so it doesn't hold a concurrency slot
    # forever; the overall sync (POST /ingest/s3) itself runs as a detached
    # background task with no wall-clock bound, so a large batch is never
    # cut off partway through.
    INGEST_FILE_TIMEOUT_SECONDS: float = 300.0
    INGEST_LIST_TIMEOUT_SECONDS: float = 120.0

    # PageRank for citation graph authority scoring
    PAGERANK_DAMPING: float = 0.85
    PAGERANK_MAX_ITER: int = 100
    PAGERANK_TOL: float = 1e-6

    # Intent classifier threshold
    INTENT_CLASSIFIER_THRESHOLD: float = 0.35

    # Claim verification
    CLAIM_VERIFICATION_ENABLED: bool = True
    CLAIM_EXTRACTION_MAX_CLAIMS: int = 20

    # Evaluation
    EVAL_IOU_THRESHOLD: float = 0.5
    EVAL_TEXT_OVERLAP_THRESHOLD: float = 0.3
    EVAL_K_VALUES: str = "[1, 3, 5, 10, 20]"

    # Authority lookup table — stored as JSON string env var, parsed on load
    AUTHORITY_TABLE: dict[str, float] = Field(
        default_factory=lambda: dict(_DEFAULT_AUTHORITY_TABLE)
    )

    @field_validator("AUTHORITY_TABLE", mode="before")
    @classmethod
    def parse_authority_table(cls, v: object) -> dict[str, float]:
        if isinstance(v, str):
            parsed = json.loads(v)
            if not isinstance(parsed, dict):
                raise ValueError("AUTHORITY_TABLE must be a JSON object mapping domain strings to floats")
            return parsed
        if isinstance(v, dict):
            return v
        raise ValueError("AUTHORITY_TABLE must be a JSON string or dict")

    @computed_field
    @property
    def s3_bucket_names_list(self) -> list[str]:
        """Return resolved list of S3 bucket names."""
        if self.S3_BUCKET_NAMES:
            return [b.strip() for b in self.S3_BUCKET_NAMES.split(",") if b.strip()]
        if self.S3_BUCKET_NAME:
            return [self.S3_BUCKET_NAME]
        return []

    @computed_field
    @property
    def bucket_list(self) -> list[str]:
        """Alias for s3_bucket_names_list — preferred name used by MultiS3Loader."""
        return self.s3_bucket_names_list

    @computed_field
    @property
    def llm_provider_chain(self) -> list[dict]:
        """Direct-API provider chain, called straight over HTTP (no litellm) by
        app.core.llm.provider. Groq first — fastest + most reliable free-tier
        streaming path seen in practice; the local gateway and other direct
        providers are fallbacks if Groq is unset or fails."""
        chain: list[dict] = []
        if self.GROQ_API_KEY:
            chain.append({
                "kind": "openai",
                "provider_name": "groq",
                "base_url": "https://api.groq.com/openai/v1",
                "api_key": self.GROQ_API_KEY,
                "model": "llama-3.3-70b-versatile",
            })
        if self.NVIDIA_API_KEY:
            chain.append({
                "kind": "openai",
                "provider_name": "nvidia",
                "base_url": "https://integrate.api.nvidia.com/v1",
                "api_key": self.NVIDIA_API_KEY,
                "model": "meta/llama-3.1-70b-instruct",
            })
        if self.MISTRAL_KEY or self.MISTRAL_API_KEY:
            chain.append({
                "kind": "openai",
                "provider_name": "mistral",
                "base_url": "https://api.mistral.ai/v1",
                "api_key": self.MISTRAL_KEY or self.MISTRAL_API_KEY,
                "model": "mistral-large-latest",
            })
        if self.GOOGLE_GEMINI_KEY:
            chain.append({
                "kind": "openai",
                "provider_name": "gemini",
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "api_key": self.GOOGLE_GEMINI_KEY,
                "model": "gemini-flash-latest",
            })
        if self.SAMBANOVA_KEY:
            chain.append({
                "kind": "openai",
                "provider_name": "sambanova",
                "base_url": "https://api.sambanova.ai/v1",
                "api_key": self.SAMBANOVA_KEY,
                "model": "Meta-Llama-3.3-70B-Instruct",
            })
        if self.CLOUDFLARE_KEY and self.CLOUDFLARE_ACCOUNT_ID:
            chain.append({
                "kind": "openai",
                "provider_name": "cloudflare",
                "base_url": f"https://api.cloudflare.com/client/v4/accounts/{self.CLOUDFLARE_ACCOUNT_ID}/ai/v1",
                "api_key": self.CLOUDFLARE_KEY,
                "model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
            })
        if self.GATEWAY_KEY:
            chain.append({
                "kind": "openai",
                "provider_name": "gateway",
                "base_url": self.GATEWAY_URL,
                "api_key": self.GATEWAY_KEY,
                "model": self.GATEWAY_MODEL,
            })
        if self.OPENAI_API_KEY:
            chain.append({
                "kind": "openai",
                "provider_name": "openai",
                "base_url": "https://api.openai.com/v1",
                "api_key": self.OPENAI_API_KEY,
                "model": "gpt-4o-mini",
            })
        if self.ANTHROPIC_API_KEY:
            chain.append({
                "kind": "anthropic",
                "provider_name": "anthropic",
                "api_key": self.ANTHROPIC_API_KEY,
                "model": "claude-3-5-haiku-20241022",
            })
        if not chain:
            chain.append({
                "kind": "openai",
                "provider_name": "ollama",
                "base_url": "http://localhost:11434/v1",
                "api_key": "",
                "model": "llama3.2",
            })
        return chain

    @computed_field
    @property
    def web_search_provider(self) -> str:
        if self.WIGOLO_ENABLED:
            return "wigolo"
        if self.TAVILY_API_KEY:
            return "tavily"
        if self.BRAVE_SEARCH_API_KEY:
            return "brave"
        return "duckduckgo"


# ── Auth / OTP ──────────────────────────────────────────────────────────
    # Dev fallback: when no email/SMS provider is configured, OTPs are returned
    # in the API response (and logged) so the full auth flow works offline. Set
    # AUTH_DEV_RETURN_OTP=false once real credentials are attached in production.
    AUTH_DEV_RETURN_OTP: bool = True
    AUTH_OTP_LENGTH: int = 6
    AUTH_OTP_TTL_SECONDS: int = 600          # 10 minutes
    AUTH_OTP_MAX_ATTEMPTS: int = 5
    AUTH_OTP_MIN_INTERVAL_SECONDS: int = 30  # throttle re-sends per target
    AUTH_SESSION_TTL_SECONDS: int = 604800   # 7 days
    AUTH_RESET_TOKEN_TTL_SECONDS: int = 600  # 10 minutes

    # SMTP for email OTPs / reset — unset to fall back to dev-mode delivery.
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: Optional[str] = None
    SMTP_STARTTLS: bool = True

    # SMS gateway for phone OTPs — a generic JSON POST endpoint. When unset,
    # phone OTPs fall back to dev-mode delivery (returned in the response).
    SMS_GATEWAY_URL: Optional[str] = None
    SMS_GATEWAY_KEY: Optional[str] = None
    SMS_FROM_NAME: str = "JuryAI"

    @property
    def auth_provider_status(self) -> dict:
        """Which delivery channels are wired. Drives the API's delivery field."""
        return {
            "email": bool(self.SMTP_HOST and self.SMTP_FROM),
            "sms": bool(self.SMS_GATEWAY_URL),
            "dev": bool(self.AUTH_DEV_RETURN_OTP),
        }


settings = Settings()
