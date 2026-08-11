"""Tests for web search overhaul: Wigolo + source validator fallback chain.

Coverage (13 tests):
  1.  _wigolo_available() returns False when Wigolo daemon unreachable
  2.  web_search() falls back to DuckDuckGo when Wigolo + Tavily unavailable
  3.  web_search() uses Tavily when TAVILY_API_KEY is set and Wigolo down
  4.  _clean_legal_text strips <script> tags and their content
  5.  _clean_legal_text strips <style> tags and their content
  6.  SourceValidator.validate() preserves original content when all fetches fail
  7.  content_hash is a 16-character hex string
  8.  citation_id follows "web-{index}" with 0-based indexing
  9.  authority_score >= 0.0 and all required WebEvidence fields present after web_search()
  10. _wigolo() maps markdown_content/snippet fallback and freshness_signal.published_date
  11. _httpx_fetch extracts real text from a PDF response instead of garbling bytes
  12. _httpx_fetch returns "" for genuinely non-text binary content (e.g. images)
  13. validate() skips re-fetching evidence that already has substantial content

Government-domain-scoped search pass (added in a later task):
  14. web_search() issues both a generic and a government-domain-scoped Wigolo call
  15. web_search() merges results, deduping by URL with the generic pass winning
  16. the government-scoped pass is skipped entirely when Wigolo is unavailable
  17. GOVERNMENT_SEARCH_DOMAINS parses a JSON array string like AUTHORITY_TABLE does
"""
from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.graph.state import WebEvidence
from app.core.web_search.source_validator import _clean_legal_text


# ---------------------------------------------------------------------------
# Internal helper — not re-exported by the package, so import by full path
# ---------------------------------------------------------------------------

