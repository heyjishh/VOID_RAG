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
        prefix: Optional[str] = None,
        region: Optional[str] = None,
        local_root: Optional[str] = None,
    ):
        self.bucket_names: list[str] = [b for b in bucket_names if b]
        self.prefix: str = (prefix or settings.S3_DOCUMENT_PREFIX).strip("/")
        self.region: str = region or settings.AWS_REGION
        self.local_root: Path = Path(local_root or "/tmp/juryai-storage")

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
                    prefix_path = self.prefix + "/" if self.prefix else ""
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
        )
        # Preserve ``self.bucket`` for any code that reads it directly
        self.bucket: Optional[str] = effective_bucket
