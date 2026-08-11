import io
import fitz
from unittest.mock import MagicMock, patch
from app.core.ingestion.s3_loader import S3Loader
from app.core.ingestion.parser import parse_bytes


def _make_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_s3_loader_local_fallback(tmp_path):
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
