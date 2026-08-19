"""Web search with provider priority: Wigolo → Tavily → Brave → DuckDuckGo.

After search results are collected they are piped through SourceValidator
(full-page fetch chain) and then enriched with source type detection and
authority scores.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config.settings import settings
from app.core.graph.state import WebEvidence
from app.core.retrieval.authority_scorer import get_authority_scorer
from app.core.retrieval.reranker import get_reranker
from app.core.retrieval.source_type import HIGH_COURT_DOMAINS, detect_source_type
from app.core.web_search.source_validator import SourceValidator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Wigolo availability cache
# ---------------------------------------------------------------------------

_wigolo_cache: Optional[tuple[float, bool]] = None  # noqa: UP007
_WIGOLO_CACHE_TTL: float = 60.0  # seconds


async def _wigolo_available() -> bool:
    """Return True if the Wigolo search daemon is reachable.

    Uses ``GET {WIGOLO_URL}/openapi.json`` with a 1-second timeout.
    Result is cached for 60 seconds using ``asyncio.get_event_loop().time()``.
    """
    global _wigolo_cache

    if not settings.WIGOLO_ENABLED:
        return False

    now: float = asyncio.get_running_loop().time()

    if _wigolo_cache is not None:
        ts, cached_result = _wigolo_cache
        if now - ts < _WIGOLO_CACHE_TTL:
            return cached_result

    available: bool = False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.WIGOLO_URL}/openapi.json",
                timeout=1.0,
            )
        available = resp.status_code == 200
    except Exception as exc:  # noqa: BLE001
        logger.debug("Wigolo availability check failed: %s", exc)

    _wigolo_cache = (now, available)
    return available


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_evidence(
    *,
    title: str,
    url: str,
    content: str,
    score: float,
    published_at: str = "",
) -> WebEvidence:
    """Build a WebEvidence dict with placeholder fields filled in."""
    return {
        "title": title,
        "url": url,
        "content": content,
        "score": score,
        "authority_score": 0.0,   # populated after source validation
        "source_type": "",        # populated after source validation
        "published_at": published_at,
        "retrieved_at": _now_iso(),
        "content_hash": hashlib.sha256(content.encode()).hexdigest()[:16],
        "citation_id": "",        # assigned by web_search() after collecting all results
    }


# ---------------------------------------------------------------------------
# Provider implementations — each returns list[WebEvidence]
# ---------------------------------------------------------------------------

def _parse_wigolo_results(data: dict) -> list[WebEvidence]:
    """Map a Wigolo ``/v1/search`` JSON response into WebEvidence entries."""
    evidence: list[WebEvidence] = []
    for r in data.get("results", []):
        content: str = r.get("markdown_content", "") or r.get("snippet", "")
        score: float = float(
            (r.get("evidence_score") or {}).get("final", 0.0)
        )
        published_at: str = (
            (r.get("freshness_signal") or {}).get("published_date", "") or ""
        )
        evidence.append(
            _make_evidence(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=content,
                score=score,
                published_at=published_at,
            )
        )
    return evidence


async def _wigolo(query: str, max_results: int) -> list[WebEvidence]:
    """Search via the self-hosted Wigolo daemon."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.WIGOLO_URL}/v1/search",
                json={
                    "query": query,
                    "max_results": max_results,
                    "include_full_markdown": True,
                },
                timeout=30.0,
            )
        return _parse_wigolo_results(resp.json())
    except Exception as exc:  # noqa: BLE001
        logger.debug("Wigolo search failed: %s", exc)
        return []


async def _wigolo_government_search(query: str, max_results: int) -> list[WebEvidence]:
    """Search via Wigolo scoped to official Indian government/judiciary domains."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.WIGOLO_URL}/v1/search",
                json={
                    "query": query,
                    "max_results": max_results,
                    "include_full_markdown": True,
                    "include_domains": sorted(
                        set(settings.GOVERNMENT_SEARCH_DOMAINS) | HIGH_COURT_DOMAINS
                    ),
                },
                timeout=30.0,
            )
        return _parse_wigolo_results(resp.json())
    except Exception as exc:  # noqa: BLE001
        logger.debug("Wigolo government-domain search failed: %s", exc)
        return []


async def _tavily(query: str, max_results: int) -> list[WebEvidence]:
    """Search via the Tavily API (requires TAVILY_API_KEY)."""
    try:
        from tavily import AsyncTavilyClient  # optional dep
        client = AsyncTavilyClient(api_key=settings.TAVILY_API_KEY)
        resp = await client.search(query, max_results=max_results)
        return [
            _make_evidence(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
                score=float(r.get("score", 0.0)),
                published_at=r.get("published_date", "") or "",
            )
            for r in resp.get("results", [])
        ]
    except Exception as exc:  # noqa: BLE001
        logger.debug("Tavily search failed: %s", exc)
        return []


async def _brave(query: str, max_results: int) -> list[WebEvidence]:
    """Search via the Brave Search API (requires BRAVE_SEARCH_API_KEY)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max_results},
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": settings.BRAVE_SEARCH_API_KEY or "",
                },
                timeout=15.0,
            )
        if resp.status_code != 200:
            return []
        return [
            _make_evidence(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("description", ""),
                score=0.5,
            )
            for r in resp.json().get("web", {}).get("results", [])
        ]
    except Exception as exc:  # noqa: BLE001
        logger.debug("Brave search failed: %s", exc)
        return []


