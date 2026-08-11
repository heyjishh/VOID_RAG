"""Pure scoring functions for the JuryAI eval harness.

Kept dependency-free and side-effect-free so they can be unit-tested without the
retrieval/LLM stack. ``run_eval.py`` drives the live pipeline and feeds the
resulting records here.

An eval *record* is a dict shaped like::

    {
        "question": str,
        "answer": str,
        "verification": {"groundedness_score": float, "verdict": str, "blocked": bool, ...},
        "citations": [{"source": str, "verified": bool, ...}, ...],
        "source_chunks": [{"source": str, ...}, ...],
        "expected_sources": [str, ...],   # from the golden set (optional)
    }
"""
from __future__ import annotations

from typing import Any

# Verdicts that count as a hallucination risk (answer not grounded in evidence).
_UNGROUNDED_VERDICTS = {"unsupported"}


def is_hallucination(record: dict) -> bool:
    """True when the answer is ungrounded and was NOT blocked/refused.

    A blocked answer is a *safe refusal*, not a hallucination — the gate caught
    it. Only an ungrounded answer that still reached the user counts.
    """
    v = record.get("verification") or {}
    if v.get("blocked"):
        return False
    verdict = v.get("verdict", "unsupported")
    return verdict in _UNGROUNDED_VERDICTS


def has_verified_citation(record: dict) -> bool:
    return any(c.get("verified") for c in record.get("citations") or [])


def expected_source_recall(record: dict) -> float:
    """Fraction of expected sources that appear in retrieved chunks or citations.

    Returns 1.0 when the golden record lists no expected sources (nothing to miss).
    Matching is case-insensitive substring on the source filename.
    """
    expected = [s.lower() for s in record.get("expected_sources") or []]
    if not expected:
        return 1.0
    seen = {
        (c.get("source") or "").lower()
        for c in (record.get("citations") or []) + (record.get("source_chunks") or [])
        if c.get("source")
    }
    hits = sum(1 for e in expected if any(e in s for s in seen))
    return hits / len(expected)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate(records: list[dict]) -> dict[str, Any]:
    """Compute corpus-level eval metrics over a list of records."""
    n = len(records)
    if n == 0:
        return {
            "n": 0,
            "hallucination_rate": 0.0,
            "mean_groundedness": 0.0,
            "citation_coverage": 0.0,
            "refusal_rate": 0.0,
            "regeneration_rate": 0.0,
            "expected_source_recall": 0.0,
        }
    groundedness = [
        float((r.get("verification") or {}).get("groundedness_score", 0.0)) for r in records
    ]
    return {
        "n": n,
        "hallucination_rate": sum(is_hallucination(r) for r in records) / n,
        "mean_groundedness": _mean(groundedness),
        "citation_coverage": sum(has_verified_citation(r) for r in records) / n,
        "refusal_rate": sum(
            bool((r.get("verification") or {}).get("blocked")) for r in records
        ) / n,
        "regeneration_rate": sum(
            bool((r.get("verification") or {}).get("regenerated")) for r in records
        ) / n,
        "expected_source_recall": _mean([expected_source_recall(r) for r in records]),
    }


def format_report(metrics: dict[str, Any]) -> str:
    """Render aggregate metrics as a short markdown table."""
    pct = lambda x: f"{x * 100:.1f}%"  # noqa: E731
    rows = [
        ("Questions evaluated", str(metrics["n"])),
        ("Hallucination rate", pct(metrics["hallucination_rate"])),
        ("Mean groundedness", f"{metrics['mean_groundedness']:.3f}"),
        ("Citation coverage", pct(metrics["citation_coverage"])),
        ("Refusal (gate-blocked) rate", pct(metrics["refusal_rate"])),
        ("Regeneration rate", pct(metrics["regeneration_rate"])),
        ("Expected-source recall", pct(metrics["expected_source_recall"])),
    ]
    width = max(len(k) for k, _ in rows)
    lines = ["| Metric | Value |", "| --- | --- |"]
    lines += [f"| {k.ljust(width)} | {val} |" for k, val in rows]
    return "\n".join(lines)
