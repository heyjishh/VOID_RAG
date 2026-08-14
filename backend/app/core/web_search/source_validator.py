"""Source validator — fetch pipeline for web evidence.

Fetch order per URL (first success wins):
  a. plain httpx (timeout 8 s)
  b. Lightpanda CDP via playwright.connect_over_cdp (only if binary started)
  c. standard playwright chromium headless
  d. camoufox

Each browser step is capped at 10 s.  All failures are logged at DEBUG only.
Lightpanda, playwright and camoufox are optional dependencies; missing packages
silently skip that step.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import shutil
import subprocess
from html.parser import HTMLParser
from urllib.parse import urlparse

import fitz
import httpx

from app.config.settings import settings
from app.core.graph.state import WebEvidence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level Lightpanda process (started once at import, if binary found)
# ---------------------------------------------------------------------------

_lightpanda_proc: subprocess.Popen | None = None  # noqa: UP007


def _start_lightpanda() -> None:
    """Launch Lightpanda serve in the background if binary is on PATH."""
    global _lightpanda_proc
    if shutil.which(settings.LIGHTPANDA_BINARY) is None:
        return
    try:
        _lightpanda_proc = subprocess.Popen(
            [
                settings.LIGHTPANDA_BINARY,
                "serve",
                "--host", "127.0.0.1",
                "--port", str(settings.LIGHTPANDA_PORT),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.debug("Started Lightpanda PID=%d", _lightpanda_proc.pid)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to start Lightpanda: %s", exc)
        _lightpanda_proc = None


_start_lightpanda()


# ---------------------------------------------------------------------------
# HTML text extractor — stdlib html.parser only, no third-party HTML libs
# ---------------------------------------------------------------------------

class _HTMLTextExtractor(HTMLParser):
    """Extract visible text from HTML, skipping non-content elements."""

    _SKIP_TAGS: frozenset[str] = frozenset({
        "script", "style", "nav", "header", "footer",
        "noscript", "aside", "form", "menu", "button",
        "svg", "iframe", "template",
    })
    _BLOCK_TAGS: frozenset[str] = frozenset({
        "p", "div", "li", "br", "tr", "td", "th",
        "h1", "h2", "h3", "h4", "h5", "h6",
        "blockquote", "article", "section",
    })

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth: int = 0
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        lname = tag.lower()
        if lname in self._SKIP_TAGS:
            self._skip_depth += 1
        elif lname in self._BLOCK_TAGS and self._skip_depth == 0:
            # Insert a separator so block elements don't run words together
            self._buf.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._buf.append(stripped)


def _clean_legal_text(html_str: str) -> str:
    """Strip HTML tags, scripts, styles and return normalised visible text.

    Uses stdlib ``html.parser`` only — no third-party HTML libraries.
    """
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(html_str)
    except Exception:  # noqa: BLE001
        pass
    text = " ".join(extractor._buf)
    # Normalise runs of whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# SourceValidator
# ---------------------------------------------------------------------------

_USER_AGENT = "Mozilla/5.0 (compatible; JuryAI/1.0; +https://juryai.in)"
_SUBSTANTIAL_CONTENT_MIN_CHARS = 500


class SourceValidator:
    """Populate ``content`` for each WebEvidence via a multi-step fetch pipeline."""

    async def validate(
        self,
        evidence_list: list[WebEvidence],
        on_step: callable | None = None,
    ) -> list[WebEvidence]:
        """Fetch full page content for every evidence item.

        For each URL, attempts fetch methods in priority order.  If all methods
        fail the original snippet content is preserved unchanged.

        Runs every URL's fetch concurrently — sequential awaits meant one slow
        or unreachable URL (up to ~38s worst case across all four fetch tiers)
        blocked every URL behind it, turning a 5-source web search into
        minutes of dead air on the reasoning timeline.

        ``on_step(dict)`` is invoked as each source completes (or is skipped)
        so the reasoning timeline can show live fetch progress.
        """
        needs_fetch = [
            i for i, ev in enumerate(evidence_list)
            if len(ev.get("content", "")) < _SUBSTANTIAL_CONTENT_MIN_CHARS
        ]
        skipped = len(evidence_list) - len(needs_fetch)
        done_count = 0

        async def _fetch_and_report(index: int) -> str:
            nonlocal done_count
            content = await self._fetch_content(evidence_list[index]["url"])
            done_count += 1
            if on_step:
                url = evidence_list[index]["url"]
                domain = urlparse(url).netloc or url
                on_step({
                    "step": "web_search_fetch_progress",
                    "detail": f"Fetching sources {done_count}/{len(needs_fetch)} — {domain}",
                    "done": done_count,
                    "total": len(needs_fetch),
                    "domain": domain,
                })
            return content

        contents = await asyncio.gather(
            *(_fetch_and_report(i) for i in needs_fetch)
        )
        if on_step and skipped:
            on_step({
                "step": "web_search_fetch_progress",
                "detail": f"{skipped} sources already have full text",
                "done": len(needs_fetch),
                "total": len(needs_fetch),
            })
        for i, content in zip(needs_fetch, contents):
            if content:
                evidence_list[i]["content"] = content
                evidence_list[i]["content_hash"] = hashlib.sha256(content.encode()).hexdigest()[:16]
        return evidence_list

    # ------------------------------------------------------------------
    # Fetch pipeline — each helper returns "" on any failure
    # ------------------------------------------------------------------

    async def _fetch_content(self, url: str) -> str:
        """Try fetch methods in order; return first non-empty result."""
        # a. plain httpx
        content = await self._httpx_fetch(url)
        if content:
            return content

        # b. Lightpanda CDP (only when the process was started at module import)
        if _lightpanda_proc is not None:
            content = await self._lightpanda_fetch(url)
            if content:
                return content

        # c. standard Playwright
        content = await self._playwright_fetch(url)
        if content:
            return content

        # d. Camoufox
        content = await self._camoufox_fetch(url)
        return content  # empty string when all methods failed

    async def _httpx_fetch(self, url: str) -> str:
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    timeout=8.0,
                    headers={"User-Agent": _USER_AGENT},
                )
                if resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "").lower()
                    is_pdf = (
                        "application/pdf" in content_type
                        or url.lower().split("?", 1)[0].endswith(".pdf")
                    )
                    if is_pdf:
                        return self._extract_pdf_text(resp.content)
                    if (
                        content_type == ""
                        or "text" in content_type
                        or "html" in content_type
                        or "xml" in content_type
                        or "json" in content_type
                    ):
                        return _clean_legal_text(resp.text)
                    return ""
        except Exception as exc:  # noqa: BLE001
            logger.debug("httpx fetch failed for %s: %s", url, exc)
        return ""

    def _extract_pdf_text(self, data: bytes) -> str:
        try:
            doc = fitz.open(stream=data, filetype="pdf")
            pages = [page.get_text().strip() for page in doc]
            return "\n\n".join(page for page in pages if page)
        except Exception as exc:  # noqa: BLE001
            logger.debug("PDF text extraction failed: %s", exc)
            return ""

    async def _lightpanda_fetch(self, url: str) -> str:
        try:
            from playwright.async_api import async_playwright  # type: ignore[import]
            async with async_playwright() as p:
                browser = await asyncio.wait_for(
                    p.chromium.connect_over_cdp(
                        f"ws://127.0.0.1:{settings.LIGHTPANDA_PORT}"
                    ),
                    timeout=10.0,
                )
                page = await browser.new_page()
                await asyncio.wait_for(page.goto(url), timeout=10.0)
                html = await page.content()
                await browser.close()
                return _clean_legal_text(html)
        except ImportError:
            logger.debug("playwright not installed — Lightpanda step skipped")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Lightpanda fetch failed for %s: %s", url, exc)
        return ""

    async def _playwright_fetch(self, url: str) -> str:
        try:
            from playwright.async_api import async_playwright  # type: ignore[import]
            async with async_playwright() as p:
                browser = await asyncio.wait_for(
                    p.chromium.launch(headless=True),
                    timeout=10.0,
                )
                page = await browser.new_page()
                await asyncio.wait_for(page.goto(url), timeout=10.0)
                html = await page.content()
                await browser.close()
                return _clean_legal_text(html)
        except ImportError:
            logger.debug("playwright not installed — standard Playwright step skipped")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Playwright fetch failed for %s: %s", url, exc)
        return ""

    async def _camoufox_fetch(self, url: str) -> str:
        try:
            from camoufox.async_api import AsyncCamoufox  # type: ignore[import]
            async with AsyncCamoufox(os="linux") as browser:
                page = await browser.new_page()
                await asyncio.wait_for(page.goto(url), timeout=10.0)
                html = await page.content()
                await page.close()
                return _clean_legal_text(html)
        except ImportError:
            logger.debug("camoufox not installed — Camoufox step skipped")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Camoufox fetch failed for %s: %s", url, exc)
        return ""
