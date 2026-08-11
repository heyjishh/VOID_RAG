from __future__ import annotations
import re

# Legal domain vocabulary — triggers "legal" intent
_LEGAL_TERMS = frozenset({
    "ipc", "crpc", "section", "act", "statute", "provision", "article",
    "constitution", "amendment", "court", "judge", "justice", "verdict",
    "plaintiff", "defendant", "petition", "writ", "bail", "cognizable",
    "offence", "offense", "punishment", "imprisonment", "fine", "acquittal",
    "conviction", "appeal", "tribunal", "arbitration", "contract", "tort",
    "negligence", "liability", "damages", "injunction", "decree", "affidavit",
    "witness", "evidence", "precedent", "ratio", "obiter", "hearing",
    "jurisdiction", "bench", "suo motu", "habeas corpus", "mandamus", "certiorari",
    "advocate", "barrister", "solicitor", "counsel", "legal", "law", "laws",
    "rights", "duty", "obligation", "enactment", "order", "judgment",
})

# Terms that suggest current events / web search
_WEB_TERMS = frozenset({
    "today", "yesterday", "latest", "recent", "news", "current", "now",
    "breaking", "2024", "2025", "2026", "happened", "update", "announced",
})


def classify_intent(question: str) -> str:
    """Classify query intent using keyword matching. Runs in <1ms. No LLM call."""
    tokens = set(re.findall(r"\b\w+\b", question.lower()))
    has_legal = bool(tokens & _LEGAL_TERMS)
    has_web = bool(tokens & _WEB_TERMS)
    if has_legal and has_web:
        return "both"
    if has_legal:
        return "legal"
    return "web"
