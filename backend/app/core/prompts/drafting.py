from __future__ import annotations

_DOCUMENT_STRUCTURE = {
    "Plaint": (
        "Structure: Title/Court header → Parties (with full descriptions) → Jurisdiction clause → "
        "Chronological Facts (numbered paras, each covering one material fact with dates, amounts, "
        "and document references) → Cause of Action (with limitation analysis) → Legal Grounds "
        "(each ground as a separate section citing specific statutory provisions, sections, and "
        "case law) → Reliefs Sought (specific, measurable) → Interim Relief application if "
        "applicable → Verification → Vakalatnama reference."
    ),
    "Written statement/Counter": (
        "Structure: Title/Court header → Parties → Preliminary Objections (jurisdiction, "
        "limitation, maintainability, non-joinder/misjoinder — each as a separate numbered "
        "section with statutory basis) → Para-wise Reply to Plaint (mirror every paragraph of "
        "the plaint with Admitted/Denied/Not admitted and detailed counter-narrative for each) → "
        "Additional Facts and Grounds → Counter-claim if applicable → Prayer."
    ),
    "Petition (writ/SLP/review)": (
        "Structure: Title/Court header with petition type and Article/provision invoked → "
        "Parties (with locus standi justification) → Statement of Facts (detailed chronology "
        "with dates and documents) → Questions of Law → Grounds (each ground as a separate "
        "section with constitutional/statutory provisions and supporting case law) → Comparable "
        "precedent analysis → Interim relief prayer → Main prayers → Verification."
    ),
    "Written submissions": (
        "Structure: Title/Court header → Brief Facts → Issues for Determination → "
        "Submissions on each issue (separate detailed section per issue with statutory "
        "provisions, case law analysis distinguishing facts, and application to present case) → "
        "Distinguishing opposing precedents → Summary of submissions → Prayer."
    ),
    "Application (IA/bail/misc.)": (
        "Structure: Title/Court header with application type → Parties → Facts giving rise to "
        "the application (chronological, detailed) → Grounds (each with statutory basis and "
        "case law — for bail: nature of offence, evidence strength, flight risk, custody period, "
        "surety details; for IA: urgency, irreparable harm, balance of convenience, prima facie "
        "case) → Prayer with specific conditions/terms proposed."
    ),
    "Opinion/memo": (
        "Structure: Title with subject matter → Executive Summary (2-3 paras) → Facts as "
        "Understood → Issues Identified → Detailed Analysis per issue (statutory framework, "
        "judicial interpretation with case citations, application to facts, risk assessment "
        "with probability) → Alternative Strategies/Options with pros and cons → "
        "Recommendation → Caveats and Limitations → Annexures list."
    ),
    "Agreement": (
        "Structure: Title → Date and Place → Recitals/Whereas clauses (background and purpose) → "
        "Definitions (every defined term) → Operative clauses: Scope/Obligations of each party → "
        "Consideration/Payment terms → Representations and Warranties → Covenants → "
        "Conditions Precedent → Term and Termination → Indemnification → Limitation of Liability → "
        "Confidentiality → Dispute Resolution (arbitration/mediation/jurisdiction) → "
        "Force Majeure → Miscellaneous (amendment, waiver, severability, entire agreement, "
        "notices, assignment, governing law) → Schedules/Annexures → Execution block."
    ),
    "Notice/letter": (
        "Structure: Header (sender details, date, reference no.) → Addressee details → "
        "Subject line → Salutation → Background/Context paras → Statement of grievance/claim "
        "with factual chronology → Legal basis (specific statutory provisions, contractual "
        "clauses, or rights invoked) → Demand/Relief sought with specific timeline → "
        "Consequences of non-compliance (legal remedies available) → "
        "Without prejudice reservation → Closing."
    ),
    "Reply notice": (
        "Structure: Header → Reference to original notice (date, subject) → Denial/Admission "
        "of allegations para-by-para → Counter-narrative of facts → Legal defences with "
        "statutory basis → Counterclaim if applicable → Demand → Reservation of rights → Closing."
    ),
    "Affidavit": (
        "Structure: Title/Court header → Deponent identification (name, age, occupation, "
        "address) → 'I solemnly affirm and state as follows' → Numbered paragraphs of facts "
        "(each para covering one distinct fact with supporting documents referenced as "
        "Annexure-A/B/C) → Verification clause with place and date → Deponent signature block → "
        "Notary/Oath Commissioner block."
    ),
    "Order/Judgment": (
        "Structure: Court header → Case details (number, parties, dates) → Appearances → "
        "Brief Facts and Procedural History → Issues framed → Discussion and Analysis per issue "
        "(evidence evaluation, statutory interpretation, case law application) → Findings → "
        "Order/Decree with specific directions, timelines, and costs."
    ),
}

