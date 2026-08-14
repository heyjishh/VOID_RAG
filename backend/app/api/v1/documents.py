import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.config.settings import settings
from app.core.cache import document_index_get, document_index_set
from app.core.ingestion.s3_loader import MultiS3Loader

router = APIRouter()

logger = logging.getLogger("juryai.documents")

# Media types for the formats the ingestion parser supports (see
# app.core.ingestion.parser). Anything else the corpus never serves.
_MEDIA_TYPES = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown"}


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
