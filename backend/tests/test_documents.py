"""Tests for GET /api/v1/documents/view (app.api.v1.documents).

Ingestion stores only a chunk's basename as its ``source`` field (see
app.core.ingestion.pipeline), so this endpoint resolves that basename back to
its real S3 {key, bucket} via a cached index built from list_keys_with_meta(),
then serves the raw PDF bytes.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.config.settings import settings
from app.core import valkey
from app.main import create_app


@pytest.fixture(autouse=True)
def _reset_valkey_state(monkeypatch):
    """Force every cache lookup to miss (no live Valkey needed) and reset the
    shared breaker before and after each test."""
    valkey.reset()
    monkeypatch.setattr(valkey, "get_client", lambda: None)
    yield
    valkey.reset()


@pytest.fixture(autouse=True)
def _isolated_document_cache_dir(tmp_path, monkeypatch):
    """Every test gets its own DOCUMENT_CACHE_DIR so cache state never leaks
    between tests or hits the real /tmp/juryai-document-cache."""
    monkeypatch.setattr(settings, "DOCUMENT_CACHE_DIR", str(tmp_path / "document-cache"))
    yield


def _fake_loader(entries: list[dict], downloads: dict[str, bytes]) -> MagicMock:
    loader = MagicMock()
    loader.list_keys_with_meta.return_value = entries
    loader.download.side_effect = lambda key, bucket=None: downloads.get(key)
    return loader


@pytest.mark.asyncio
async def test_list_documents_total_reflects_full_corpus_not_just_the_page():
    """total must count the whole (filtered) corpus, not the sliced page —
    otherwise a paginating caller (the composer's source picker) can never
    tell a second page exists, and silently truncates to the first `limit`
    documents."""
    app = create_app()
    entries = [
        {"key": f"Acts/Act {i:03d}.pdf", "size": 1, "etag": f"e{i}", "bucket": "bucket-a"}
        for i in range(5)
    ]
    loader = _fake_loader(entries=entries, downloads={})

    with patch("app.api.v1.documents.MultiS3Loader", return_value=loader):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/v1/documents", params={"limit": 2, "offset": 0})

    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 5  # full corpus, not len(this page) == 2
    assert len(data["documents"]) == 2


@pytest.mark.asyncio
async def test_list_document_folders_groups_by_bucket_and_prefix():
    """Folders must come straight from each object's key path, not a
    hardcoded taxonomy — nested prefixes and multiple buckets both need to
    show up as distinct groups with an accurate per-folder count."""
    app = create_app()
    entries = [
        {"key": "Acts/A.pdf", "size": 1, "etag": "e1", "bucket": "bucket-a"},
        {"key": "Acts/B.pdf", "size": 1, "etag": "e2", "bucket": "bucket-a"},
        {"key": "Notifications/2024/C.pdf", "size": 1, "etag": "e3", "bucket": "bucket-a"},
        {"key": "Acts/D.pdf", "size": 1, "etag": "e4", "bucket": "bucket-b"},
    ]
    loader = _fake_loader(entries=entries, downloads={})

    with patch("app.api.v1.documents.MultiS3Loader", return_value=loader):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/v1/documents/folders")

    assert r.status_code == 200
    folders = {(f["bucket"], f["folder"]): f["count"] for f in r.json()["folders"]}
    assert folders == {
        ("bucket-a", "Acts"): 2,
        ("bucket-a", "Notifications/2024"): 1,
        ("bucket-b", "Acts"): 1,
    }


@pytest.mark.asyncio
async def test_view_document_resolves_basename_and_returns_pdf_bytes():
    app = create_app()
    basename = "ADVOCATES' WELFARE FUND ACT, 2001.pdf"
    key = f"Acts/{basename}"
    loader = _fake_loader(
        entries=[{"key": key, "size": 10, "etag": "e1", "bucket": "bucket-a"}],
        downloads={key: b"%PDF-1.4 fake bytes"},
    )

    with patch("app.api.v1.documents.MultiS3Loader", return_value=loader):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/v1/documents/view", params={"source": basename})

    assert r.status_code == 200
    assert r.content == b"%PDF-1.4 fake bytes"
    assert r.headers["content-type"] == "application/pdf"
    assert basename in r.headers["content-disposition"]
    loader.download.assert_called_once_with(key, bucket="bucket-a")


@pytest.mark.asyncio
async def test_view_document_unmatched_basename_returns_404():
    app = create_app()
    loader = _fake_loader(
        entries=[{"key": "Acts/other.pdf", "size": 1, "etag": "e", "bucket": "bucket-a"}],
        downloads={},
    )

    with patch("app.api.v1.documents.MultiS3Loader", return_value=loader):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/v1/documents/view", params={"source": "missing.pdf"})

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_view_document_download_miss_returns_404():
    app = create_app()
    key = "Acts/found-but-gone.pdf"
    loader = _fake_loader(
        entries=[{"key": key, "size": 1, "etag": "e", "bucket": "bucket-a"}],
        downloads={},
    )

    with patch("app.api.v1.documents.MultiS3Loader", return_value=loader):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/v1/documents/view", params={"source": "found-but-gone.pdf"})

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_view_document_rejects_path_traversal_source():
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r1 = await c.get("/api/v1/documents/view", params={"source": "../etc/passwd"})
        r2 = await c.get("/api/v1/documents/view", params={"source": "folder/name.pdf"})

    assert r1.status_code == 400
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_view_document_cache_hit_skips_s3_entirely():
    app = create_app()
    basename = "cached-act.pdf"
    cached_bytes = b"%PDF-1.4 already cached"
    cache_path = Path(settings.DOCUMENT_CACHE_DIR) / basename
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(cached_bytes)

    loader = _fake_loader(entries=[], downloads={})

    with patch("app.api.v1.documents.MultiS3Loader", return_value=loader):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/v1/documents/view", params={"source": basename})

    assert r.status_code == 200
    assert r.content == cached_bytes
    assert r.headers["content-type"] == "application/pdf"
    loader.list_keys_with_meta.assert_not_called()
    loader.download.assert_not_called()


@pytest.mark.asyncio
async def test_view_document_cache_miss_writes_bytes_to_disk():
    app = create_app()
    basename = "ADVOCATES' WELFARE FUND ACT, 2001.pdf"
    key = f"Acts/{basename}"
    downloaded_bytes = b"%PDF-1.4 fresh download"
    loader = _fake_loader(
        entries=[{"key": key, "size": 10, "etag": "e1", "bucket": "bucket-a"}],
        downloads={key: downloaded_bytes},
    )

    with patch("app.api.v1.documents.MultiS3Loader", return_value=loader):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/v1/documents/view", params={"source": basename})

    assert r.status_code == 200
    assert r.content == downloaded_bytes

    cache_path = Path(settings.DOCUMENT_CACHE_DIR) / basename
    assert cache_path.exists()
    assert cache_path.read_bytes() == downloaded_bytes
