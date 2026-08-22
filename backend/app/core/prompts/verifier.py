from __future__ import annotations

VERIFY_PROMPT = """You are an independent legal verification layer. You did NOT write \
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
