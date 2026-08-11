"""Authority scoring for legal document chunks and web evidence.

Multi-factor formula
--------------------
    z_relevance = clip(query_relevance, 0, 1)
    authority   = AUTHORITY_TABLE.get(source_type, default)
    recency     = exp(-λ * years_since)        # years_since=0 if date unknown
    citation_q  = log(1 + cites) / log(1 + MAX_CITATIONS)
    score       = α*z_relevance + β*authority + γ*recency + δ*citation_q

All weights (α, β, γ, δ) are loaded from settings; they MUST sum to 1.0.
"""
from __future__ import annotations
import math
from datetime import datetime, timezone
from functools import lru_cache

from app.config.settings import settings

# Maximum citation count used for citation-quality normalisation.
# This is a MODULE-LEVEL CONSTANT — not configurable via settings.
MAX_CITATIONS: int = 1000


class AuthorityScorer:
    """Multi-factor authority scorer for legal chunks and web evidence.

    Initialised from application settings so that weights and the authority
    lookup table are overridable via environment variables without code changes.
    """

    def __init__(self) -> None:
        # Authority lookup table — keys are source_type strings or domain names;
        # falls back to the "default" key when source_type is not found.
        self._table: dict[str, float] = dict(settings.AUTHORITY_TABLE)
        self._alpha: float = settings.AUTHORITY_SCORE_ALPHA
        self._beta: float = settings.AUTHORITY_SCORE_BETA
        self._gamma: float = settings.AUTHORITY_SCORE_GAMMA
        self._delta: float = settings.AUTHORITY_SCORE_DELTA
        self._lambda: float = settings.RECENCY_DECAY_LAMBDA

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(
        self,
        chunk_or_evidence: dict,
        query_relevance: float,
        published_at: str | None = None,
        citation_count: int = 0,
    ) -> float:
        """Compute the composite authority score for a chunk or evidence dict.

        Parameters
        ----------
        chunk_or_evidence:
            A ScoredChunk or WebEvidence dict.  ``source_type`` is extracted
            from this dict to drive the authority lookup.
        query_relevance:
            Reranker relevance score for this chunk (expected range 0–1).
        published_at:
            ISO-8601 date/datetime string of publication, or None if unknown.
            Unknown dates produce recency=1.0 (no penalty).
        citation_count:
            Number of citations this document has received.

        Returns
        -------
        float
            Composite score in [0, 1].
        """
        source_type: str = chunk_or_evidence.get("source_type") or ""
        z_relevance: float = max(0.0, min(1.0, query_relevance))
        authority: float = self._authority(source_type)
        recency: float = self._recency(published_at)
        citation_q: float = math.log1p(citation_count) / math.log1p(MAX_CITATIONS)

        return (
            self._alpha * z_relevance
            + self._beta * authority
            + self._gamma * recency
            + self._delta * citation_q
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _authority(self, source_type: str) -> float:
        """Look up authority score from AUTHORITY_TABLE; fall back to default."""
        return self._table.get(source_type, self._table.get("default", 0.60))

    def _recency(self, published_at: str | None) -> float:
        """Compute recency decay; returns 1.0 (no decay) when date is unknown."""
        if not published_at:
            return 1.0
        try:
            pub_dt = _parse_iso(published_at)
            now = datetime.now(tz=timezone.utc)
            years_since = max(0.0, (now - pub_dt).days / 365.25)
            return math.exp(-self._lambda * years_since)
        except (ValueError, TypeError, OverflowError):
            return 1.0  # unparseable date — no recency penalty


def _parse_iso(date_str: str) -> datetime:
    """Parse an ISO-8601 date/datetime string into an aware datetime.

    Handles common variants:
    - Date-only: ``"2023-01-15"``
    - Datetime with Z suffix: ``"2023-01-15T10:30:00Z"``
    - Datetime with offset: ``"2023-01-15T10:30:00+05:30"``
    - Datetime with space separator: ``"2023-01-15 10:30:00"``
    """
    s = date_str.strip()
    # Normalise Z suffix to +00:00 for Python < 3.11 compatibility
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    # Replace space separator with T
    s = s.replace(" ", "T")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@lru_cache(maxsize=1)
def get_authority_scorer() -> AuthorityScorer:
    """Return the singleton AuthorityScorer instance (lru_cache-backed)."""
    return AuthorityScorer()
