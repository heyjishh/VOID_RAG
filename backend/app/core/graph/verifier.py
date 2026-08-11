from __future__ import annotations
import json
from langchain_core.messages import HumanMessage
from app.core.llm.provider import get_llm


_VERIFY_PROMPT = """You are an independent legal verification layer. You did NOT write \
the answer below. Your job is to audit it against the retrieved legal EVIDENCE and report \
how well-grounded it is.

Instructions:
1. Decompose the ANSWER into atomic factual claims (each a single, self-contained assertion).
2. For EACH claim, decide whether it is SUPPORTED by the provided EVIDENCE. A claim is \
supported only if the evidence directly substantiates it. General legal knowledge that is \
NOT in the evidence does NOT count as supported.
3. Each evidence block below is labeled with an id, e.g. "[source p.N | id:abcd1234]". For \
every SUPPORTED claim, record the id of the evidence block that grounds it as content_hash. \
If a claim is grounded in more than one block, pick the single strongest match. Unsupported \
claims have no id, by definition.
4. Compute a groundedness_score between 0.0 and 1.0 = (supported claims) / (total claims).
5. Choose a verdict: "grounded" (>=0.8), "partially_grounded" (>=0.5), or "unsupported" (<0.5).
6. Write a short one-sentence summary explaining the verdict.

Return STRICT JSON with EXACTLY these keys and nothing else:
{
  "groundedness_score": <float 0..1>,
  "verdict": "grounded" | "partially_grounded" | "unsupported",
  "supported_claims": [{"claim": <string>, "content_hash": <string id from an evidence block>}, ...],
  "unsupported_claims": [<string>, ...],
  "summary": "<one sentence>"
}

Output ONLY the JSON object. Do not wrap it in markdown, do not add commentary.

EVIDENCE:
{evidence}

ANSWER:
{answer}

JSON:"""


_FALLBACK: dict = {
    "groundedness_score": 0.0,
    "verdict": "unsupported",
    "supported_claims": [],
    "unsupported_claims": [],
    "summary": "Verification unavailable.",
}


def _verdict_from_score(score: float) -> str:
    if score >= 0.8:
        return "grounded"
    if score >= 0.5:
        return "partially_grounded"
    return "unsupported"


def _build_evidence_text(evidence: list[dict]) -> str:
    """Render evidence for a prompt. For merged evidence, prefer internal-domain items.

    Public reuse: the verifier gate renders the same evidence block for its
    regeneration prompt (see ``app.core.graph.gate``).
    """
    items = [e for e in evidence if e.get("domain") == "internal"]
    if not items:
        # Not merged evidence (no domain tags) — use everything.
        items = list(evidence)
    parts: list[str] = []
    for e in items:
        text = e.get("text") or e.get("content") or ""
        if not text:
            continue
        source = e.get("source") or e.get("title") or "unknown"
        page = e.get("page")
        content_hash = e.get("content_hash") or ""
        header = f"[{source} p.{page}" if page is not None else f"[{source}"
        if content_hash:
            header += f" | id:{content_hash}"
        header += "]"
        parts.append(f"{header}\n{text}")
    return "\n\n".join(parts) or "(none)"


def _normalize_supported_claims(raw_claims) -> list[dict]:
    """Coerce supported_claims entries into {"claim": str, "content_hash": str}.

    Tolerates a model that ignores the id instruction and emits bare strings
    (content_hash falls back to "") so a formatting slip degrades gracefully
    instead of raising.
    """
    normalized: list[dict] = []
    for c in raw_claims or []:
        if isinstance(c, dict):
            claim = str(c.get("claim", ""))
            content_hash = str(c.get("content_hash") or "")
        else:
            claim = str(c)
            content_hash = ""
        if claim:
            normalized.append({"claim": claim, "content_hash": content_hash})
    return normalized


def _parse_verdict(raw: str) -> dict:
    """Robustly parse the LLM output into the verification dict."""
    text = (raw or "").strip()
    # Strip markdown code fences.
    if text.startswith("```"):
        text = text.strip("`")
        # Drop an optional leading language hint like "json\n".
        if "\n" in text:
            first, rest = text.split("\n", 1)
            if first.strip().lower() in ("json", ""):
                text = rest
    # Isolate the JSON object: first "{" to last "}".
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found in verifier output")
    data = json.loads(text[start : end + 1])

    supported = _normalize_supported_claims(data.get("supported_claims"))
    unsupported = [str(c) for c in (data.get("unsupported_claims") or [])]

    score = data.get("groundedness_score")
    try:
        score = float(score)
    except (TypeError, ValueError):
        total = len(supported) + len(unsupported)
        score = (len(supported) / total) if total else 0.0
    score = max(0.0, min(1.0, score))

    verdict = data.get("verdict")
    if verdict not in ("grounded", "partially_grounded", "unsupported"):
        verdict = _verdict_from_score(score)

    summary = str(data.get("summary") or "")

    return {
        "groundedness_score": score,
        "verdict": verdict,
        "supported_claims": supported,
        "unsupported_claims": unsupported,
        "summary": summary,
    }


async def verify_answer(answer: str, evidence: list[dict]) -> dict:
    """Independently verify an answer's groundedness against retrieved legal evidence.

    Returns a dict with keys: groundedness_score, verdict, supported_claims,
    unsupported_claims, summary. On any error (or empty inputs) returns a safe
    fallback without raising.
    """
    if not answer or not answer.strip() or not evidence:
        return dict(_FALLBACK)

    evidence_text = _build_evidence_text(evidence)
    prompt = (
        _VERIFY_PROMPT
        .replace("{evidence}", evidence_text)
        .replace("{answer}", answer)
    )

    try:
        resp = await get_llm().ainvoke([HumanMessage(content=prompt)])
        return _parse_verdict(getattr(resp, "content", "") or "")
    except Exception:  # noqa: BLE001 — robust fallback: never propagate verifier failures
        return dict(_FALLBACK)
