import io
import fitz
import pytest
from unittest.mock import MagicMock, patch
from app.config.settings import settings
from app.core.ingestion.s3_loader import S3Loader
from app.core.ingestion.parser import parse_bytes
from app.core.ingestion.pipeline import _AdaptiveLimiter, _CpuGovernor


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


@pytest.mark.asyncio
async def test_adaptive_limiter_grows_on_success():
    limiter = _AdaptiveLimiter(initial=2, minimum=2, maximum=8)
    await limiter.acquire()
    await limiter.release(ok=True)
    assert limiter.limit == 3
    await limiter.acquire()
    await limiter.release(ok=True)
    assert limiter.limit == 4


@pytest.mark.asyncio
async def test_adaptive_limiter_halves_on_failure_and_floors_at_minimum():
    limiter = _AdaptiveLimiter(initial=8, minimum=2, maximum=24)
    await limiter.acquire()
    await limiter.release(ok=False)
    assert limiter.limit == 4
    await limiter.acquire()
    await limiter.release(ok=False)
    assert limiter.limit == 2  # floored at minimum, not 1
    await limiter.acquire()
    await limiter.release(ok=False)
    assert limiter.limit == 2


@pytest.mark.asyncio
async def test_adaptive_limiter_caps_at_maximum():
    limiter = _AdaptiveLimiter(initial=8, minimum=2, maximum=8)
    await limiter.acquire()
    await limiter.release(ok=True)
    assert limiter.limit == 8  # already at ceiling, success doesn't overshoot


def test_cpu_governor_degrades_above_budget_and_floors_at_minimum():
    gov = _CpuGovernor(budget_percent=50.0, min_ceiling=2, max_ceiling=8, sample_interval=2.0)
    gov.ceiling = 8
    gov._step(90.0)
    assert gov.ceiling == 7
    for _ in range(10):
        gov._step(90.0)
    assert gov.ceiling == 2  # never drops below minimum — pipeline stays alive


def test_cpu_governor_recovers_when_load_drops():
    gov = _CpuGovernor(budget_percent=50.0, min_ceiling=2, max_ceiling=8, sample_interval=2.0)
    gov.ceiling = 2
    gov._step(10.0)
    assert gov.ceiling == 3


@pytest.mark.asyncio
async def test_limiter_is_clamped_by_governor_ceiling():
    gov = _CpuGovernor(budget_percent=50.0, min_ceiling=2, max_ceiling=8, sample_interval=2.0)
    gov.ceiling = 3
    limiter = _AdaptiveLimiter(initial=8, minimum=2, maximum=8, governor=gov)
    # AIMD's internal limit is 8, but the governor's CPU-budget ceiling (3) wins.
    assert limiter.limit == 3


@pytest.mark.asyncio
async def test_list_pdf_keys_times_out_without_hanging(monkeypatch):
    """A listing call that never returns (a stuck botocore call — DNS, a
    dead connection, a retry loop) must not hang the caller forever. This
    replaced a forked-subprocess design that, in practice, deadlocked on
    every call when forked from a live multi-threaded async server (a lock
    held by another thread at fork time is inherited "locked forever" in
    the child). asyncio.wait_for over a plain to_thread call has no such
    fork risk and still bounds the wait."""
    import threading
    from app.core.ingestion import pipeline

    release = threading.Event()

    def _hangs_forever(prefix_filter):
        release.wait()  # never set within the test — simulates a stuck call
        return []

    monkeypatch.setattr(pipeline, "_list_pdf_keys", _hangs_forever)

    with pytest.raises(TimeoutError):
        await pipeline._list_pdf_keys_with_timeout("", timeout=0.05)

    release.set()  # let the orphaned thread-pool worker finish so it doesn't leak


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
