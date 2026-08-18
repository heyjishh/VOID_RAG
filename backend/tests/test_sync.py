import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_manifest_mark_and_list(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    with patch("app.core.ingestion.manifest.MANIFEST_PATH", manifest_path):
        from app.core.ingestion.manifest import Manifest
        m = Manifest()
        assert m.list_ingested() == set()
        m.mark_ingested("Acts/ipc.pdf", size=12345, etag="abc123")
        assert "Acts/ipc.pdf" in m.list_ingested()
        # reload from disk — must persist
        m2 = Manifest()
        assert "Acts/ipc.pdf" in m2.list_ingested()


def test_manifest_remove(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    with patch("app.core.ingestion.manifest.MANIFEST_PATH", manifest_path):
        from app.core.ingestion.manifest import Manifest
        m = Manifest()
        m.mark_ingested("Acts/x.pdf", size=1, etag="e")
        m.remove("Acts/x.pdf")
        assert "Acts/x.pdf" not in m.list_ingested()


def test_sync_only_skips_ingested_keys(tmp_path, monkeypatch):
    manifest_path = tmp_path / "manifest.json"
    with patch("app.core.ingestion.manifest.MANIFEST_PATH", manifest_path):
        from app.core.ingestion.manifest import Manifest
        m = Manifest()
        m.mark_ingested("Acts/already.pdf", size=100, etag="e1")

        import asyncio
        from app.core.ingestion import pipeline
        # Isolate the last-sync summary file too — without this the test
        # writes to the real backend/.last_sync.json on every run, which is
        # exactly what silently overwrote real ingestion history and made a
        # completed sync look like it "started from 0" on the next run.
        monkeypatch.setattr(pipeline, "_LAST_SYNC_PATH", tmp_path / "last_sync.json")

        mock_loader = MagicMock()
        mock_loader.list_keys_with_meta.return_value = [
            {"key": "Acts/already.pdf", "size": 100, "etag": "e1"},
            {"key": "Acts/new.pdf",     "size": 200, "etag": "e2"},
        ]
        mock_loader.download.return_value = b"%PDF-fake"

        with patch("app.core.ingestion.pipeline.MultiS3Loader", return_value=mock_loader), \
             patch("app.core.ingestion.pipeline.QdrantStore"), \
             patch("app.core.ingestion.pipeline.QuickwitStore"), \
             patch("app.core.ingestion.pipeline.parse_bytes", return_value=[
                 {"text": "test", "source": "new.pdf", "page": 0}
             ]):
            result = asyncio.run(pipeline.run_ingestion_pipeline(prefix_filter="", sync_only=True))
        # only "new.pdf" processed; "already.pdf" skipped
        assert result["ingested"] == 1
        assert result["skipped"] == 1

        # Checkpointed as it completed, not only in a final batch write at the
        # end of the whole run — reload from disk to prove it's actually
        # persisted, the way it would need to be to survive a kill mid-run.
        m3 = Manifest()
        assert "Acts/new.pdf" in m3.list_ingested()


def test_get_sync_status_caches_s3_listing_within_ttl(tmp_path, monkeypatch):
    """Repeated status polls within the TTL must reuse the cached S3 listing —
    this is the fix for the pipeline hammering S3 on every frontend poll."""
    manifest_path = tmp_path / "manifest.json"
    with patch("app.core.ingestion.manifest.MANIFEST_PATH", manifest_path):
        import asyncio
        from app.core.ingestion import pipeline
        from app.config.settings import settings

        pipeline._status_snapshot = None
        pipeline._status_snapshot_at = 0.0
        monkeypatch.setattr(settings, "INGEST_STATUS_CACHE_TTL_SECONDS", 60.0)

        mock_loader = MagicMock()
        mock_loader.list_keys_with_meta.return_value = [
            {"key": "Acts/a.pdf", "size": 1, "etag": "e"},
        ]
        with patch("app.core.ingestion.pipeline.MultiS3Loader", return_value=mock_loader):
            asyncio.run(pipeline.get_sync_status())
            asyncio.run(pipeline.get_sync_status())

        assert mock_loader.list_keys_with_meta.call_count == 1


def test_listing_timeout_records_error_in_last_sync(tmp_path, monkeypatch):
    """A listing that times out must be distinguishable from a listing that
    genuinely found zero pending keys — both used to look identical (empty
    result, no error), leaving 'Last Sync' silent about why a run stopped."""
    manifest_path = tmp_path / "manifest.json"
    last_sync_path = tmp_path / "last_sync.json"
    with patch("app.core.ingestion.manifest.MANIFEST_PATH", manifest_path):
        import asyncio
        from app.core.ingestion import pipeline

        monkeypatch.setattr(pipeline, "_LAST_SYNC_PATH", last_sync_path)

        with patch(
            "app.core.ingestion.pipeline._list_pdf_keys_with_timeout",
            side_effect=TimeoutError("S3 listing did not complete within 1s"),
        ):
            result = asyncio.run(pipeline.run_ingestion_pipeline(prefix_filter="", sync_only=True))

        assert result == {"ingested": 0, "failed": 0, "skipped": 0, "total_keys": 0}

        state = pipeline.get_sync_state()
        assert state["running"] is False
        assert "did not complete" in state["error"]

        saved = json.loads(last_sync_path.read_text())
        assert "did not complete" in saved["error"]
