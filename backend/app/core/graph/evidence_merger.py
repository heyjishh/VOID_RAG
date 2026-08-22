"""Evidence merger: combines internal legal corpus chunks with web evidence.

Applies authority-based scoring, deduplicates by content_hash, and returns
the top-10 items sorted by final_score descending.
"""
from __future__ import annotations

import hashlib

from app.core.retrieval.authority_scorer import find_superseded_statute

# Source types that bypass the web corpus penalty — these are primary legal sources.
_AUTHORITATIVE_WEB_TYPES: frozenset[str] = frozenset({
    "supreme_court_judgment",
    "statute",
    "constitutional",
    "government_notification",
    "high_court_judgment",
})


def content_hash_for(item: dict) -> str:
    """Stable id for an evidence item — sha256(text)[:16], reused if already
    present (e.g. WebEvidence already carries one from web_search).
    """
    return item.get("content_hash") or hashlib.sha256(
        item.get("text", "").encode()
    ).hexdigest()[:16]


def ensure_content_hashes(items: list[dict]) -> list[dict]:
    """Attach a content_hash to every item that lacks one (idempotent).

    The verifier needs a stable id on every evidence item it sees, regardless
    of which graph produced it — legacy ``ScoredChunk`` items never pass
    through ``merge_evidence`` and would otherwise reach the verifier unhashed.
    """
    return [
        item if item.get("content_hash") else {**item, "content_hash": content_hash_for(item)}
        for item in items
    ]


def merge_evidence(
    legal_chunks: list[dict],
    web_evidence: list[dict],
    settings,
    as_of_date: str | None = None,
) -> list[dict]:
    """Merge and authority-score internal chunks and web evidence.

    Scoring rules
    -------------
    - Internal: ``final_score = chunk["authority_score"] * settings.INTERNAL_CORPUS_PREMIUM``
    - Web authoritative (supreme_court_judgment / statute / constitutional):
      ``final_score = evidence["authority_score"]``  (no penalty)
    - Web other:
      ``final_score = evidence["authority_score"] * settings.WEB_CORPUS_PENALTY``

    After scoring:
    - Drop items with ``final_score < settings.EVIDENCE_MIN_SCORE`` — without
      this floor, low-quality items (e.g. an unclassifiable forum post) could
      still occupy a top-10 slot purely because nothing else was competing
      for it, not because they were actually good evidence.
    - Deduplicate by ``content_hash`` (keep item with highest final_score).
    - Sort descending by final_score.
    - Return top 10.
    - Each item is tagged with ``"domain": "internal"`` or ``"domain": "web"``.

    Parameters
    ----------
    legal_chunks:
        Chunks from the internal legal corpus (ScoredChunk-shaped dicts).
    web_evidence:
        Evidence from web search (WebEvidence-shaped dicts).
    settings:
        Application settings object with INTERNAL_CORPUS_PREMIUM and
        WEB_CORPUS_PENALTY attributes.

    Returns
    -------
    list[dict]
        Up to 10 merged, deduplicated, authority-scored evidence dicts.
    """
    combined: list[dict] = []

    # --- Internal corpus chunks ------------------------------------------
    for chunk in legal_chunks:
        authority_score: float = float(chunk.get("authority_score") or 0.7)
        final_score: float = authority_score * settings.INTERNAL_CORPUS_PREMIUM
        content_hash: str = content_hash_for(chunk)

        item = {
            **chunk,
            "domain": "internal",
            "content_hash": content_hash,
            "final_score": final_score,
        }
        combined.append(item)

    # --- Web evidence -------------------------------------------------------
    for ev in web_evidence:
        base: float = float(ev.get("authority_score") or 0.0)
        src_type: str = ev.get("source_type", "")
        if src_type in _AUTHORITATIVE_WEB_TYPES:
            final_score = base
        else:
            final_score = base * settings.WEB_CORPUS_PENALTY

        item = {
            **ev,
            "domain": "web",
            "final_score": final_score,
        }
        combined.append(item)

    # --- Drop evidence that doesn't clear the minimum quality floor --------
    combined = [item for item in combined if item["final_score"] >= settings.EVIDENCE_MIN_SCORE]

    # --- Deduplicate by content_hash (keep highest final_score) ------------
    best: dict[str, dict] = {}
    for item in combined:
        h: str = item.get("content_hash", "")
        if not h:
            # No hash available — treat as unique, use object id as key
            h = str(id(item))
        existing = best.get(h)
        if existing is None or item["final_score"] > existing["final_score"]:
            best[h] = item

    # --- Sort and truncate --------------------------------------------------
    deduped = sorted(best.values(), key=lambda x: x["final_score"], reverse=True)[:10]

    if as_of_date:
        for item in deduped:
            match = find_superseded_statute(item.get("text", ""), as_of_date)
            if match:
                item["superseded_by"] = match[1]

    return deduped
