from __future__ import annotations

REGEN_PROMPT = """Your previous answer was flagged as NOT grounded in the provided \
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