def _make_test_evidence(**overrides) -> WebEvidence:
    base: WebEvidence = {
        "title": "Test Title",
        "url": "https://example.com",
        "content": "original snippet",
        "score": 0.5,
        "authority_score": 0.0,
        "source_type": "",
        "published_at": "",
        "retrieved_at": "2026-08-08T00:00:00+00:00",
        "content_hash": hashlib.sha256(b"original snippet").hexdigest()[:16],
        "citation_id": "web-0",
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


# ===========================================================================
# 1. _wigolo_available returns False when Wigolo daemon is unreachable
# ===========================================================================

@pytest.mark.asyncio
async def test_wigolo_available_returns_false_when_unreachable():
    """_wigolo_available() must return False when the HTTP probe raises."""
    import httpx
    import app.core.web_search.searcher as searcher_mod

    # Always force a fresh check by clearing the module-level cache
    searcher_mod._wigolo_cache = None

    # Build a mock AsyncClient whose .get() raises a connection error
    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.ConnectError("connection refused")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.core.web_search.searcher.settings") as mock_settings, \
         patch("httpx.AsyncClient", return_value=mock_client):
        mock_settings.WIGOLO_ENABLED = True
        mock_settings.WIGOLO_URL = "http://127.0.0.1:3333"

        result = await searcher_mod._wigolo_available()

    assert result is False


# ===========================================================================
# 2. web_search falls back to DuckDuckGo when Wigolo + Tavily unavailable
# ===========================================================================

@pytest.mark.asyncio
async def test_web_search_fallback_to_duckduckgo():
    """web_search() uses DuckDuckGo when Wigolo is down and no Tavily key."""
    import app.core.web_search.searcher as searcher_mod

    ddg_hit = {"title": "DDG Result", "href": "https://ddg.example.com/1", "body": "ddg content"}

    mock_ddgs = AsyncMock()
    mock_ddgs.text = AsyncMock(return_value=[ddg_hit])
    mock_ddgs.__aenter__ = AsyncMock(return_value=mock_ddgs)
    mock_ddgs.__aexit__ = AsyncMock(return_value=False)

    mock_scorer = MagicMock()
    mock_scorer.score.return_value = 0.3

    mock_validator = AsyncMock()
    mock_validator.validate = AsyncMock(side_effect=lambda ev_list: ev_list)

    # Build the WebEvidence that _duckduckgo would return
    from app.core.web_search.searcher import _make_evidence
    ddg_evidence = [_make_evidence(
        title=ddg_hit["title"],
        url=ddg_hit["href"],
        content=ddg_hit["body"],
        score=0.3,
    )]

    with patch.object(searcher_mod, "_wigolo_available", AsyncMock(return_value=False)), \
         patch.object(searcher_mod, "_duckduckgo", AsyncMock(return_value=ddg_evidence)), \
         patch("app.core.web_search.searcher.settings") as mock_settings, \
         patch("app.core.web_search.searcher.SourceValidator", return_value=mock_validator), \
         patch("app.core.web_search.searcher.get_authority_scorer", return_value=mock_scorer), \
         patch("app.core.web_search.searcher.detect_source_type", return_value="web"):

        mock_settings.TAVILY_API_KEY = None
        mock_settings.BRAVE_SEARCH_API_KEY = None

        results = await searcher_mod.web_search("test query", max_results=1)

    assert len(results) >= 1
    assert results[0]["url"] == "https://ddg.example.com/1"


# ===========================================================================
# 3. web_search uses Tavily when TAVILY_API_KEY is set and Wigolo is down
# ===========================================================================

@pytest.mark.asyncio
async def test_web_search_uses_tavily_when_key_present():
    """web_search() must prefer Tavily over DuckDuckGo when TAVILY_API_KEY is set."""
    import app.core.web_search.searcher as searcher_mod

    tavily_result = {
        "title": "Tavily Result",
        "url": "https://tavily.example.com/result",
        "content": "tavily content",
        "score": 0.8,
        "published_date": "2026-01-01",
    }

    mock_tavily_client = AsyncMock()
    mock_tavily_client.search = AsyncMock(return_value={"results": [tavily_result]})

    mock_scorer = MagicMock()
    mock_scorer.score.return_value = 0.7

    mock_validator = AsyncMock()
    mock_validator.validate = AsyncMock(side_effect=lambda ev_list: ev_list)

    with patch.object(searcher_mod, "_wigolo_available", AsyncMock(return_value=False)), \
         patch("app.core.web_search.searcher.settings") as mock_settings, \
         patch("app.core.web_search.searcher.SourceValidator", return_value=mock_validator), \
         patch("app.core.web_search.searcher.get_authority_scorer", return_value=mock_scorer), \
         patch("app.core.web_search.searcher.detect_source_type", return_value="web"), \
         patch("tavily.AsyncTavilyClient", return_value=mock_tavily_client):

        mock_settings.TAVILY_API_KEY = "fake-tavily-key"
        mock_settings.BRAVE_SEARCH_API_KEY = None

        results = await searcher_mod.web_search("legal query", max_results=1)

    assert len(results) >= 1
    assert results[0]["url"] == "https://tavily.example.com/result"


# ===========================================================================
# 4 & 5. _clean_legal_text strips <script> and <style> tags
# ===========================================================================

def test_clean_legal_text_strips_script_tag_content():
    """_clean_legal_text must exclude all content inside <script> elements."""
    html = (
        "<html><body>"
        "<script>alert('xss'); var secret = 42;</script>"
        "<p>Visible legal text here.</p>"
        "</body></html>"
    )
    result = _clean_legal_text(html)

    assert "alert" not in result, "Script body must be stripped"
    assert "xss" not in result, "Script string literal must be stripped"
    assert "secret" not in result, "Script variable must be stripped"
    assert "Visible legal text here." in result


def test_clean_legal_text_strips_style_tag_content():
    """_clean_legal_text must exclude all content inside <style> elements."""
    html = (
        "<html><head>"
        "<style>body { color: red; } .hidden { display: none; }</style>"
        "</head><body>"
        "<article>Main article content.</article>"
        "<style>.extra { margin: 0; }</style>"
        "</body></html>"
    )
    result = _clean_legal_text(html)

    assert "color: red" not in result
    assert "display: none" not in result
    assert "margin" not in result
    assert "Main article content." in result


# ===========================================================================
# 6. SourceValidator.validate() preserves content when all fetch methods fail
# ===========================================================================

@pytest.mark.asyncio
async def test_source_validator_preserves_content_when_all_fetches_fail():
    """validate() must keep original evidence.content when every fetch returns ''."""
    from app.core.web_search.source_validator import SourceValidator, _lightpanda_proc

    evidence = _make_test_evidence(content="original snippet", citation_id="web-0")
    validator = SourceValidator()

    # Patch the three methods that will actually be called when _lightpanda_proc is None:
    # _httpx_fetch, _playwright_fetch, _camoufox_fetch
    # Also patch _lightpanda_fetch in case the binary happens to be present on CI.
    with patch.object(validator, "_httpx_fetch", AsyncMock(return_value="")), \
         patch.object(validator, "_lightpanda_fetch", AsyncMock(return_value="")), \
         patch.object(validator, "_playwright_fetch", AsyncMock(return_value="")), \
         patch.object(validator, "_camoufox_fetch", AsyncMock(return_value="")):
        result = await validator.validate([evidence])

    assert len(result) == 1
    assert result[0]["content"] == "original snippet", (
        "Original content must be preserved when all fetch steps fail"
    )


# ===========================================================================
# 6b. SourceValidator.validate() fetches all URLs concurrently, not sequentially
# ===========================================================================

@pytest.mark.asyncio
async def test_source_validator_validate_fetches_concurrently():
    """Regression test: validate() used to await _fetch_content per-URL in a
    plain for-loop, so N URLs took N times as long as the slowest one (up to
    ~38s each across the httpx/Lightpanda/Playwright/Camoufox fallback tiers).
    Wall-clock time for 5 URLs at 0.2s each must stay close to 0.2s, proving
    they ran via asyncio.gather rather than sequentially."""
    import asyncio
    import time

    from app.core.web_search.source_validator import SourceValidator

    evidence_list = [
        _make_test_evidence(url=f"https://example.com/{i}", citation_id=f"web-{i}")
        for i in range(5)
    ]
    validator = SourceValidator()

    async def slow_fetch(url):
        await asyncio.sleep(0.2)
        return f"fetched content for {url}"

    with patch.object(validator, "_fetch_content", slow_fetch):
        start = time.monotonic()
        result = await validator.validate(evidence_list)
        elapsed = time.monotonic() - start

    assert len(result) == 5
    assert elapsed < 0.4, (
        f"validate() took {elapsed:.2f}s for 5 URLs at 0.2s each — "
        "expected concurrent execution close to 0.2s, got sequential-looking timing"
    )
    for i, ev in enumerate(result):
        assert ev["content"] == f"fetched content for https://example.com/{i}"


# ===========================================================================
# 7. content_hash is a 16-character hexadecimal string
# ===========================================================================

def test_content_hash_is_16_char_hex_string():
    """_make_evidence must produce a 16-char hex content_hash via sha256[:16]."""
    from app.core.web_search.searcher import _make_evidence

    content = "some legal document text for hashing"
    ev = _make_evidence(title="T", url="https://x.com", content=content, score=0.5)

    expected = hashlib.sha256(content.encode()).hexdigest()[:16]
    assert ev["content_hash"] == expected
    assert len(ev["content_hash"]) == 16
    assert all(c in "0123456789abcdef" for c in ev["content_hash"]), (
        "content_hash must contain only lowercase hex characters"
    )


# ===========================================================================
# 8. citation_id follows "web-{index}" (0-based) for every result
# ===========================================================================

@pytest.mark.asyncio
async def test_citation_id_format_is_web_index():
    """Every result's citation_id must match 'web-{0-based index}'."""
    import app.core.web_search.searcher as searcher_mod

    ddg_hits = [
        {"title": f"Result {i}", "href": f"https://example.com/{i}", "body": f"text {i}"}
        for i in range(3)
    ]

    mock_scorer = MagicMock()
    mock_scorer.score.return_value = 0.3

    mock_validator = AsyncMock()
    mock_validator.validate = AsyncMock(side_effect=lambda ev_list: ev_list)

    # Build WebEvidence list matching what _duckduckgo would produce
    from app.core.web_search.searcher import _make_evidence
    ddg_evidence = [
        _make_evidence(
            title=h["title"], url=h["href"], content=h["body"], score=0.3
        )
        for h in ddg_hits
    ]

    with patch.object(searcher_mod, "_wigolo_available", AsyncMock(return_value=False)), \
         patch.object(searcher_mod, "_duckduckgo", AsyncMock(return_value=ddg_evidence)), \
         patch("app.core.web_search.searcher.settings") as mock_settings, \
         patch("app.core.web_search.searcher.SourceValidator", return_value=mock_validator), \
         patch("app.core.web_search.searcher.get_authority_scorer", return_value=mock_scorer), \
         patch("app.core.web_search.searcher.detect_source_type", return_value="web"):

        mock_settings.TAVILY_API_KEY = None
        mock_settings.BRAVE_SEARCH_API_KEY = None

        results = await searcher_mod.web_search("query", max_results=3)

    assert len(results) == 3, "Expected exactly 3 results"
    for i, ev in enumerate(results):
        assert ev["citation_id"] == f"web-{i}", (
            f"Index {i}: expected 'web-{i}', got {ev['citation_id']!r}"
        )


# ===========================================================================
# 9. authority_score >= 0.0 and all required WebEvidence fields present
# ===========================================================================

@pytest.mark.asyncio
async def test_web_search_returns_valid_web_evidence_with_authority_score():
    """web_search() must return list[WebEvidence] with all required fields and authority_score >= 0."""
    import app.core.web_search.searcher as searcher_mod

    REQUIRED_FIELDS = {
        "title", "url", "content", "score", "authority_score",
        "source_type", "published_at", "retrieved_at", "content_hash", "citation_id",
    }

    ddg_hit = {"title": "Evidence Item", "href": "https://evidence.example.com", "body": "legal text"}

    mock_scorer = MagicMock()
    mock_scorer.score.return_value = 0.55  # non-zero to confirm it was set

    mock_validator = AsyncMock()
    mock_validator.validate = AsyncMock(side_effect=lambda ev_list: ev_list)

    from app.core.web_search.searcher import _make_evidence
    ddg_evidence = [_make_evidence(
        title=ddg_hit["title"], url=ddg_hit["href"], content=ddg_hit["body"], score=0.3
    )]

    with patch.object(searcher_mod, "_wigolo_available", AsyncMock(return_value=False)), \
         patch.object(searcher_mod, "_duckduckgo", AsyncMock(return_value=ddg_evidence)), \
         patch("app.core.web_search.searcher.settings") as mock_settings, \
         patch("app.core.web_search.searcher.SourceValidator", return_value=mock_validator), \
         patch("app.core.web_search.searcher.get_authority_scorer", return_value=mock_scorer), \
         patch("app.core.web_search.searcher.detect_source_type", return_value="legal_web"):

        mock_settings.TAVILY_API_KEY = None
        mock_settings.BRAVE_SEARCH_API_KEY = None

        results = await searcher_mod.web_search("query", max_results=1)

    assert isinstance(results, list)
    assert len(results) >= 1, "Expected at least one result"

    for ev in results:
        missing = REQUIRED_FIELDS - set(ev.keys())
        assert not missing, f"WebEvidence missing required fields: {missing}"
        assert ev["authority_score"] >= 0.0, (
            f"authority_score must be >= 0.0, got {ev['authority_score']}"
        )
        assert ev["source_type"] != "", "source_type must be populated after web_search()"


# ===========================================================================
# 10. _wigolo() maps markdown_content/snippet fallback and published_date
# ===========================================================================

@pytest.mark.asyncio
async def test_wigolo_maps_markdown_content_snippet_and_published_date():
    """_wigolo() must request include_full_markdown and correctly map
    markdown_content (falling back to snippet) and freshness_signal.published_date
    from the real wigolo /v1/search response shape."""
    import app.core.web_search.searcher as searcher_mod

    wigolo_payload = {
        "results": [
            {
                "title": "Result With Markdown",
                "url": "https://example.com/full",
                "snippet": "short snippet",
                "evidence_score": {"final": 0.75},
                "freshness_signal": {"published_date": "2025-07-01", "inferred": True},
                "markdown_content": "Full page markdown content here.",
            },
            {
                "title": "Result Without Markdown",
                "url": "https://example.com/nomd",
                "snippet": "fallback snippet text",
                "evidence_score": {"final": 0.4},
                "freshness_signal": {"published_date": "2025-06-01"},
                "fetch_failed": "stage_timeout",
            },
        ]
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = wigolo_payload

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.core.web_search.searcher.settings") as mock_settings, \
         patch("httpx.AsyncClient", return_value=mock_client):
        mock_settings.WIGOLO_URL = "http://127.0.0.1:3333"

        results = await searcher_mod._wigolo("query", 2)

    assert len(results) == 2
    assert results[0]["content"] == "Full page markdown content here."
    assert results[0]["published_at"] == "2025-07-01"
    assert results[1]["content"] == "fallback snippet text"
    assert results[1]["published_at"] == "2025-06-01"

    _, post_kwargs = mock_client.post.call_args
    assert post_kwargs["json"]["include_full_markdown"] is True


# ===========================================================================
# 11. _httpx_fetch extracts real text from a PDF response
# ===========================================================================

@pytest.mark.asyncio
async def test_httpx_fetch_extracts_text_from_pdf_content_type():
    """_httpx_fetch must extract real text from a PDF response via fitz
    instead of returning garbled raw PDF bytes decoded as text."""
    import fitz

    from app.core.web_search.source_validator import SourceValidator

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hearsay evidence must satisfy an exception.")
    pdf_bytes = doc.tobytes()
    doc.close()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/pdf"}
    mock_resp.content = pdf_bytes

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    validator = SourceValidator()
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await validator._httpx_fetch("https://example.com/doc.pdf")

    assert "Hearsay evidence must satisfy an exception." in result
    assert "%PDF" not in result


# ===========================================================================
# 12. _httpx_fetch returns "" for genuinely non-text binary content
# ===========================================================================

@pytest.mark.asyncio
async def test_httpx_fetch_returns_empty_for_non_text_binary():
    """_httpx_fetch must return '' for non-text binary content (e.g. images)
    rather than garbling raw bytes as decoded text."""
    from app.core.web_search.source_validator import SourceValidator

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "image/png"}
    mock_resp.text = "\x89PNG\r\n garbled binary data"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    validator = SourceValidator()
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await validator._httpx_fetch("https://example.com/image.png")

    assert result == ""


# ===========================================================================
# 13. validate() skips re-fetching evidence with substantial existing content
# ===========================================================================

@pytest.mark.asyncio
async def test_validate_skips_refetch_for_substantial_existing_content():
    """validate() must not re-fetch evidence that already carries substantial
    content (e.g. wigolo's own markdown_content) but must still fetch items
    that only have a short search-engine snippet."""
    from app.core.web_search.source_validator import SourceValidator

    substantial_content = "A" * 600
    evidence_list = [
        _make_test_evidence(
            url="https://wigolo.example.com/full",
            content=substantial_content,
            citation_id="web-0",
        ),
        _make_test_evidence(
            url="https://short.example.com/snippet",
            content="short snippet",
            citation_id="web-1",
        ),
    ]

    validator = SourceValidator()
    with patch.object(
        validator, "_fetch_content", AsyncMock(return_value="freshly fetched content")
    ) as mock_fetch:
        result = await validator.validate(evidence_list)

    mock_fetch.assert_called_once_with("https://short.example.com/snippet")
    assert result[0]["content"] == substantial_content
    assert result[1]["content"] == "freshly fetched content"


# ===========================================================================
# 14. web_search issues both a generic and a government-domain-scoped call
# ===========================================================================

@pytest.mark.asyncio
async def test_web_search_issues_generic_and_government_scoped_wigolo_calls():
    """When Wigolo is available, web_search() must run the generic pass AND
    a domain-scoped government pass, with include_domains covering sci.gov.in
    and at least one High Court domain."""
    import app.core.web_search.searcher as searcher_mod
    from app.core.retrieval.source_type import HIGH_COURT_DOMAINS

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": []}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    mock_scorer = MagicMock()
    mock_scorer.score.return_value = 0.3

    mock_validator = AsyncMock()
    mock_validator.validate = AsyncMock(side_effect=lambda ev_list: ev_list)

    with patch.object(searcher_mod, "_wigolo_available", AsyncMock(return_value=True)), \
         patch.object(searcher_mod, "_duckduckgo", AsyncMock(return_value=[])), \
         patch("httpx.AsyncClient", return_value=mock_client), \
         patch("app.core.web_search.searcher.settings") as mock_settings, \
         patch("app.core.web_search.searcher.SourceValidator", return_value=mock_validator), \
         patch("app.core.web_search.searcher.get_authority_scorer", return_value=mock_scorer), \
         patch("app.core.web_search.searcher.detect_source_type", return_value="web"):

        mock_settings.WIGOLO_URL = "http://127.0.0.1:3333"
        mock_settings.GOVERNMENT_SEARCH_DOMAINS = ["indiacode.nic.in", "sci.gov.in"]
        mock_settings.WEB_SEARCH_GOVERNMENT_MAX_RESULTS = 5
        mock_settings.TAVILY_API_KEY = None
        mock_settings.BRAVE_SEARCH_API_KEY = None

        await searcher_mod.web_search("test query", max_results=5)

    assert mock_client.post.call_count == 2

    calls_with_include_domains = [
        call.kwargs["json"]["include_domains"]
        for call in mock_client.post.call_args_list
        if "include_domains" in call.kwargs["json"]
    ]
    assert len(calls_with_include_domains) == 1, (
        "Exactly one of the two Wigolo calls must carry include_domains"
    )
    scoped_domains = set(calls_with_include_domains[0])
    assert "sci.gov.in" in scoped_domains
    assert scoped_domains & set(HIGH_COURT_DOMAINS), (
        "include_domains must contain at least one High Court domain"
    )


# ===========================================================================
# 15. Merge/dedupe: generic pass wins on overlapping URLs
# ===========================================================================

@pytest.mark.asyncio
async def test_web_search_merges_and_dedupes_government_results_by_url():
    """The final merged list must contain each overlapping URL exactly once
    (generic pass's version kept), plus every unique URL from both passes."""
    import app.core.web_search.searcher as searcher_mod
    from app.core.web_search.searcher import _make_evidence

    shared_url = "https://sci.gov.in/shared-judgment"
    generic_results = [
        _make_evidence(title="Generic Shared", url=shared_url, content="generic version", score=0.9),
        _make_evidence(title="Generic Only", url="https://example.com/generic-only", content="g", score=0.5),
    ]
    government_results = [
        _make_evidence(title="Government Shared", url=shared_url, content="government version", score=0.6),
        _make_evidence(title="Government Only", url="https://indiacode.nic.in/gov-only", content="gv", score=0.4),
    ]

    mock_scorer = MagicMock()
    mock_scorer.score.return_value = 0.5

    mock_validator = AsyncMock()
    mock_validator.validate = AsyncMock(side_effect=lambda ev_list: ev_list)

    with patch.object(searcher_mod, "_wigolo_available", AsyncMock(return_value=True)), \
         patch.object(searcher_mod, "_wigolo", AsyncMock(return_value=generic_results)), \
         patch.object(searcher_mod, "_wigolo_government_search", AsyncMock(return_value=government_results)), \
         patch("app.core.web_search.searcher.settings") as mock_settings, \
         patch("app.core.web_search.searcher.SourceValidator", return_value=mock_validator), \
         patch("app.core.web_search.searcher.get_authority_scorer", return_value=mock_scorer), \
         patch("app.core.web_search.searcher.detect_source_type", return_value="web"):

        mock_settings.WEB_SEARCH_GOVERNMENT_MAX_RESULTS = 5

        results = await searcher_mod.web_search("test query", max_results=5)

    urls = [ev["url"] for ev in results]
    assert urls.count(shared_url) == 1, "Shared URL must appear exactly once"
    assert set(urls) == {
        shared_url,
        "https://example.com/generic-only",
        "https://indiacode.nic.in/gov-only",
    }
    shared_entry = next(ev for ev in results if ev["url"] == shared_url)
    assert shared_entry["content"] == "generic version", (
        "Generic pass's version must win on a URL collision"
    )


# ===========================================================================
# 16. Government-scoped pass is skipped when Wigolo is unavailable
# ===========================================================================

@pytest.mark.asyncio
async def test_government_scoped_pass_skipped_when_wigolo_unavailable():
    """No second (government-scoped) call must be made when
    _wigolo_available() returns False — this feature is Wigolo-only."""
    import app.core.web_search.searcher as searcher_mod

    mock_scorer = MagicMock()
    mock_scorer.score.return_value = 0.3

    mock_validator = AsyncMock()
    mock_validator.validate = AsyncMock(side_effect=lambda ev_list: ev_list)

    mock_gov_search = AsyncMock(return_value=[])

    with patch.object(searcher_mod, "_wigolo_available", AsyncMock(return_value=False)), \
         patch.object(searcher_mod, "_wigolo_government_search", mock_gov_search), \
         patch.object(searcher_mod, "_duckduckgo", AsyncMock(return_value=[])), \
         patch("app.core.web_search.searcher.settings") as mock_settings, \
         patch("app.core.web_search.searcher.SourceValidator", return_value=mock_validator), \
         patch("app.core.web_search.searcher.get_authority_scorer", return_value=mock_scorer), \
         patch("app.core.web_search.searcher.detect_source_type", return_value="web"):

        mock_settings.TAVILY_API_KEY = None
        mock_settings.BRAVE_SEARCH_API_KEY = None

        await searcher_mod.web_search("test query", max_results=5)

    mock_gov_search.assert_not_called()


# ===========================================================================
# 17. GOVERNMENT_SEARCH_DOMAINS parses a JSON array string (env-var style)
# ===========================================================================

def test_government_search_domains_parses_json_array_string():
    """GOVERNMENT_SEARCH_DOMAINS must accept a JSON array string, mirroring
    how AUTHORITY_TABLE accepts a JSON object string from the environment."""
    from app.config.settings import Settings

    cfg = Settings(GOVERNMENT_SEARCH_DOMAINS='["indiacode.nic.in", "sci.gov.in"]')

    assert cfg.GOVERNMENT_SEARCH_DOMAINS == ["indiacode.nic.in", "sci.gov.in"]