BASE_PROMPT = """You are an expert legal drafting assistant producing comprehensive, court-ready \
legal documents. Your output must be a COMPLETE, DETAILED, PRODUCTION-READY document in Markdown \
that a lawyer can file or send with minimal editing.

CRITICAL LENGTH AND DETAIL REQUIREMENTS:
- Produce a THOROUGH document covering every legally relevant aspect
- Every factual assertion must be detailed with dates, parties, amounts, and document references
- Every legal ground must cite specific statutory provisions (section numbers, act names, years) \
and relevant case law (case name, citation, court, year, and the principle established)
- Each section must be fully developed — no placeholders, no "[insert here]", no abbreviated clauses
- Include all standard clauses, boilerplate, and formalities expected in this document type
- When the brief mentions a legal issue, analyze it from EVERY applicable angle — statutory \
provisions, judicial precedents (at least 2-3 per major point), constitutional provisions if \
relevant, and procedural requirements
- For agreements: include comprehensive definitions, detailed obligations, all protective clauses
- For court filings: include full cause of action, detailed grounds, complete prayer clause
- The document MUST be exhaustive and substantive — 40 to 50 pages is the target length for \
a properly detailed legal instrument. Expand every section fully: elaborate each ground with \
multiple precedents, develop every factual paragraph with full particulars, include all \
procedural and substantive requirements, and never truncate or summarize where detail is needed
- If the document type calls for grounds/issues, dedicate 2-4 pages per major ground with \
statutory analysis, case law discussion (ratio decidendi, facts distinguished), and application
- Include all relevant annexure references, exhibit lists, and supporting document descriptions

Brief:
{brief}
{document_type_clause}{house_style_clause}{input_document_clause}{research_clause}
{structure_clause}
Output the complete document in Markdown with proper numbering and hierarchy. Output ONLY the \
document — no commentary, no preamble, no "Here is the document". Every section must be fully \
written out, never summarized or abbreviated."""


def _document_type_clause(document_type: str | None) -> str:
    if not document_type:
        return ""
    return f"\nDocument type: {document_type}\n"


def _structure_clause(document_type: str | None) -> str:
    if not document_type:
        return ""
    structure = _DOCUMENT_STRUCTURE.get(document_type)
    if not structure:
        return ""
    return f"\nExpected document structure and sections:\n{structure}\n"


def _house_style_clause(exemplar_text: str | None) -> str:
    if not exemplar_text:
        return ""
    return f"\nMatch the drafting style, tone, and formatting of this house-style example:\n{exemplar_text}\n"


def _input_document_clause(input_text: str | None) -> str:
    if not input_text:
        return ""
    return f"\nIncorporate and build on this input document:\n{input_text}\n"


def _format_chunk(i: int, c: dict) -> str:
    if c.get("domain") == "web":
        return f"[{i}] {c['source']} ({c.get('url', '')})\n{c['text']}"
    return f"[{i}] {c['source']} p.{c['page']}\n{c['text']}"


def _research_clause(chunks: list[dict]) -> str:
    if not chunks:
        return ""
    ctx = "\n\n".join(_format_chunk(i, c) for i, c in enumerate(chunks, 1))
    return f"\nRelevant research context (cite as [N] where you rely on it):\n{ctx}\n"


def build_draft_prompt(
    *,
    brief: str,
    document_type: str | None = None,
    house_style_text: str | None = None,
    input_document_text: str | None = None,
    research_chunks: list[dict] | None = None,
) -> str:
    return BASE_PROMPT.format(
        brief=brief,
        document_type_clause=_document_type_clause(document_type),
        house_style_clause=_house_style_clause(house_style_text),
        input_document_clause=_input_document_clause(input_document_text),
        research_clause=_research_clause(research_chunks or []),
        structure_clause=_structure_clause(document_type),
    )
