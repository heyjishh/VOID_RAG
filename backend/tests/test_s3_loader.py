"""Tests for MultiS3Loader and backward-compat S3Loader alias.

All AWS API calls are mocked so no real credentials are needed.
"""
from __future__ import annotations
import io
from unittest.mock import MagicMock, patch, call
import pytest

from app.core.ingestion.s3_loader import MultiS3Loader, S3Loader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_s3_page(bucket: str, keys: list[str]) -> dict:
    """Build a fake ``list_objects_v2`` response page."""
    return {
        "Contents": [
            {"Key": k, "Size": len(k), "ETag": f'"{k}-etag"'}
            for k in keys
        ]
    }


def _mock_paginator(pages: list[dict]):
    """Return a paginator mock whose ``paginate()`` yields *pages*."""
    paginator = MagicMock()
    paginator.paginate.return_value = iter(pages)
    return paginator


# ---------------------------------------------------------------------------
# MultiS3Loader — list_keys_with_meta across two buckets
# ---------------------------------------------------------------------------

def test_multi_loader_lists_both_buckets():
    """list_keys_with_meta aggregates objects from every configured bucket."""
    client_a = MagicMock()
    client_b = MagicMock()

    client_a.get_paginator.return_value = _mock_paginator(
        [_make_s3_page("bucket-a", ["a/doc1.pdf", "a/doc2.txt"])]
    )
    client_b.get_paginator.return_value = _mock_paginator(
        [_make_s3_page("bucket-b", ["b/report.pdf"])]
    )

    with patch("boto3.client", side_effect=[client_a, client_b]):
        loader = MultiS3Loader(["bucket-a", "bucket-b"])

    items = loader.list_keys_with_meta()

    assert len(items) == 3
    buckets = {i["bucket"] for i in items}
    assert buckets == {"bucket-a", "bucket-b"}

    keys = {i["key"] for i in items}
    assert "a/doc1.pdf" in keys
    assert "b/report.pdf" in keys


def test_multi_loader_items_have_bucket_field():
    """Every item returned by list_keys_with_meta must carry a 'bucket' field."""
    client = MagicMock()
    client.get_paginator.return_value = _mock_paginator(
        [_make_s3_page("only-bucket", ["x.pdf"])]
    )

    with patch("boto3.client", return_value=client):
        loader = MultiS3Loader(["only-bucket"])

    items = loader.list_keys_with_meta()
    assert all("bucket" in item for item in items)
    assert items[0]["bucket"] == "only-bucket"


# ---------------------------------------------------------------------------
# MultiS3Loader — download with and without bucket hint
# ---------------------------------------------------------------------------

def test_download_with_bucket_hint_targets_correct_bucket():
    """download(key, bucket=X) fetches only from bucket X, not others."""
    client_a = MagicMock()
    client_b = MagicMock()
    client_b.get_object.return_value = {"Body": io.BytesIO(b"data-from-b")}

    with patch("boto3.client", side_effect=[client_a, client_b]):
        loader = MultiS3Loader(["bucket-a", "bucket-b"])

    result = loader.download("some/key.pdf", bucket="bucket-b")

    assert result == b"data-from-b"
    client_a.get_object.assert_not_called()
    client_b.get_object.assert_called_once_with(Bucket="bucket-b", Key="some/key.pdf")


def test_download_without_bucket_hint_tries_in_order():
    """download(key) without a bucket hint iterates buckets in declaration order."""
    from botocore.exceptions import ClientError

    client_a = MagicMock()
    client_a.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": ""}}, "GetObject"
    )
    client_b = MagicMock()
    client_b.get_object.return_value = {"Body": io.BytesIO(b"found-in-b")}

    with patch("boto3.client", side_effect=[client_a, client_b]):
        loader = MultiS3Loader(["bucket-a", "bucket-b"])

    result = loader.download("missing-in-a.pdf")

    assert result == b"found-in-b"
    client_a.get_object.assert_called_once()
    client_b.get_object.assert_called_once()


# ---------------------------------------------------------------------------
# S3Loader — backward-compat single-bucket alias
# ---------------------------------------------------------------------------

def test_s3_loader_single_bucket_compat(tmp_path):
    """S3Loader(local_root=...) still works exactly like the original."""
    (tmp_path / "legacy.pdf").write_bytes(b"%PDF-legacy")

    loader = S3Loader(local_root=str(tmp_path))
    keys = loader.list_keys()

    assert "legacy.pdf" in keys


def test_s3_loader_download_local_fallback(tmp_path):
    """S3Loader.download() falls back to local filesystem when no bucket."""
    (tmp_path / "local.txt").write_bytes(b"hello local")

    loader = S3Loader(local_root=str(tmp_path))
    data = loader.download("local.txt")

    assert data == b"hello local"


def test_s3_loader_exposes_bucket_attribute():
    """S3Loader.bucket is set for legacy code that reads the attribute directly."""
    with patch("boto3.client", return_value=MagicMock()):
        loader = S3Loader(bucket="my-single-bucket")

    assert loader.bucket == "my-single-bucket"
    # Also check that MultiS3Loader internals are wired correctly
    assert loader.bucket_names == ["my-single-bucket"]


# ---------------------------------------------------------------------------
# auto_configure — multi-bucket detection
# ---------------------------------------------------------------------------

def test_auto_configure_writes_all_matching_buckets(tmp_path):
    """auto_configure detects all candidate buckets and writes S3_BUCKET_NAMES."""
    from scripts.auto_configure import run_auto_configure, _BUCKET_CANDIDATES
    import scripts.auto_configure as ac_mod

    # Simulate `aws s3 ls` listing three of our four known candidates
    available_candidates = [c for c, _ in _BUCKET_CANDIDATES[:3]]
    fake_aws_output = "\n".join(
        f"2024-01-01 00:00:00 {b}" for b in available_candidates
    )

    env_file = tmp_path / ".env"
    # No prior config — fresh run
    saved_env = ac_mod.ENV_FILE
    ac_mod.ENV_FILE = env_file

    try:
        with (
            patch.object(ac_mod, "_list_s3_buckets", return_value=available_candidates),
            patch.object(ac_mod, "_read_gateway_key", return_value=""),
        ):
            written = run_auto_configure()
    finally:
        ac_mod.ENV_FILE = saved_env

    assert "S3_BUCKET_NAMES" in written
    written_names = written["S3_BUCKET_NAMES"].split(",")
    # All three candidates must appear
    assert len(written_names) == 3
    for name in available_candidates:
        assert name in written_names

    # Backward-compat key must also be written
    assert "S3_BUCKET_NAME" in written
    # Best match is the first candidate
    assert written["S3_BUCKET_NAME"] == _BUCKET_CANDIDATES[0][0]


def test_auto_configure_single_bucket_fallback(tmp_path):
    """auto_configure writes S3_BUCKET_NAMES even when only one bucket matches."""
    from scripts.auto_configure import run_auto_configure, _BUCKET_CANDIDATES
    import scripts.auto_configure as ac_mod

    best_bucket = _BUCKET_CANDIDATES[0][0]
    env_file = tmp_path / ".env"
    saved_env = ac_mod.ENV_FILE
    ac_mod.ENV_FILE = env_file

    try:
        with (
            patch.object(ac_mod, "_list_s3_buckets", return_value=[best_bucket]),
            patch.object(ac_mod, "_read_gateway_key", return_value=""),
        ):
            written = run_auto_configure()
    finally:
        ac_mod.ENV_FILE = saved_env

    assert written["S3_BUCKET_NAMES"] == best_bucket
    assert written["S3_BUCKET_NAME"] == best_bucket
