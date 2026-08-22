"""Tests for MultiS3Loader and backward-compat S3Loader alias.

All AWS API calls are mocked so no real credentials are needed.
"""
from __future__ import annotations
import io
import json
from unittest.mock import MagicMock, patch, call
import pytest

from app.config.settings import settings
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
# MultiS3Loader — auto-discovery of all buckets when none are configured
# ---------------------------------------------------------------------------

def test_multi_loader_auto_discovers_all_buckets_when_none_configured():
    """An empty bucket_names list must mean 'no restriction — sync every
    bucket these credentials can see', not 'sync nothing'."""
    discovery_client = MagicMock()
    discovery_client.list_buckets.return_value = {
        "Buckets": [{"Name": "bucket-a"}, {"Name": "bucket-b"}]
    }
    client_a = MagicMock()
    client_b = MagicMock()

    with patch("boto3.client", side_effect=[discovery_client, client_a, client_b]):
        loader = MultiS3Loader([])

    assert loader.bucket_names == ["bucket-a", "bucket-b"]
    discovery_client.list_buckets.assert_called_once()


def test_multi_loader_auto_discover_disabled_stays_empty():
    """auto_discover=False must never call list_buckets — used by S3Loader,
    whose contract is one specific bucket or the local-filesystem fallback."""
    with patch("boto3.client") as mock_client:
        loader = MultiS3Loader([], auto_discover=False)

    assert loader.bucket_names == []
    mock_client.assert_not_called()


def test_multi_loader_discover_failure_falls_back_to_empty():
    """A ListAllMyBuckets failure (e.g. missing IAM permission) must degrade
    to an empty bucket list — same as a per-bucket listing error — not raise."""
    from botocore.exceptions import ClientError

    discovery_client = MagicMock()
    discovery_client.list_buckets.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": ""}}, "ListBuckets"
    )

    with patch("boto3.client", return_value=discovery_client):
        loader = MultiS3Loader([])

    assert loader.bucket_names == []


def test_s3_loader_does_not_auto_discover_when_unconfigured(monkeypatch):
    """S3Loader() with no bucket configured must hit the local-filesystem
    fallback, never attempt to discover/sync every visible bucket."""
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", None)
    monkeypatch.setattr(settings, "S3_BUCKET_NAMES", None)

    with patch("boto3.client") as mock_client:
        loader = S3Loader()

    assert loader.bucket_names == []
    mock_client.assert_not_called()


# ---------------------------------------------------------------------------
# MultiS3Loader — per-bucket prefix resolution (regression: a single global
# S3_DOCUMENT_PREFIX must never be force-applied to every configured bucket)
# ---------------------------------------------------------------------------

def test_multi_loader_applies_distinct_prefix_per_bucket(monkeypatch):
    """Two buckets configured with different S3_BUCKET_PREFIXES entries must
    each get their OWN Prefix in the list_objects_v2 call — not whichever
    bucket's prefix happens to be listed first."""
    monkeypatch.setattr(settings, "S3_BUCKET_PREFIXES", json.dumps({
        "all-acts-raw": "Acts", "income-tax-acts": "",
    }))

    client_a = MagicMock()
    client_b = MagicMock()
    client_a.get_paginator.return_value = _mock_paginator([_make_s3_page("all-acts-raw", [])])
    client_b.get_paginator.return_value = _mock_paginator([_make_s3_page("income-tax-acts", [])])

    with patch("boto3.client", side_effect=[client_a, client_b]):
        loader = MultiS3Loader(["all-acts-raw", "income-tax-acts"])
    loader.list_keys_with_meta()

    a_kwargs = client_a.get_paginator.return_value.paginate.call_args.kwargs
    b_kwargs = client_b.get_paginator.return_value.paginate.call_args.kwargs
    assert a_kwargs["Prefix"] == "Acts/"
    # Empty prefix means "scan the whole bucket" — no Prefix kwarg at all,
    # not inherited from the other bucket's "Acts/" restriction.
    assert "Prefix" not in b_kwargs