async def _duckduckgo(query: str, max_results: int) -> list[WebEvidence]:
    """Search via DuckDuckGo (no API key required).

    Runs two searches concurrently — one broad and one scoped to
    indiankanoon.org (the most comprehensive free Indian legal database) —
    then deduplicates by URL. This compensates for DuckDuckGo's tendency to
    return generic results for Indian legal queries.
    """
    try:
        from ddgs import DDGS  # optional dep
    except ImportError:
        logger.debug("ddgs not installed — DuckDuckGo step skipped")
        return []

    loop = asyncio.get_running_loop()

    def _broad():
        return list(DDGS().text(query, max_results=max_results))

    def _scoped():
        return list(DDGS().text(
            f"site:indiankanoon.org {query}",
            max_results=min(max_results, 3),
        ))

    try:
        broad_hits, scoped_hits = await asyncio.gather(
            loop.run_in_executor(None, _broad),
            loop.run_in_executor(None, _scoped),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("DuckDuckGo search failed: %s", exc)
        return []

    seen_urls: set[str] = set()
    evidence: list[WebEvidence] = []
    for r in (scoped_hits or []) + (broad_hits or []):
        url = r.get("href", "")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        evidence.append(
            _make_evidence(
                title=r.get("title", ""),
                url=url,
                content=r.get("body", ""),
                score=0.3,
            )
        )
    return evidence


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def web_search(
    query: str,
    max_results: int = 5,
    on_step: Optional[callable] = None,
) -> list[WebEvidence]:
    """Search the web and return validated, authority-scored evidence.

    Provider priority
    -----------------
    1. Wigolo  — self-hosted daemon; fastest, richest metadata
    2. Tavily  — requires ``TAVILY_API_KEY``
    3. Brave   — requires ``BRAVE_SEARCH_API_KEY``
    4. DuckDuckGo — always-available free fallback

    After collection results are run through :class:`SourceValidator` to fetch
    full page content, then re-scored against ``query`` by the same
    cross-encoder reranker used for internal chunks (replacing each
    provider's own keyword-matching score with genuine semantic relevance),
    then ``detect_source_type`` and ``AuthorityScorer`` populate
    ``source_type`` and ``authority_score``.

    ``on_step(dict)`` is invoked as phases complete (provider chosen, sources
    fetched, scoring) so callers can surface real-time progress on the
    reasoning timeline instead of one static "searching…" step covering the
    whole pipeline.
    """
    def _report(step: str, detail: str, **extra) -> None:
        if on_step:
            on_step({"step": step, "detail": detail, **extra})

    results: list[WebEvidence] = []

    # 1. Wigolo (self-hosted, highest priority) — generic pass plus a
    # domain-scoped government/judiciary pass run concurrently. The
    # government pass is Wigolo-only: only Wigolo's /v1/search supports
    # include_domains, so Tavily/Brave/DuckDuckGo have no equivalent.
    if await _wigolo_available():
        _report("web_search_provider", "Searching the web via the self-hosted daemon")
        results, government_results = await asyncio.gather(
            _wigolo(query, max_results),
            _wigolo_government_search(query, settings.WEB_SEARCH_GOVERNMENT_MAX_RESULTS),
        )
        seen_urls = {ev["url"] for ev in results}
        # First-seen wins: the generic pass already ranked/scored this URL,
        # so the government pass must not overwrite or duplicate it.
        for ev in government_results:
            if ev["url"] not in seen_urls:
                results.append(ev)
                seen_urls.add(ev["url"])

    # 2. Tavily
    if not results and settings.TAVILY_API_KEY:
        _report("web_search_provider", "Searching via Tavily")
        results = await _tavily(query, max_results)

    # 3. Brave
    if not results and settings.BRAVE_SEARCH_API_KEY:
        _report("web_search_provider", "Searching via Brave")
        results = await _brave(query, max_results)

    # 4. DuckDuckGo (always-available free fallback)
    if not results:
        _report("web_search_provider", "Searching via DuckDuckGo")
        results = await _duckduckgo(query, max_results)

    # Fetch full content via source validator fallback chain
    if results:
        _report(
            "web_search_fetch",
            f"Fetching full text of {len(results)} web sources",
            total=len(results),
        )
    validator = SourceValidator()
    results = await validator.validate(results, on_step=on_step)

    # Assign citation IDs by final list position (0-based)
    for i, ev in enumerate(results):
        ev["citation_id"] = f"web-{i}"

    # Replace each provider's own keyword-matching score with genuine
    # semantic relevance to the actual question, via the same cross-encoder
    # used for internal chunks — otherwise authority scoring below trusts
    # whatever heuristic the search provider used internally.
    if results:
        _report(
            "web_search_scoring",
            f"Scoring {len(results)} sources against your question",
            total=len(results),
        )
        relevance_scores = get_reranker().score_pairs(
            query, [ev.get("content", "") for ev in results]
        )
        for ev, rel in zip(results, relevance_scores):
            ev["score"] = rel

    # Enrich with source type and authority score
    authority_scorer = get_authority_scorer()
    for ev in results:
        ev["source_type"] = detect_source_type(url=ev["url"])
        ev["authority_score"] = authority_scorer.score(
            ev,
            query_relevance=ev["score"],
            published_at=ev["published_at"] or None,
        )

    return results
