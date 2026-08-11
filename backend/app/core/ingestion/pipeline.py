from __future__ import annotations
import asyncio
from app.core.ingestion.s3_loader import MultiS3Loader, S3Loader  # S3Loader kept for compat
from app.core.ingestion.parser import parse_bytes
from app.core.ingestion.manifest import Manifest
from app.core.retrieval.qdrant_store import QdrantStore
from app.core.retrieval.quickwit_store import QuickwitStore
from app.config.settings import settings

_SUPPORTED = (".pdf", ".txt", ".md")


async def run_ingestion_pipeline(
    prefix_filter: str = "",
    sync_only: bool = True,
) -> dict:
    """
    Ingest documents from S3.
    sync_only=True  → skip keys already in manifest (incremental)
    sync_only=False → re-process all matching keys (full re-ingest)
    Returns: {ingested, failed, skipped, total_keys}
    """
    def _sync_pipeline():
        loader = MultiS3Loader(settings.bucket_list)
        qdrant = QdrantStore()
        quickwit = QuickwitStore()
        manifest = Manifest()
        ingested_set = manifest.list_ingested()

        all_meta = loader.list_keys_with_meta()
        if prefix_filter:
            all_meta = [m for m in all_meta if m["key"].startswith(prefix_filter)]

        ingested = failed = skipped = 0
        newly_ingested = []

        for meta in all_meta:
            key = meta["key"]
            fname = key.split("/")[-1]

            if not any(fname.lower().endswith(ext) for ext in _SUPPORTED):
                continue

            # Skip already-ingested keys in sync mode
            if sync_only and key in ingested_set:
                skipped += 1
                continue

            data = loader.download(key, bucket=meta.get("bucket"))
            if data is None:
                failed += 1
                continue

            try:
                chunks = parse_bytes(data, fname)
                if chunks:
                    qdrant.upsert(chunks)
                    quickwit.upsert(chunks)
                    ingested += 1
                    newly_ingested.append(meta)
            except Exception:
                failed += 1

        if newly_ingested:
            manifest.mark_ingested_batch(newly_ingested)

        return {
            "ingested": ingested,
            "failed": failed,
            "skipped": skipped,
            "total_keys": len(all_meta),
        }

    return await asyncio.to_thread(_sync_pipeline)


async def get_sync_status() -> dict:
    """Returns how many keys are ingested vs pending across all configured S3 buckets."""
    def _check():
        loader = MultiS3Loader(settings.bucket_list)
        manifest = Manifest()
        all_meta = loader.list_keys_with_meta()
        pdf_keys = [m for m in all_meta if any(m["key"].lower().endswith(e) for e in _SUPPORTED)]
        ingested_set = manifest.list_ingested()
        pending = [m["key"] for m in pdf_keys if m["key"] not in ingested_set]
        return {
            "total_on_s3": len(pdf_keys),
            "ingested": manifest.count(),
            "pending": len(pending),
            "pending_keys": pending[:20],  # first 20 for preview
        }
    return await asyncio.to_thread(_check)
