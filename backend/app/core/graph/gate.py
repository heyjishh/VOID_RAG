"""Verifier gate — block ungrounded answers, auto-correct across bounded rounds.

The meta-verifier (``app.core.graph.verifier``) scores an answer's groundedness
against the retrieved evidence and names which specific claims are unsupported.
This gate acts on that, LexLegis-style — but iteratively, not just once:

    1. Verify the first answer.
    2. If it fails the gate (score < GROUNDEDNESS_MIN), for up to
       GATE_MAX_CORRECTION_ROUNDS rounds:
       a. Take the specific unsupported claims and run a targeted corpus
          search for each — not a blind retry with the same evidence.
       b. Regenerate with the enlarged evidence set (stricter, evidence-only
          prompt).
       c. Re-verify. Stop early if grounded, or if a round found no new
          evidence at all (looping further on the same inputs won't help).
    3. Keep whichever attempt across all rounds is best grounded.
    4. If the best attempt STILL fails, block release — return a safe refusal
       rather than ship an unsupported legal statement.

Best-effort: verification failures fall back to "unsupported" (see verifier), so
the gate degrades to blocking rather than silently passing bad answers.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable

from langchain_core.messages import HumanMessage

from app.config.settings import settings
from app.core.graph.evidence_merger import ensure_content_hashes
from app.core.graph.nodes import legal_retrieve_node
from app.core.graph.verifier import verify_answer, _build_evidence_text
from app.core.llm.provider import get_llm
from app.core.prompts.gate import REGEN_PROMPT

logger = logging.getLogger("juryai.gate")


@dataclass
class GateResult:
    answer: str
    verification: dict
    blocked: bool
    regenerated: bool
    rounds: int = 0
    # Populated only when regeneration produced the answer actually released —
    # empty means "unchanged, caller should keep its own inference metadata".
    model_provider: str = ""
    model_name: str = ""


def _passes(verification: dict) -> bool:
    return float(verification.get("groundedness_score", 0.0)) >= settings.GROUNDEDNESS_MIN


async def _regenerate(question: str, evidence_text: str) -> tuple[str, str, str]:
    prompt = REGEN_PROMPT.replace("{question}", question).replace("{evidence}", evidence_text)
    resp = await get_llm().ainvoke([HumanMessage(content=prompt)])
    meta = resp.response_metadata or {}
    return getattr(resp, "content", "") or "", meta.get("model_provider", ""), meta.get("model_name", "")


async def _search_for_claim(claim: str) -> list[dict]:
    """One targeted corpus search seeded with the unsupported claim's own
    text instead of the original question — the whole point of auto-correct
    is to go find evidence for the SPECIFIC thing that was missing, not to
    re-run the same broad search that already produced the gap."""
    try:
        state = {
            "question": claim, "on_step": lambda s: None,
            "source_filter": None, "as_of_date": None, "intent": "unknown",
        }
        result = await legal_retrieve_node(state)
        return result.get("legal_chunks", [])
    except Exception as exc:
        logger.warning("Correction search failed for claim %r: %s", claim, exc)
        return []


async def _find_new_evidence(unsupported_claims: list[str], seen_hashes: set[str]) -> list[dict]:
    targets = unsupported_claims[: settings.GATE_MAX_CLAIMS_PER_ROUND]
    if not targets:
        return []
    gathered = await asyncio.gather(*[_search_for_claim(c) for c in targets], return_exceptions=True)
    new_evidence: list[dict] = []
    for r in gathered:
        if isinstance(r, list):
            for item in ensure_content_hashes(r):
                h = item.get("content_hash")
                if h and h not in seen_hashes:
                    seen_hashes.add(h)
                    new_evidence.append(item)
    return new_evidence


async def gate_answer(
    question: str,
    answer: str,
    evidence: list[dict],
    evidence_text: str,
    verification: dict,
    on_round: Callable[[dict], None] | None = None,
) -> GateResult:
    """Apply the groundedness gate to an already-verified answer, correcting
    across up to ``settings.GATE_MAX_CORRECTION_ROUNDS`` rounds if it fails.

    ``verification`` is the verdict for ``answer`` (computed by the caller so the
    result can be reused). ``evidence_text`` is the rendered evidence block used
    for the first regeneration attempt. ``on_round``, if given, is called once
    per correction round with a small dict describing what happened — callers
    can surface this as an SSE event so the correction isn't a silent retry.
    Returns the best answer, its verdict, and gate flags.
    """
    if not settings.VERIFIER_GATE_ENABLED or _passes(verification):
        return GateResult(answer=answer, verification=verification, blocked=False, regenerated=False, rounds=0)

    best_answer, best_verification = answer, verification
    current_evidence = list(evidence)
    current_evidence_text = evidence_text
    seen_hashes = {e.get("content_hash") for e in current_evidence if e.get("content_hash")}
    regenerated = False
    model_provider, model_name = "", ""
    rounds_run = 0

    for round_num in range(1, settings.GATE_MAX_CORRECTION_ROUNDS + 1):
        unsupported = best_verification.get("unsupported_claims", [])
        new_evidence = await _find_new_evidence(unsupported, seen_hashes) if unsupported else []
        if new_evidence:
            current_evidence = current_evidence + new_evidence
            current_evidence_text = _build_evidence_text(current_evidence)
        elif round_num > 1:
            # No new evidence this round (and this isn't the first attempt) —
            # regenerating again with the same inputs would just repeat the
            # same failure, so stop looping rather than burn more rounds.
            break

        if on_round:
            on_round({
                "round": round_num,
                "detail": (
                    f"Round {round_num}: searching for support for "
                    f"{len(unsupported)} unsupported claim(s) — found {len(new_evidence)} new source(s)"
                    if unsupported else f"Round {round_num}: regenerating with existing evidence"
                ),
            })

        try:
            retry_answer, retry_provider, retry_model = await _regenerate(question, current_evidence_text)
        except Exception as exc:  # noqa: BLE001 — regeneration is best-effort
            logger.warning("gate regeneration failed (round %d): %s", round_num, exc)
            break

        rounds_run = round_num
        if not retry_answer.strip():
            continue
        regenerated = True

        retry_verification = await verify_answer(retry_answer, current_evidence)
        if float(retry_verification.get("groundedness_score", 0.0)) > float(
            best_verification.get("groundedness_score", 0.0)
        ):
            best_answer, best_verification = retry_answer, retry_verification
            model_provider, model_name = retry_provider, retry_model

        if _passes(best_verification):
            break

    blocked = not _passes(best_verification)
    return GateResult(
        answer=best_answer,
        verification=best_verification,
        blocked=blocked,
        regenerated=regenerated,
        rounds=rounds_run,
        model_provider=model_provider,
        model_name=model_name,
    )
