import io
import fitz
from unittest.mock import MagicMock, patch
from app.config.settings import settings
from app.core.ingestion.s3_loader import S3Loader
from app.core.ingestion.parser import parse_bytes


_HEADING_FONT = 24
_BODY_FONT = 11
_CELL_FONT = 10


def _make_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _draw_table(page, cells: list[list[str]], origin=(50, 140), cell=(120, 24)) -> None:
    """Draw a grid + cell text so pymupdf4llm detects a real table."""
    x0, y0 = origin
    cw, rh = cell
    rows, cols = len(cells), len(cells[0])
    for r in range(rows + 1):
        page.draw_line((x0, y0 + r * rh), (x0 + cols * cw, y0 + r * rh))
    for c in range(cols + 1):
        page.draw_line((x0 + c * cw, y0), (x0 + c * cw, y0 + rows * rh))
    for r in range(rows):
        for c in range(cols):
            page.insert_text((x0 + c * cw + 5, y0 + r * rh + 16), cells[r][c], fontsize=_CELL_FONT)


def _make_structured_pdf(heading: str, body: str, cells: list[list[str]]) -> bytes:
    """A single-page PDF with a large-font heading, body text, and a drawn table."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 60), heading, fontsize=_HEADING_FONT)
    page.insert_text((50, 100), body, fontsize=_BODY_FONT)
    _draw_table(page, cells)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_s3_loader_local_fallback(tmp_path, monkeypatch):
    # Isolate from a live S3_BUCKET_NAME in the local .env so the loader takes
    # the local-filesystem fallback path instead of hitting real S3.
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", None)
    monkeypatch.setattr(settings, "S3_BUCKET_NAMES", None)
    (tmp_path / "a.pdf").write_bytes(b"%PDF")
    loader = S3Loader(local_root=str(tmp_path))
    keys = loader.list_keys()
    assert "a.pdf" in keys


def test_s3_loader_download_local(tmp_path):
    (tmp_path / "doc.pdf").write_bytes(b"content")
    loader = S3Loader(local_root=str(tmp_path))
    assert loader.download("doc.pdf") == b"content"


def test_parse_pdf_returns_chunks():
    data = _make_pdf("Section 302 IPC defines murder and its punishment.")
    chunks = parse_bytes(data, "ipc.pdf")
    assert len(chunks) >= 1
    assert all("text" in c and "source" in c and "page" in c for c in chunks)
    assert chunks[0]["source"] == "ipc.pdf"
    assert "Section 302" in " ".join(c["text"] for c in chunks)


def test_parse_blank_pdf_returns_empty():
    doc = fitz.open()
    doc.new_page()
    buf = io.BytesIO()
    doc.save(buf)
    assert parse_bytes(buf.getvalue(), "blank.pdf") == []


def test_parse_txt_splits():
    text = "word " * 300
    chunks = parse_bytes(text.encode(), "doc.txt")
    assert len(chunks) >= 2


def test_parse_pdf_preserves_markdown_structure():
    """Headings (#) and table syntax (|) survive extraction into chunk text."""
    data = _make_structured_pdf(
        heading="Indian Penal Code",
        body="Section 302 defines the punishment for murder.",
        cells=[["Section", "Punishment"], ["302", "Life / Death"], ["304", "Imprisonment"]],
    )
    chunks = parse_bytes(data, "ipc.pdf")
    combined = "\n".join(c["text"] for c in chunks)
    assert "# Indian Penal Code" in combined
    assert "|Section|Punishment|" in combined
    assert "|---" in combined  # markdown table separator row
    assert "302" in combined and "Life / Death" in combined


def test_parse_pdf_structure_metadata_correct():
    """Every structured chunk carries the right source and 0-based page index."""
    data = _make_structured_pdf(
        heading="Contract Law",
        body="An offer must be accepted to form a binding agreement.",
        cells=[["Element", "Required"], ["Offer", "Yes"], ["Acceptance", "Yes"]],
    )
    chunks = parse_bytes(data, "contracts.pdf")
    assert chunks, "expected at least one chunk from a structured PDF"
    assert all(c["source"] == "contracts.pdf" for c in chunks)
    assert all(c["page"] == 0 for c in chunks)


def test_parse_pdf_page_metadata_increments_across_pages():
    """Chunks report the page they came from across a multi-page document."""
    doc = fitz.open()
    doc.new_page().insert_text((50, 60), "Volume One", fontsize=_HEADING_FONT)
    doc.new_page().insert_text((50, 60), "Volume Two", fontsize=_HEADING_FONT)
    buf = io.BytesIO()
    doc.save(buf)
    chunks = parse_bytes(buf.getvalue(), "multi.pdf")
    pages = {c["page"] for c in chunks}
    assert pages == {0, 1}
