from __future__ import annotations
import re
from app.core.graph.state import CitationResult

# Matches a [N] marker as instructed by ANSWER_PROMPT — one or more digits in
# brackets, e.g. "[1]" or "[12]". Distinct from "verified" (claim-level
# groundedness): a chunk can be cited without being grounded (hallucinated
# citation) or grounded without ever being cited (retrieved but unused).
_CITATION_MARKER_RE = re.compile(r"\[(\d+)\]")


def derive_citations(verification: dict, evidence: list[dict], answer: str = "") -> list[CitationResult]:
    """Derive per-evidence-item citation verification from claim-level grounding.

    "Verified" means the verifier's ``supported_claims`` reference this evidence
    item's ``content_hash`` — i.e. at least one atomic claim in the answer is
    grounded in it. This replaces the old regex+substring quote matcher, which
    only worked when the LLM quoted evidence verbatim; paraphrased claims are
    now visible too, and every evidence item (not just quoted ones) gets a
    verdict.

    "Cited" is a separate, cheaper signal: whether the item's 1-based [N]
    marker literally appears in ``answer`` text, regardless of whether the
    verifier could ground it. This is what lets the frontend report a genuine
    "N retrieved, M cited" stat — evidence handed to the prompt but never
    referenced by the model is retrieved-only, not part of the answer.
    """
    claims_by_hash: dict[str, list[str]] = {}
    for claim in verification.get("supported_claims") or []:
        content_hash = claim.get("content_hash") if isinstance(claim, dict) else ""
        if not content_hash:
            continue
        text = claim.get("claim", "") if isinstance(claim, dict) else str(claim)
        claims_by_hash.setdefault(content_hash, []).append(text)

    cited_markers = {int(n) for n in _CITATION_MARKER_RE.findall(answer)}

    results: list[CitationResult] = []
    for i, item in enumerate(evidence, 1):
        content_hash = item.get("content_hash", "") or ""
        matched = claims_by_hash.get(content_hash, []) if content_hash else []
        results.append({
            "quote": "; ".join(matched),
            "verified": bool(matched),
            "cited": i in cited_markers,
            "source": item.get("source") or item.get("title") or "",
            "page": item.get("page") or 0,
            "content_hash": content_hash,
            "index": i,
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


def cited_indices(citations: list[dict]) -> set[int]:
    """1-based indices of citations whose [N] marker actually appears in the
    answer — the "cited" half of the retrieved-vs-cited distinction."""
    return {c.get("index") for c in citations if c.get("cited") and c.get("index")}
