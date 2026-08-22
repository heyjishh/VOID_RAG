import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.config.settings import settings
from app.core.cache import document_index_get, document_index_set
from app.core.ingestion.s3_loader import MultiS3Loader

router = APIRouter()

logger = logging.getLogger("juryai.documents")

# Media types for the formats the ingestion parser supports (see
# app.core.ingestion.parser). Anything else the corpus never serves.
_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".bmp": "image/bmp",
}


def _media_type(source: str) -> str:
    return _MEDIA_TYPES.get(Path(source).suffix.lower(), "application/octet-stream")


def _build_index(entries: list[dict]) -> dict:
    return {
        meta["key"].split("/")[-1]: {"key": meta["key"], "bucket": meta.get("bucket", "")}
        for meta in entries
    }


async def _resolve_source(loader: MultiS3Loader, source: str) -> dict | None:
    index = await document_index_get()
    if index and source in index:
        return index[source]

    # A cache miss must trigger a live re-list rather than a 404 — the corpus
    # is actively being ingested, so a just-uploaded file must be findable
    # immediately, not only after the cached index happens to expire.
    entries = await asyncio.to_thread(loader.list_keys_with_meta)
    index = _build_index(entries)
    await document_index_set(index)
    return index.get(source)


def _cache_path(source: str) -> Path:
    return Path(settings.DOCUMENT_CACHE_DIR) / source


def _read_cache_file(path: Path) -> bytes:
    return path.read_bytes()


def _write_cache_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


@router.get("/documents/folders")
async def list_document_folders():
    """Distinct folder prefixes across the corpus, derived straight from
    each object's S3 key path — not a hardcoded taxonomy. However the
    bucket is actually organized (flat today, nested tomorrow, multiple
    buckets) shows up here automatically, no code change needed."""
    loader = MultiS3Loader(settings.bucket_list)
    entries = await asyncio.to_thread(loader.list_keys_with_meta)

    counts: dict[tuple[str, str], int] = {}
    for e in entries:
        parts = e["key"].split("/")
        folder = "/".join(parts[:-1])  # "" for objects sitting at the bucket root
        bucket = e.get("bucket", "")
        counts[(bucket, folder)] = counts.get((bucket, folder), 0) + 1

    return {
        "folders": [
            {
                "bucket": bucket,
                "folder": folder,
                "prefix": f"{folder}/" if folder else "",
                "count": count,
            }
            for (bucket, folder), count in sorted(counts.items())
        ]
    }


@router.get("/documents")
async def list_documents(
    prefix: str = Query("", description="Filter by key prefix"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    loader = MultiS3Loader(settings.bucket_list)
    entries = await asyncio.to_thread(loader.list_keys_with_meta)

    if prefix:
        entries = [e for e in entries if e["key"].startswith(prefix)]

    entries = sorted(entries, key=lambda e: e["key"])
    # Total across the full (filtered) corpus, not just this page — callers
    # paginating (e.g. the composer's source picker) need this to know
    # whether a second page exists at all.
    total = len(entries)
    page = entries[offset:offset + limit]

    return {
        "total": total,
        "documents": [
            {
                "key": e["key"],
                "filename": e["key"].split("/")[-1],
                "size": e.get("size", 0),
                "etag": e.get("etag", ""),
                "bucket": e.get("bucket", ""),
                "media_type": _media_type(e["key"].split("/")[-1]),
            }
            for e in page
        ],
    }


@router.get("/documents/view")
async def view_document(source: str):
    if "/" in source or ".." in source:
        raise HTTPException(status_code=400, detail="source must be a bare filename")

    cache_path = _cache_path(source)
    if cache_path.exists():
        data = await asyncio.to_thread(_read_cache_file, cache_path)
        return Response(
            content=data,
            media_type=_media_type(source),
            headers={"Content-Disposition": f'inline; filename="{source}"'},
        )

    loader = MultiS3Loader(settings.bucket_list)
    resolved = await _resolve_source(loader, source)
    if resolved is None:
        raise HTTPException(status_code=404, detail=f"No document found for source: {source}")

    data = await asyncio.to_thread(loader.download, resolved["key"], bucket=resolved.get("bucket") or None)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Document bytes unavailable for source: {source}")

    try:
        await asyncio.to_thread(_write_cache_file, cache_path, data)
    except OSError as exc:
        logger.warning("document cache write failed for %s: %s", source, exc)

    return Response(
        content=data,
        media_type=_media_type(source),
        headers={"Content-Disposition": f'inline; filename="{source}"'},
    )
