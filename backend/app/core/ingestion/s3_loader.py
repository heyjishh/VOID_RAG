from __future__ import annotations
from pathlib import Path
from typing import Optional
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from app.config.settings import settings

_BOTO_CONFIG = Config(
    connect_timeout=3,
    read_timeout=5,
    retries={"max_attempts": 1, "mode": "standard"},
    parameter_validation=False,
    s3={"addressing_style": "path"},
)


class MultiS3Loader:
    """S3 loader that operates across one or more buckets.

    Each item returned by ``list_keys_with_meta()`` includes a ``bucket``
    field so callers know which bucket the object lives in.  ``download()``
    accepts an optional *bucket* hint; when omitted it tries every bucket in
    declaration order.
    """

    def __init__(
        self,
        bucket_names: list[str],
        prefix: Optional[str | dict[str, str]] = None,
        region: Optional[str] = None,
        local_root: Optional[str] = None,
        auto_discover: bool = True,
    ):
        self.region: str = region or settings.AWS_REGION
        self.local_root: Path = Path(local_root or "/tmp/juryai-storage")

        resolved_names = [b for b in bucket_names if b]
        if not resolved_names and auto_discover:
            # No bucket configured at all — discover every bucket visible to
            # these credentials rather than silently syncing nothing. This is
            # what an empty S3_BUCKET_NAME/S3_BUCKET_NAMES is meant to mean:
            # "no restriction", the same philosophy as the empty-prefix
            # default, extended one level up to bucket selection itself.
            resolved_names = self._discover_all_buckets(self.region)
        self.bucket_names: list[str] = resolved_names
        self._prefixes: dict[str, str] = self._resolve_prefixes(prefix, self.bucket_names)

        # One boto3 client per bucket (same credentials, different logical target)
        self._clients: dict[str, object] = {}
        for bucket in self.bucket_names:
            self._clients[bucket] = boto3.client(
                "s3",
                region_name=self.region,
                config=_BOTO_CONFIG,
                **(
                    {
                        "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
                        "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
                    }
                    if settings.AWS_ACCESS_KEY_ID
                    else {}
                ),
            )

    @staticmethod
    def _discover_all_buckets(region: str) -> list[str]:
        """List every bucket the configured credentials can see via
        ListAllMyBuckets. Requires that IAM permission specifically (distinct
        from per-bucket ListBucket/GetObject) — falls back to an empty list
        (and from there to the local-filesystem fallback) on any failure,
        same as a per-bucket listing error."""
        try:
            client = boto3.client(
                "s3",
                region_name=region,
                config=_BOTO_CONFIG,
                **(
                    {
                        "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
                        "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
                    }
                    if settings.AWS_ACCESS_KEY_ID
                    else {}
                ),
            )
            resp = client.list_buckets()
            return [b["Name"] for b in resp.get("Buckets", []) if b.get("Name")]
        except (BotoCoreError, ClientError):
            return []

    @staticmethod
    def _resolve_prefixes(prefix: Optional[str | dict[str, str]], bucket_names: list[str]) -> dict[str, str]:
        """Per-bucket prefix resolution.

        - An explicit dict (or settings.S3_BUCKET_PREFIXES) always wins per bucket.
        - An explicit plain string applies to every bucket — the caller asked
          for exactly that (e.g. S3Loader(bucket=X, prefix=Y)).
        - With nothing explicit and exactly one bucket configured,
          S3_DOCUMENT_PREFIX applies (true single-bucket legacy behavior).
        - With nothing explicit and MULTIPLE buckets, a bucket absent from
          the mapping is scanned unrestricted (""), not silently forced onto
          whatever prefix another bucket happens to use.
        """
        if isinstance(prefix, dict):
            explicit_map, fallback = dict(prefix), ""
        elif isinstance(prefix, str):
            explicit_map, fallback = {}, prefix
        else:
            explicit_map = dict(settings.s3_bucket_prefixes)
            fallback = settings.S3_DOCUMENT_PREFIX if len(bucket_names) == 1 else ""
        return {b: (explicit_map.get(b, fallback) or "").strip("/") for b in bucket_names}

    @property
    def _is_configured(self) -> bool:
        return bool(self.bucket_names)

    def list_keys(self) -> list[str]:
        return [m["key"] for m in self.list_keys_with_meta()]

    def list_keys_with_meta(self) -> list[dict]:
        """Return ``[{key, size, etag, bucket}]`` for all objects across all buckets."""
        if self._is_configured:
            results: list[dict] = []
            for bucket in self.bucket_names:
                client = self._clients[bucket]
                try:
                    paginator = client.get_paginator("list_objects_v2")
                    bucket_prefix = self._prefixes.get(bucket, "")
                    prefix_path = bucket_prefix + "/" if bucket_prefix else ""
                    paginate_kwargs = {
                        "Bucket": bucket,
                        "PaginationConfig": {"MaxItems": 1000},
                    }
                    if prefix_path:
                        paginate_kwargs["Prefix"] = prefix_path
                    for page in paginator.paginate(**paginate_kwargs):
                        for obj in page.get("Contents", []):
                            results.append(
                                {
                                    "key": obj["Key"],
                                    "size": obj["Size"],
                                    "etag": obj.get("ETag", "").strip('"'),
                                    "bucket": bucket,
                                }
                            )
                except (BotoCoreError, ClientError):
                    continue
            if results:
                return results

        # Local fallback — used in tests and when no bucket is configured
        if not self.local_root.exists():
            return []
        return [
            {
                "key": p.name,
                "size": p.stat().st_size,
                "etag": str(p.stat().st_mtime),
                "bucket": "",
            }
            for p in self.local_root.iterdir()
            if p.is_file()
        ]

    def download(self, key: str, bucket: str | None = None) -> bytes | None:
        """Download *key* from S3.

        If *bucket* is given, fetch only from that bucket.
        Otherwise try every bucket in declaration order, returning the first hit.
        Falls back to the local filesystem when no bucket is configured or all
        S3 attempts fail.
        """
        if self._is_configured:
            buckets_to_try = [bucket] if bucket else self.bucket_names
            for b in buckets_to_try:
                client = self._clients.get(b)
                if client is None:
                    continue
                try:
                    resp = client.get_object(Bucket=b, Key=key)
                    return resp["Body"].read()
                except (BotoCoreError, ClientError):
                    continue

        # Local fallback
        resolved = (self.local_root / key).resolve()
        if not str(resolved).startswith(str(self.local_root.resolve()) + "/"):
            return None
        return resolved.read_bytes() if resolved.exists() else None


class S3Loader(MultiS3Loader):
    """Single-bucket loader — backward-compatible wrapper around ``MultiS3Loader``.

    All existing code that instantiates ``S3Loader(bucket=..., prefix=...)``
    continues to work without changes.
    """

    def __init__(
        self,
        bucket: Optional[str] = None,
        prefix: Optional[str] = None,
        region: Optional[str] = None,
        local_root: Optional[str] = None,
    ):
        effective_bucket = bucket or settings.S3_BUCKET_NAME
        super().__init__(
            bucket_names=[effective_bucket] if effective_bucket else [],
            prefix=prefix,
            region=region,
            local_root=local_root,
            # S3Loader's contract is "one specific bucket, or the local
            # filesystem fallback" — auto-discovering every visible bucket
            # doesn't fit a caller that explicitly asked for a single one.
            auto_discover=False,
        )
        # Preserve ``self.bucket`` for any code that reads it directly
        self.bucket: Optional[str] = effective_bucket
