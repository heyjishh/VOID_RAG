"""Verifier gate — block ungrounded answers, regenerate once.

The meta-verifier (``app.core.graph.verifier``) scores an answer's groundedness
against the retrieved evidence. Today an "unsupported" verdict only decorates the
UI with a badge. This gate acts on it, LexLegis-style:

    1. Verify the first answer.
    2. If it fails the gate (score < GROUNDEDNESS_MIN), regenerate ONCE with a
       stricter, evidence-only prompt.
    3. Keep whichever attempt is better grounded.
    4. If the best attempt STILL fails, block release — return a safe refusal
       rather than ship an unsupported legal statement.

Best-effort: verification failures fall back to "unsupported" (see verifier), so
the gate degrades to blocking rather than silently passing bad answers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from langchain_core.messages import HumanMessage

from app.config.settings import settings
from app.core.graph.verifier import verify_answer
from app.core.llm.provider import get_llm

logger = logging.getLogger("juryai.gate")

# Stricter retry prompt: same evidence, but the model is told the first attempt
# failed grounding and must quote or decline.
_REGEN_PROMPT = """Your previous answer was flagged as NOT grounded in the provided \
legal sources. Rewrite it using ONLY the evidence below.

Rules:
- Every claim MUST be directly supported by a quote from the evidence.
- Quote the supporting text in double-quotes and cite [Source: filename, Page N].
- If the evidence does not support an answer, say exactly: "The retrieved sources \
do not contain enough information to answer this."
- Do NOT use outside legal knowledge. Do NOT speculate.

Question: {question}

Evidence:
{evidence}

Grounded answer:"""


@dataclass
class GateResult:
    answer: str
    verification: dict
    blocked: bool
    regenerated: bool
    # Populated only when regeneration produced the answer actually released —
    # empty means "unchanged, caller should keep its own inference metadata".
    model_provider: str = ""
    model_name: str = ""


def _passes(verification: dict) -> bool:
    return float(verification.get("groundedness_score", 0.0)) >= settings.GROUNDEDNESS_MIN


async def _regenerate(question: str, evidence_text: str) -> tuple[str, str, str]:
    prompt = _REGEN_PROMPT.replace("{question}", question).replace("{evidence}", evidence_text)
    resp = await get_llm().ainvoke([HumanMessage(content=prompt)])
    meta = resp.response_metadata or {}
    return getattr(resp, "content", "") or "", meta.get("model_provider", ""), meta.get("model_name", "")


async def gate_answer(
    question: str,
    answer: str,
    evidence: list[dict],
    evidence_text: str,
    verification: dict,
) -> GateResult:
    """Apply the groundedness gate to an already-verified answer.

    ``verification`` is the verdict for ``answer`` (computed by the caller so the
    result can be reused). ``evidence_text`` is the rendered evidence block used
    for regeneration. Returns the best answer, its verdict, and gate flags.
    """
    if not settings.VERIFIER_GATE_ENABLED or _passes(verification):
        return GateResult(answer=answer, verification=verification, blocked=False, regenerated=False)

    # First attempt failed the gate — try one stricter regeneration.
    try:
        retry_answer, retry_provider, retry_model = await _regenerate(question, evidence_text)
    except Exception as exc:  # noqa: BLE001 — regeneration is best-effort
        logger.warning("gate regeneration failed: %s", exc)
        retry_answer, retry_provider, retry_model = "", "", ""

    model_provider, model_name = "", ""
    if retry_answer.strip():
        retry_verification = await verify_answer(retry_answer, evidence)
        # Keep whichever attempt is better grounded.
        if float(retry_verification.get("groundedness_score", 0.0)) > float(
            verification.get("groundedness_score", 0.0)
        ):
            answer, verification = retry_answer, retry_verification
            model_provider, model_name = retry_provider, retry_model
        regenerated = True
    else:
        regenerated = False

    if _passes(verification):
        return GateResult(
            answer=answer,
            verification=verification,
            blocked=False,
            regenerated=regenerated,
            model_provider=model_provider,
            model_name=model_name,
        )

    # Still ungrounded after the retry — block release.
    return GateResult(
        answer=settings.GATE_BLOCKED_MESSAGE,
        verification=verification,
        blocked=True,
        regenerated=regenerated,
    )
