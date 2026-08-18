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
    """Parse PDF with pymupdf4llm, fallback to OCR if text extraction is poor."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    chunks: list[Chunk] = []

    # First pass: try standard markdown extraction
    for page_index, page in enumerate(pymupdf4llm.to_markdown(doc, page_chunks=True)):
        page_text = page["text"]
        # Check if page has meaningful text
        if len(page_text.strip()) >= 50:
            chunks.extend(_chunk_markdown(page_text, filename, page_index))
        else:
            # Page appears to be scanned/image-based — try OCR
            ocr_chunks = _parse_page_ocr(doc, filename, page_index)
            if ocr_chunks:
                chunks.extend(ocr_chunks)
                logger.info("OCR used for page %d of %s", page_index + 1, filename)
            else:
                # Fallback to whatever text we got
                chunks.extend(_chunk_markdown(page_text, filename, page_index))

    return chunks


def _parse_page_ocr(doc: pymupdf.Document, filename: str, page_index: int) -> list[Chunk]:
    """OCR a single page using RapidOCR (ONNX Runtime, CPU-only)."""
    try:
        from rapidocr_onnxruntime import RapidOCR
        from app.config.settings import settings
    except ImportError:
        logger.debug("RapidOCR not available, skipping OCR")
        return []

    if not settings.OCR_ENABLED:
        return []

    ocr = RapidOCR()
    try:
        # Render page to image at configured DPI
        page = doc[page_index]
        pix = page.get_pixmap(dpi=settings.OCR_DPI)
        img_bytes = pix.tobytes("png")

        # Run OCR
        result, _ = ocr(img_bytes)
        if not result:
            return []

        # Sort by reading order (top-to-bottom, left-to-right)
        result.sort(key=lambda x: (x[0][0][1], x[0][0][0]))

        # Combine into text
        text = "\n".join([line[1] for line in result if line[1].strip()])

        if len(text.strip()) < settings.OCR_MIN_CHARS_PER_PAGE:
            return []

        return _chunk_markdown(text, filename, page_index)

    except Exception as exc:
        logger.warning("OCR failed for page %d of %s: %s", page_index + 1, filename, exc)
        return []


def parse_bytes(data: bytes, filename: str) -> list[Chunk]:
    if filename.lower().endswith(_TEXT_SUFFIXES):
        return _chunk_markdown(data.decode("utf-8", errors="replace"), filename, 0)
    try:
        return _parse_pdf(data, filename)
    except (pymupdf.FileDataError, ValueError, RuntimeError) as exc:
        logger.warning("PDF parse failed for %s, falling back to text: %s", filename, exc)
        return _chunk_markdown(data.decode("utf-8", errors="replace"), filename, 0)