from __future__ import annotations

CLAIM_EXTRACTION_PROMPT = """You are a legal fact-checker. Decompose the following legal answer into atomic, verifiable claims.

Each claim should be:
1. A single, specific factual assertion (not compound)
2. Independently verifiable against legal sources
3. Include specific legal references (sections, articles, case names) when present

Return ONLY a JSON array of claims. Each claim must have:
- \"text\": the exact claim text from the answer
- \"type\": one of [statutory, case_law, procedural, definitional, factual, comparative]
- \"entities\": list of legal entities mentioned (sections, articles, acts, case names)

Example:
Answer: \"Section 302 IPC provides death penalty for murder. In Bachan Singh v. State of Punjab, the Supreme Court held death penalty is constitutional only in rarest of rare cases.\"
Claims: [
  {{\"text\": \"Section 302 IPC provides death penalty for murder\", \"type\": \"statutory\", \"entities\": [\"Section 302\", \"IPC\"]}},
  {{\"text\": \"In Bachan Singh v. State of Punjab, the Supreme Court held death penalty is constitutional only in rarest of rare cases\", \"type\": \"case_law\", \"entities\": [\"Bachan Singh v. State of Punjab\", \"Supreme Court\"]}}
]

Answer: {answer}

Claims:"""


CLAIM_VERIFICATION_PROMPT = """You are a legal fact-checker. Verify the following claim against the provided evidence.

CLAIM: {claim}
CLAIM TYPE: {claim_type}

EVIDENCE:
{evidence}

For each piece of evidence, determine if it SUPPORTS, REFUTES, or is NEUTRAL to the claim.
Consider:
- Exact textual match for statutory provisions
- Case name, court, and holding match for precedents
- Procedural accuracy for process claims
- Definitional accuracy for legal terms

Return ONLY a JSON object:
{{
  "verdict": "supported|partially_supported|refuted|insufficient_evidence|conflicting_evidence",
  "confidence": 0.0-1.0,
  "supporting_evidence": ["exact quote from evidence that supports"],
  "refuting_evidence": ["exact quote from evidence that refutes"],
  "explanation": "Brief reasoning for verdict",
  "matched_citation": {{"raw_text": "...", "citation_type": "...", "normalized": "..."}} or null
}}"""


GROUNDEDNESS_PROMPT = """You are a legal fact-checker. Assess the overall groundedness of this legal answer based on claim-level verifications.

ANSWER: {answer}

CLAIM VERIFICATIONS:
{verifications}

Compute:
1. Groundedness score (0.0-1.0): proportion of claims supported by evidence
2. Overall verdict: supported|partially_supported|refuted|insufficient_evidence|conflicting_evidence
3. Summary: 2-3 sentence summary of verification outcome
4. List of unsupported claims

Return ONLY a JSON object:
{{
  "groundedness_score": 0.0-1.0,
  "overall_verdict": "supported|partially_supported|refuted|insufficient_evidence|conflicting_evidence",
  "summary": "...",
  "unsupported_claims": ["claim text 1", "claim text 2"]
}}"""
