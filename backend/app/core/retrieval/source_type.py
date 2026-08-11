"""Legal source type detection from URL, filename, and metadata.

Priority: URL (if non-empty) -> filename -> "unknown".
For internal S3 documents (url=""), the default when no filename pattern
matches is ``"case_doc"`` (not ``"unknown"``).
"""
from __future__ import annotations
import re
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# High Court domain list — must be a set for O(1) lookup, not an if/elif chain
# ---------------------------------------------------------------------------
HIGH_COURT_DOMAINS: frozenset[str] = frozenset({
    "hcbombay.nic.in",
    "delhihighcourt.nic.in",
    "hcallahabad.nic.in",
    "highcourt.mp.nic.in",
    "hcraj.nic.in",
    "highcourt.gujarat.gov.in",
    "hckerala.nic.in",
    "hcmadras.nic.in",
    "calcuttahighcourt.nic.in",
    "highcourtchd.gov.in",
    "ghcl.nic.in",
    "highcourtofandhrapradesh.gov.in",
    "hcandaman.nic.in",
    "gauhati.nic.in",
    "patnahighcourt.gov.in",
    "jharkhandhighcourt.nic.in",
    "chhattisgarhhighcourt.gov.in",
    "bombayhighcourt.nic.in",
})

# ---------------------------------------------------------------------------
# Compiled URL-based regex patterns: (compiled_pattern, source_type).
# Order matters — first match wins.
# ---------------------------------------------------------------------------
_URL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Supreme Court of India official portal
    (re.compile(r"(?:^|\.)sci\.gov\.in$", re.I), "supreme_court_judgment"),
    # Indian Code — central statutes database
    (re.compile(r"(?:^|\.)indiacode\.nic\.in$", re.I), "statute"),
    # Ministry of Law — legislative texts
    (re.compile(r"(?:^|\.)legislative\.gov\.in$", re.I), "statute"),
    # e-Gazette (must come before generic *.gov.in catch-all)
    (re.compile(r"(?:^|\.)egazette\.gov\.in$", re.I), "government_notification"),
    # Legal news outlets — grouped regex avoids per-domain hardcoding
    (re.compile(r"(?:^|\.)(?:taxmann|barandbench|livelaw|lawstreet)\.(?:com|in|co)$", re.I), "legal_news"),
    # Social / Q&A forums
    (re.compile(r"(?:^|\.)(?:reddit|quora)\.com$", re.I), "forum"),
    # Generic *.gov.in catch-all — MUST be last gov.in rule
    (re.compile(r"(?:^|\.)gov\.in$", re.I), "government_notification"),
]

# Regex for Indian Kanoon — needs separate path/metadata inspection
_INDIANKANOON_RE: re.Pattern[str] = re.compile(r"(?:^|\.)indiankanoon\.org$", re.I)
_BLOG_HOST_RE: re.Pattern[str] = re.compile(r"^blog\.", re.I)
_BLOG_PATH_RE: re.Pattern[str] = re.compile(r"/blog/", re.I)

# ---------------------------------------------------------------------------
# Compiled filename patterns for internal S3 documents: (pattern, source_type).
# Order matters — first match wins.
# ---------------------------------------------------------------------------
_FILENAME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # SC_* / SCI_* / supreme* → Supreme Court
    (re.compile(r"^(?:SC_|SCI_|supreme)", re.I), "supreme_court_judgment"),
    # HC_* / high_court* → High Court
    (re.compile(r"^(?:HC_|high_court)", re.I), "high_court_judgment"),
    # *_act* / *_statute* / *_code* → statute
    (re.compile(r"_(?:act|statute|code)", re.I), "statute"),
    # notification* / circular* / gazette* → government notification
    (re.compile(r"^(?:notification|circular|gazette)", re.I), "government_notification"),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_source_type(
    url: str = "",
    filename: str | None = None,
    metadata: dict | None = None,
) -> str:
    """Detect the legal source type from a URL, filename, or metadata.

    Parameters
    ----------
    url:
        Full URL string. When non-empty, URL-based detection takes priority.
    filename:
        Local path or S3 key. Used when ``url`` is empty (internal docs).
    metadata:
        Optional dict with auxiliary fields (e.g. ``"title"``).  Used by
        Indian Kanoon detection to distinguish SC vs HC judgments.

    Returns
    -------
    str
        One of: ``supreme_court_judgment``, ``high_court_judgment``,
        ``statute``, ``government_notification``, ``legal_news``, ``blog``,
        ``forum``, ``case_doc`` (internal default), or ``unknown``.
    """
    if url:
        return _detect_from_url(url, metadata or {})
    if filename:
        return _detect_from_filename(filename)
    return "unknown"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_from_url(url: str, metadata: dict) -> str:
    """Return source type detected from a URL string."""
    parsed = urlparse(url if "://" in url else "https://" + url)
    hostname: str = parsed.hostname or ""
    path: str = parsed.path

    # 1. High Court domains — set membership, O(1), no if/elif chain
    if hostname in HIGH_COURT_DOMAINS:
        return "high_court_judgment"

    # 2. Indian Kanoon — needs path + metadata to distinguish SC vs HC
    if _INDIANKANOON_RE.search(hostname):
        if "/doc/" in path:
            title: str = metadata.get("title") or ""
            if "Supreme Court" in title:
                return "supreme_court_judgment"
        return "high_court_judgment"

    # 3. Blog detection: subdomain prefix OR /blog/ path segment
    if _BLOG_HOST_RE.match(hostname) or _BLOG_PATH_RE.search(path):
        return "blog"

    # 4. Regex-pattern table (order matters — see _URL_PATTERNS)
    for pattern, source_type in _URL_PATTERNS:
        if pattern.search(hostname):
            return source_type

    return "unknown"


def _detect_from_filename(filename: str) -> str:
    """Return source type detected from a filename / S3 key.

    Falls back to ``"case_doc"`` (the internal-document default), never
    ``"unknown"``, because a filename arriving here is always an internal doc.
    """
    # Use only the basename for matching — strip any leading path components
    basename = filename.rsplit("/", 1)[-1]
    for pattern, source_type in _FILENAME_PATTERNS:
        if pattern.search(basename):
            return source_type
    return "case_doc"
