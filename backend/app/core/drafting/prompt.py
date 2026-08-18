"""Prompt construction for the Draft feature.

Assembles one LLM prompt from the user's brief plus whatever optional context
was supplied: a document-type clause, a house-style exemplar, an input
document, and/or research chunks from the shared corpus. Each clause is
independently omittable so a brief-only request still degrades to the
original v1 prompt.
"""
from __future__ import annotations

_BASE_PROMPT = """You are a precise legal drafting assistant. Write a complete, ready-to-use \
legal document in Markdown based on the brief below.

Brief:
{brief}
{document_type_clause}{house_style_clause}{input_document_clause}{research_clause}
Use clear numbered clauses/paragraphs appropriate to the document type and professional legal \
drafting language. Output only the document itself — no commentary, no preamble like "Here is \
the document"."""


def _document_type_clause(document_type: str | None) -> str:
    if not document_type:
        return ""
    return f"\nDocument type: {document_type}\n"


def _house_style_clause(exemplar_text: str | None) -> str:
    if not exemplar_text:
        return ""
    return f"\nMatch the drafting style, tone, and formatting of this house-style example:\n{exemplar_text}\n"


def _input_document_clause(input_text: str | None) -> str:
    if not input_text:
        return ""
    return f"\nIncorporate and build on this input document:\n{input_text}\n"


def _research_clause(chunks: list[dict]) -> str:
    if not chunks:
        return ""
    ctx = "\n\n".join(f"[{i}] {c['source']} p.{c['page']}\n{c['text']}" for i, c in enumerate(chunks, 1))
    return f"\nRelevant research context (cite as [N] where you rely on it):\n{ctx}\n"


def build_draft_prompt(
    *,
    brief: str,
    document_type: str | None = None,
    house_style_text: str | None = None,
    input_document_text: str | None = None,
    research_chunks: list[dict] | None = None,
) -> str:
    return _BASE_PROMPT.format(
        brief=brief,
        document_type_clause=_document_type_clause(document_type),
        house_style_clause=_house_style_clause(house_style_text),
        input_document_clause=_input_document_clause(input_document_text),
        research_clause=_research_clause(research_chunks or []),
    )