def test_multi_loader_unmapped_bucket_gets_no_prefix_restriction(monkeypatch):
    """A bucket absent from S3_BUCKET_PREFIXES must be scanned unrestricted
    even when S3_DOCUMENT_PREFIX is set to something else — this is exactly
    the bug: a third bucket must not inherit either of the other two
    buckets' folder scoping."""
    monkeypatch.setattr(settings, "S3_BUCKET_PREFIXES", json.dumps({"all-acts-raw": "Acts"}))
    monkeypatch.setattr(settings, "S3_DOCUMENT_PREFIX", "documents")

    client_a = MagicMock()
    client_c = MagicMock()
    client_a.get_paginator.return_value = _mock_paginator([_make_s3_page("all-acts-raw", [])])
    client_c.get_paginator.return_value = _mock_paginator([_make_s3_page("bucket-legal-9219", [])])

    with patch("boto3.client", side_effect=[client_a, client_c]):
        loader = MultiS3Loader(["all-acts-raw", "bucket-legal-9219"])
    loader.list_keys_with_meta()

    c_kwargs = client_c.get_paginator.return_value.paginate.call_args.kwargs
    assert "Prefix" not in c_kwargs


def test_zero_config_default_scans_full_bucket_no_folder_assumed(monkeypatch):
    """With nothing configured at all, S3_DOCUMENT_PREFIX defaults to empty
    — no folder is silently assumed, every bucket is scanned in full."""
    monkeypatch.setattr(settings, "S3_BUCKET_PREFIXES", None)
    monkeypatch.setattr(settings, "S3_DOCUMENT_PREFIX", "")

    client = MagicMock()
    client.get_paginator.return_value = _mock_paginator([_make_s3_page("any-bucket", [])])

    with patch("boto3.client", return_value=client):
        loader = MultiS3Loader(["any-bucket"])
    loader.list_keys_with_meta()

    kwargs = client.get_paginator.return_value.paginate.call_args.kwargs
    assert "Prefix" not in kwargs


def test_single_bucket_still_honors_explicit_s3_document_prefix(monkeypatch):
    """Single-bucket legacy behavior: if a user explicitly sets
    S3_DOCUMENT_PREFIX, it still applies when there is exactly one bucket."""
    monkeypatch.setattr(settings, "S3_BUCKET_PREFIXES", None)
    monkeypatch.setattr(settings, "S3_DOCUMENT_PREFIX", "documents")

    client = MagicMock()
    client.get_paginator.return_value = _mock_paginator([_make_s3_page("solo-bucket", [])])

    with patch("boto3.client", return_value=client):
        loader = MultiS3Loader(["solo-bucket"])
    loader.list_keys_with_meta()

    kwargs = client.get_paginator.return_value.paginate.call_args.kwargs
    assert kwargs["Prefix"] == "documents/"


def test_explicit_string_prefix_still_applies_uniformly(monkeypatch):
    """S3Loader(bucket=X, prefix=Y) — an explicitly-passed plain string
    still scopes every configured bucket, since the caller asked for
    exactly that (unlike the settings-driven default)."""
    monkeypatch.setattr(settings, "S3_BUCKET_PREFIXES", json.dumps({"other-bucket": "unrelated"}))

    client = MagicMock()
    client.get_paginator.return_value = _mock_paginator([_make_s3_page("bucket-x", [])])

    with patch("boto3.client", return_value=client):
        loader = MultiS3Loader(["bucket-x"], prefix="explicit-scope")
    loader.list_keys_with_meta()

    kwargs = client.get_paginator.return_value.paginate.call_args.kwargs
    assert kwargs["Prefix"] == "explicit-scope/"


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

def test_s3_loader_single_bucket_compat(tmp_path, monkeypatch):
    """S3Loader(local_root=...) still works exactly like the original."""
    # Isolate from a live S3_BUCKET_NAME in the local .env so the loader takes
    # the local-filesystem fallback path instead of hitting real S3.
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", None)
    monkeypatch.setattr(settings, "S3_BUCKET_NAMES", None)
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

    # Each matched bucket keeps its OWN candidate prefix — this is the fix:
    # previously only the best match's prefix was written (as a single
    # global S3_DOCUMENT_PREFIX), which then got force-applied to every
    # bucket, hiding anything not living under that one bucket's folder.
    assert "S3_BUCKET_PREFIXES" in written
    prefixes = json.loads(written["S3_BUCKET_PREFIXES"])
    for bucket, expected_prefix in _BUCKET_CANDIDATES:
        assert prefixes[bucket] == expected_prefix
    # Confirms the buckets do NOT all share one prefix
    assert len(set(prefixes.values())) > 1


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
