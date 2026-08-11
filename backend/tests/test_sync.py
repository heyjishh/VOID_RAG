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


def test_sync_only_skips_ingested_keys(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    with patch("app.core.ingestion.manifest.MANIFEST_PATH", manifest_path):
        from app.core.ingestion.manifest import Manifest
        m = Manifest()
        m.mark_ingested("Acts/already.pdf", size=100, etag="e1")

        from unittest.mock import AsyncMock
        import asyncio

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
            result = asyncio.run(
                __import__("app.core.ingestion.pipeline", fromlist=["run_ingestion_pipeline"])
                .run_ingestion_pipeline(prefix_filter="", sync_only=True)
            )
        # only "new.pdf" processed; "already.pdf" skipped
        assert result["ingested"] == 1
        assert result["skipped"] == 1
