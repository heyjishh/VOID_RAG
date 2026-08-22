"""
Runs once at startup. Detects S3 buckets via AWS CLI (profile=legal) and
injects gateway keys and S3 config into JURYAI/backend/.env.

Multi-bucket: when several candidate buckets are found they are all written as
``S3_BUCKET_NAMES=b1,b2,...``.  The legacy ``S3_BUCKET_NAME`` key is also
written (set to the highest-priority match) for backward compatibility.
"""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path

ENV_FILE = Path(__file__).parent.parent / ".env"

# Precedence list: earlier entries win when multiple candidates are found.
# (bucket_name, default_prefix)
_BUCKET_CANDIDATES: list[tuple[str, str]] = [
    ("all-acts-raw", "Acts"),
    ("income-tax-acts", ""),
    ("bucket-legal-9219", "documents"),
]

# Gateway .env path — resolved relative to the running user's home directory
_GATEWAY_ENV = Path.home() / "free-llm-gateway/.env"


def _read_gateway_key() -> str:
    if not _GATEWAY_ENV.exists():
        return ""
    for line in _GATEWAY_ENV.read_text().splitlines():
        if line.startswith("MASTER_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def _list_s3_buckets() -> list[str]:
    """Return all bucket names from ``aws s3 ls`` (profile=legal).

    Returns an empty list when the AWS CLI is unavailable, times out, or when
    the .env already contains both ``S3_BUCKET_NAME`` / ``S3_BUCKET_NAMES``
    and ``GATEWAY_KEY`` (nothing to do).
    """
    if ENV_FILE.exists():
        env = _read_existing_env()
        already_has_buckets = env.get("S3_BUCKET_NAMES") or env.get("S3_BUCKET_NAME")
        if already_has_buckets and env.get("GATEWAY_KEY"):
            return []
    try:
        result = subprocess.run(
            ["aws", "--profile", "legal", "s3", "ls"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        buckets: list[str] = []
        for line in result.stdout.splitlines():
            parts = line.strip().split()
            if parts:
                buckets.append(parts[-1])
        return buckets
    except Exception:
        return []


def _pick_all_matching_buckets(available: list[str]) -> list[tuple[str, str]]:
    """Return ALL ``(bucket_name, prefix)`` pairs that appear in *available*.

    Results are ordered by *_BUCKET_CANDIDATES* precedence (highest first).
    If none of the known candidates are present, the first available bucket is
    returned with an empty prefix.
    """
    matched: list[tuple[str, str]] = []
    for candidate, prefix in _BUCKET_CANDIDATES:
        if candidate in available:
            matched.append((candidate, prefix))
    if not matched and available:
        matched.append((available[0], ""))
    return matched


def _pick_best_bucket(available: list[str]) -> tuple[str, str]:
    """Return ``(bucket_name, prefix)`` for the highest-priority match.

    Kept for backward compatibility — callers that only need a single bucket
    can use this helper directly.
    """
    matches = _pick_all_matching_buckets(available)
    return matches[0] if matches else ("", "")


def _read_existing_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    result: dict[str, str] = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip().strip('"')
    return result


def _write_env(data: dict[str, str]) -> None:
    lines = [f"{k}={v}" for k, v in data.items()]
    ENV_FILE.write_text("\n".join(lines) + "\n")


def run_auto_configure() -> dict[str, str]:
    """Detect S3 bucket(s) + gateway config and write to .env.

    Returns the keys that were written (for logging / tests).

    Multi-bucket behaviour:
    - If multiple known candidates are found, writes
      ``S3_BUCKET_NAMES=b1,b2,...`` (all matched buckets) AND
      ``S3_BUCKET_PREFIXES={"b1": "...", "b2": "...", ...}`` — every matched
      bucket keeps its OWN candidate prefix, so bucket b2's folder is never
      forced onto bucket b1's. Collapsing this to a single S3_DOCUMENT_PREFIX
      (the old behavior) silently hid every bucket whose real folder layout
      didn't match whichever bucket happened to be first in the list.
    - ``S3_BUCKET_NAME`` / ``S3_DOCUMENT_PREFIX`` are still set from the best
      (first) match, for backward compatibility with code paths that only
      ever look at a single bucket.
    """
    env = _read_existing_env()
    written: dict[str, str] = {}

    # Skip entirely if already fully configured
    already_has_buckets = env.get("S3_BUCKET_NAMES") or env.get("S3_BUCKET_NAME")
    if already_has_buckets and env.get("GATEWAY_KEY"):
        return {}

    # --- S3 detection -------------------------------------------------------
    if not already_has_buckets:
        available = _list_s3_buckets()
        matches = _pick_all_matching_buckets(available)
        if matches:
            best_bucket, best_prefix = matches[0]

            # Backward-compat single-bucket keys
            env["S3_BUCKET_NAME"] = best_bucket
            env["S3_DOCUMENT_PREFIX"] = best_prefix
            env["AWS_REGION"] = "us-east-1"
            written["S3_BUCKET_NAME"] = best_bucket
            written["S3_DOCUMENT_PREFIX"] = best_prefix

            # Multi-bucket keys — always written so downstream code can rely on them
            bucket_names_csv = ",".join(b for b, _ in matches)
            env["S3_BUCKET_NAMES"] = bucket_names_csv
            written["S3_BUCKET_NAMES"] = bucket_names_csv

            bucket_prefixes_json = json.dumps({b: p for b, p in matches})
            env["S3_BUCKET_PREFIXES"] = bucket_prefixes_json
            written["S3_BUCKET_PREFIXES"] = bucket_prefixes_json

    # --- Gateway key --------------------------------------------------------
    if not env.get("GATEWAY_KEY"):
        key = _read_gateway_key()
        if key:
            env["GATEWAY_KEY"] = key
            env["GATEWAY_URL"] = "http://localhost:8080/v1"
            written["GATEWAY_KEY"] = key[:8] + "..."
            written["GATEWAY_URL"] = "http://localhost:8080/v1"

    if written:
        _write_env(env)
    return written
