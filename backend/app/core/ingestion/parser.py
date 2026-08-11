from __future__ import annotations
from typing import TypedDict
import fitz

CHUNK_SIZE = 512
CHUNK_OVERLAP = 64


class Chunk(TypedDict):
    text: str
    page: int
    source: str


def _split(text: str, source: str, page: int) -> list[Chunk]:
    chunks, start = [], 0
    while start < len(text):
        piece = text[start:start + CHUNK_SIZE].strip()
        if piece:
            chunks.append({"text": piece, "page": page, "source": source})
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def parse_bytes(data: bytes, filename: str) -> list[Chunk]:
    if filename.lower().endswith((".txt", ".md")):
        return _split(data.decode("utf-8", errors="replace"), filename, 0)
    try:
        doc = fitz.open(stream=data, filetype="pdf")
        chunks = []
        for i, page in enumerate(doc):
            text = page.get_text().strip()
            if text:
                chunks.extend(_split(text, filename, i))
        return chunks
    except Exception:
        return _split(data.decode("utf-8", errors="replace"), filename, 0)
