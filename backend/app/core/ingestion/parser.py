from __future__ import annotations
import logging
from typing import TypedDict
import pymupdf
import pymupdf4llm

logger = logging.getLogger(__name__)

CHUNK_SIZE = 512
CHUNK_OVERLAP = 64
_HEADING_PREFIX = "#"
_TEXT_SUFFIXES = (".txt", ".md")


class Chunk(TypedDict):
    text: str
    page: int
    source: str


def _new(text: str, source: str, page: int) -> Chunk:
    return {"text": text, "page": page, "source": source}


def _char_split(text: str, source: str, page: int) -> list[Chunk]:
    """Overflow fallback: slice an oversized section into overlapping windows."""
    chunks, start = [], 0
    while start < len(text):
        piece = text[start:start + CHUNK_SIZE].strip()
        if piece:
            chunks.append(_new(piece, source, page))
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _split_sections(markdown: str) -> list[str]:
    """Split markdown at heading boundaries so each section keeps its heading."""
    sections: list[str] = []
    current: list[str] = []
    for line in markdown.splitlines(keepends=True):
        if line.lstrip().startswith(_HEADING_PREFIX) and current:
            sections.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("".join(current))
    return sections


def _chunk_markdown(markdown: str, source: str, page: int) -> list[Chunk]:
    """Chunk on markdown structure; small sections stay whole (tables/headings
    survive intact), oversized ones fall back to overlapping character windows."""
    chunks: list[Chunk] = []
    for section in _split_sections(markdown):
        section = section.strip()
        if not section:
            continue
        if len(section) <= CHUNK_SIZE:
            chunks.append(_new(section, source, page))
        else:
            chunks.extend(_char_split(section, source, page))
    return chunks


def _parse_pdf(data: bytes, filename: str) -> list[Chunk]:
    doc = pymupdf.open(stream=data, filetype="pdf")
    chunks: list[Chunk] = []
    for page_index, page in enumerate(pymupdf4llm.to_markdown(doc, page_chunks=True)):
        chunks.extend(_chunk_markdown(page["text"], filename, page_index))
    return chunks


def parse_bytes(data: bytes, filename: str) -> list[Chunk]:
    if filename.lower().endswith(_TEXT_SUFFIXES):
        return _chunk_markdown(data.decode("utf-8", errors="replace"), filename, 0)
    try:
        return _parse_pdf(data, filename)
    except (pymupdf.FileDataError, ValueError, RuntimeError) as exc:
        logger.warning("PDF parse failed for %s, falling back to text: %s", filename, exc)
        return _chunk_markdown(data.decode("utf-8", errors="replace"), filename, 0)
