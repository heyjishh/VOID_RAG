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
    "supremecourt.gov": 1.0,
    "law.cornell.edu": 0.95,
    "sci.gov.in": 0.95,
    "indiankanoon.org": 0.90,
    "judis.nic.in": 0.90,
    "manupatra.com": 0.85,
    "pubmed.ncbi.nlm.nih.gov": 0.85,
    "barandbench.com": 0.75,
    "livelaw.in": 0.75,
    "jstor.org": 0.80,
    "wikipedia.org": 0.50,
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

    EMBED_MODEL: str = "BAAI/bge-small-en-v1.5"
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"
    EMBED_DIM: int = 384
    EMBED_CACHE_SIZE: int = 128

    # Free-LLM Gateway (24+ providers, OpenAI-compatible)
    GATEWAY_URL: str = "http://localhost:8080/v1"
    GATEWAY_KEY: Optional[str] = None
    # Gateway model alias — gateway auto-routes to best available provider
    GATEWAY_MODEL: str = "llama-3.3-70b"

    # Direct provider keys (fallback if gateway is down)
    GROQ_API_KEY: Optional[str] = None
    MISTRAL_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    TAVILY_API_KEY: Optional[str] = None
    BRAVE_SEARCH_API_KEY: Optional[str] = None

    WEB_SEARCH_MAX_RESULTS: int = 8
    WEB_SEARCH_GOVERNMENT_MAX_RESULTS: int = 5

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
    TOP_K_FINAL: int = 5
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
        chain = []
        # Gateway first — 260+ models, auto-fallback within gateway
        if self.GATEWAY_KEY:
            chain.append({
                "model": f"openai/{self.GATEWAY_MODEL}",
                "api_key": self.GATEWAY_KEY,
                "api_base": self.GATEWAY_URL,
            })
        # Direct providers as fallback
        if self.GROQ_API_KEY:
            chain.append({"model": "groq/llama-3.3-70b-versatile", "api_key": self.GROQ_API_KEY})
        if self.MISTRAL_API_KEY:
            chain.append({"model": "mistral/mistral-large-latest", "api_key": self.MISTRAL_API_KEY})
        if self.OPENAI_API_KEY:
            chain.append({"model": "openai/gpt-4o-mini", "api_key": self.OPENAI_API_KEY})
        if self.ANTHROPIC_API_KEY:
            chain.append({"model": "anthropic/claude-3-5-haiku-20241022", "api_key": self.ANTHROPIC_API_KEY})
        if not chain:
            chain.append({"model": "ollama/llama3.2", "api_key": ""})
        return chain

    @computed_field
    @property
    def web_search_provider(self) -> str:
        if self.TAVILY_API_KEY:
            return "tavily"
        if self.BRAVE_SEARCH_API_KEY:
            return "brave"
        return "duckduckgo"


settings = Settings()
