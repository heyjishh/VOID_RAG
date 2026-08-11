from __future__ import annotations
from app.core.graph.state import CitationResult


def derive_citations(verification: dict, evidence: list[dict]) -> list[CitationResult]:
    """Derive per-evidence-item citation verification from claim-level grounding.

    "Verified" means the verifier's ``supported_claims`` reference this evidence
    item's ``content_hash`` — i.e. at least one atomic claim in the answer is
    grounded in it. This replaces the old regex+substring quote matcher, which
    only worked when the LLM quoted evidence verbatim; paraphrased claims are
    now visible too, and every evidence item (not just quoted ones) gets a
    verdict.
    """
    claims_by_hash: dict[str, list[str]] = {}
    for claim in verification.get("supported_claims") or []:
        content_hash = claim.get("content_hash") if isinstance(claim, dict) else ""
        if not content_hash:
            continue
        text = claim.get("claim", "") if isinstance(claim, dict) else str(claim)
        claims_by_hash.setdefault(content_hash, []).append(text)

    results: list[CitationResult] = []
    for item in evidence:
        content_hash = item.get("content_hash", "") or ""
        matched = claims_by_hash.get(content_hash, []) if content_hash else []
        results.append({
            "quote": "; ".join(matched),
            "verified": bool(matched),
            "source": item.get("source") or item.get("title") or "",
            "page": item.get("page") or 0,
            "content_hash": content_hash,
        })
    return results


def verified_content_hashes(citations: list[dict]) -> set[str]:
    """content_hash set for citations the verifier actually grounded — the one
    signal both chat paths use to flag a source/chunk as verified."""
    return {
        c.get("content_hash")
        for c in citations
        if c.get("verified") and c.get("content_hash")
    }
