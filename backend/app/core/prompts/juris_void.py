from __future__ import annotations

JV_DRAFT_PROMPT = (
    "Convert the following legal analysis into a formal {document_type}.\n\n"
    "Original Question: {question}\n\n"
    "Analysis:\n{answer}\n\n"
    "Format as a professional legal document with proper headings, "
    "numbered paragraphs, and formal language. Preserve all citations. "
    "Return the document in Markdown."
)
