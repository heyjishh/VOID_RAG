from __future__ import annotations
import json
import logging
import asyncio
import os
import time
from pathlib import Path

import psutil

logger = logging.getLogger(__name__)

from app.core.ingestion.s3_loader import MultiS3Loader, S3Loader  # S3Loader kept for compat
from app.core.ingestion.parser import parse_bytes
from app.core.ingestion.manifest import Manifest
from app.core.retrieval.qdrant_store import QdrantStore
from app.core.retrieval.quickwit_store import QuickwitStore
from app.config.settings import settings

_SUPPORTED = (".pdf", ".txt", ".md")
_INGEST_BATCH_SIZE = 32
_INGEST_MIN_CONCURRENT = 2
_INGEST_MAX_CONCURRENT = min(24, (os.cpu_count() or 2) * 4)

# In-memory sync state (safe for single-process uvicorn; for multi-worker
# deployments swap this for Redis/Postgres-backed state).
_sync_state = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "processed": 0,
    "total": 0,
    "ingested": 0,
    "failed": 0,
    "skipped": 0,
    "current_key": "",
    "error": None,
    "concurrency": _INGEST_MIN_CONCURRENT,
    "cpu_percent": 0.0,
}
_sync_lock = asyncio.Lock()


class _CpuGovernor:
    """Samples this process's CPU usage and scales the ingestion concurrency
    ceiling to stay under a configured budget (default 50%) — the AIMD
    limiter below reacts to success/failure, this reacts to actual host
    load. Ceiling never drops below `min_ceiling`: a throttled pipeline
    stays alive, it doesn't stall.
    """

    def __init__(self, budget_percent: float, min_ceiling: int, max_ceiling: int, sample_interval: float):
        self._budget = budget_percent
        self._min_ceiling = min_ceiling
        self._max_ceiling = max_ceiling
        self._interval = sample_interval
        self._cores = psutil.cpu_count() or 1
        self.ceiling = max_ceiling
        self.last_percent = 0.0
        self._task: asyncio.Task | None = None

    def _step(self, percent: float):
        """One control-loop decision, split out from `_loop` so it's testable
        without mocking psutil or asyncio.sleep."""
        self.last_percent = percent
        if percent > self._budget:
            self.ceiling = max(self._min_ceiling, self.ceiling - 1)
        elif percent < self._budget * 0.7 and self.ceiling < self._max_ceiling:
            self.ceiling += 1

    async def _loop(self):
        proc = psutil.Process()
        proc.cpu_percent()  # prime — first call always returns 0.0
        while True:
            await asyncio.sleep(self._interval)
            self._step(proc.cpu_percent() / self._cores)

    def start(self):
        self._task = asyncio.create_task(self._loop())

    def stop(self):
        if self._task:
            self._task.cancel()


class _AdaptiveLimiter:
    """Concurrency cap that self-tunes to what the box can actually sustain,
    instead of a fixed guess. AIMD (the TCP congestion-control rule): +1 on
    every success, halved on failure — climbs fast when things are healthy,
    backs off hard the moment downloads/parses/upserts start failing (memory
    pressure, S3 throttling, a slow Qdrant/Quickwit). An optional CPU
    governor further clamps the ceiling to a host-load budget.
    """

    def __init__(self, initial: int, minimum: int, maximum: int, governor: "_CpuGovernor | None" = None):
        self._limit = max(minimum, min(initial, maximum))
        self._min = minimum
        self._max = maximum
        self._governor = governor
        self._active = 0
        self._cond = asyncio.Condition()

    @property
    def limit(self) -> int:
        if self._governor is None:
            return self._limit
        return max(self._min, min(self._limit, self._governor.ceiling))

    async def acquire(self):
        async with self._cond:
            while self._active >= self.limit:
                await self._cond.wait()
            self._active += 1

    async def release(self, ok: bool):
        async with self._cond:
            self._active -= 1
            self._limit = min(self._max, self._limit + 1) if ok else max(self._min, self._limit // 2)
            self._cond.notify_all()


async def _set_sync_state(running=None, **kwargs):
    async with _sync_lock:
        if running is not None:
            _sync_state["running"] = running
        for k, v in kwargs.items():
            if k in _sync_state:
                _sync_state[k] = v


def get_sync_state() -> dict:
    # This is called from sync contexts (tests, status endpoint fallback).
    # In production the status endpoint uses the async path below.
    return dict(_sync_state)


_background_tasks: set[asyncio.Task] = set()


async def start_background_ingestion(prefix_filter: str = "", sync_only: bool = True) -> bool:
    """Claim the run slot and launch ingestion as a detached background
    task — no HTTP request/response envelope (and no client-side axios
    timeout) bounds it, so a large batch is never cut off partway through.
    Returns False without starting a second run if one is already active.
    """
    async with _sync_lock:
        if _sync_state["running"]:
            return False
        _sync_state["running"] = True

    task = asyncio.create_task(run_ingestion_pipeline(prefix_filter=prefix_filter, sync_only=sync_only))
    # asyncio only holds a *weak* reference to a task once nothing else
    # references it — an unreferenced task can be silently garbage-collected
    # mid-run. Keep a strong reference until it's done.
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return True


async def run_ingestion_pipeline(
    prefix_filter: str = "",
    sync_only: bool = True,
    file_timeout: float | None = None,
) -> dict:
    """
    Ingest documents from S3 using async-native batch processing.
    sync_only=True  → skip keys already in manifest (incremental)
    sync_only=False → re-process all matching keys (full re-ingest)

    No overall wall-clock deadline — intended to be launched via
    `start_background_ingestion` and run to completion regardless of how
    long the batch takes. `file_timeout` only bounds a single file's
    download (a safety net against one hung connection eating a worker
    slot forever), not the run as a whole.

    Returns: {ingested, failed, skipped, total_keys}
    """
    file_timeout = file_timeout if file_timeout is not None else settings.INGEST_FILE_TIMEOUT_SECONDS
    started_at = time.time()

    listing_error: str | None = None
    try:
        pdf_keys = await _list_pdf_keys_with_timeout(prefix_filter, timeout=settings.INGEST_LIST_TIMEOUT_SECONDS)
    except Exception as exc:
        # Distinct from "listing succeeded, zero keys matched" — a listing
        # that timed out or errored must surface as an error in Last Sync,
        # not look identical to "nothing was pending".
        logger.exception("S3 listing failed")
        pdf_keys = []
        listing_error = str(exc)

    if not pdf_keys:
        finished_at = time.time()
        await _set_sync_state(
            running=False, started_at=started_at, finished_at=finished_at,
            total=0, processed=0, error=listing_error,
        )
        _save_last_sync({
            "started_at": started_at,
            "finished_at": finished_at,
            "ingested": 0,
            "failed": 0,
            "skipped": 0,
            "total": 0,
            "error": listing_error,
        })
        return {"ingested": 0, "failed": 0, "skipped": 0, "total_keys": 0}

    await _set_sync_state(
        running=True,
        started_at=started_at,
        finished_at=None,
        processed=0,
        total=len(pdf_keys),
        ingested=0,
        failed=0,
        skipped=0,
        current_key="",
        error=None,
    )

    ingested = 0
    failed = 0
    skipped = 0
    error_message: str | None = None
    governor: _CpuGovernor | None = None

    try:
        loader = MultiS3Loader(settings.bucket_list)
        qdrant = QdrantStore()
        quickwit = QuickwitStore()
        manifest = Manifest()
        ingested_set = manifest.list_ingested()
        manifest_lock = asyncio.Lock()

        governor = _CpuGovernor(
            budget_percent=settings.INGEST_CPU_BUDGET_PERCENT,
            min_ceiling=_INGEST_MIN_CONCURRENT,
            max_ceiling=_INGEST_MAX_CONCURRENT,
            sample_interval=settings.INGEST_CPU_SAMPLE_INTERVAL_SECONDS,
        )
        governor.start()
        limiter = _AdaptiveLimiter(
            _INGEST_MIN_CONCURRENT, _INGEST_MIN_CONCURRENT, _INGEST_MAX_CONCURRENT, governor=governor
        )

        async def _report(current_key: str = ""):
            await _set_sync_state(
                processed=skipped + ingested + failed,
                ingested=ingested,
                failed=failed,
                skipped=skipped,
                current_key=current_key,
                concurrency=limiter.limit,
                cpu_percent=round(governor.last_percent, 1),
            )

        async def _process_one(meta):
            nonlocal ingested, failed, skipped
            key = meta["key"]
            fname = key.split("/")[-1]

            if sync_only and key in ingested_set:
                async with manifest_lock:
                    skipped += 1
                await _report()
                return None, "skipped"

            await limiter.acquire()
            ok = False
            try:
                try:
                    data = await asyncio.wait_for(
                        asyncio.to_thread(loader.download, key, bucket=meta.get("bucket")),
                        timeout=file_timeout,
                    )
                except asyncio.TimeoutError:
                    async with manifest_lock:
                        failed += 1
                    return None, "failed"

                if data is None:
                    async with manifest_lock:
                        failed += 1
                    return None, "failed"

                try:
                    chunks = await asyncio.to_thread(parse_bytes, data, fname)
                    if chunks:
                        await asyncio.to_thread(qdrant.upsert, chunks)
                        await asyncio.to_thread(quickwit.upsert, chunks)
                        async with manifest_lock:
                            ingested += 1
                            # Checkpointed the instant this doc finishes, not batched
                            # for a single write at the very end of the whole run —
                            # a kill/crash mid-run (a long sync over hundreds of
                            # docs is exactly the kind of thing that gets
                            # interrupted) previously lost every completed doc's
                            # progress, since the manifest was only ever saved once
                            # after the full loop finished.
                            manifest.mark_ingested(key, meta["size"], meta["etag"])
                        ok = True
                        return meta, "ingested"
                except Exception:
                    logger.exception("Failed to ingest %s", key)
                    async with manifest_lock:
                        failed += 1
                    return None, "failed"
            finally:
                await limiter.release(ok)
                # Reported here — per document, the instant it finishes — rather
                # than only after the whole batch's gather() resolves. At low
                # concurrency a 32-doc batch can take many minutes to clear, and
                # batch-level reporting made real progress look frozen at 0 the
                # entire time.
                await _report(key)

        for batch_start in range(0, len(pdf_keys), _INGEST_BATCH_SIZE):
            batch = pdf_keys[batch_start:batch_start + _INGEST_BATCH_SIZE]
            tasks = [_process_one(meta) for meta in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    async with manifest_lock:
                        failed += 1
                    await _report()
    except Exception as exc:
        # Whatever failed (a store client, a listing race, a bug) — never
        # leave `running` stuck true. The next status poll must show the
        # failure, not a progress bar frozen mid-sync forever.
        logger.exception("Ingestion run aborted unexpectedly")
        error_message = str(exc)
    finally:
        if governor:
            governor.stop()

    finished_at = time.time()
    await _set_sync_state(
        running=False,
        finished_at=finished_at,
        processed=skipped + ingested + failed,
        ingested=ingested,
        failed=failed,
        skipped=skipped,
        current_key="",
        cpu_percent=0.0,
        error=error_message,
    )
    _save_last_sync({
        "started_at": started_at,
        "finished_at": finished_at,
        "ingested": ingested,
        "failed": failed,
        "skipped": skipped,
        "total": len(pdf_keys),
        "error": error_message,
    })

    return {
        "ingested": ingested,
        "failed": failed,
        "skipped": skipped,
        "total_keys": len(pdf_keys),
    }


def _list_pdf_keys(prefix_filter: str) -> list[dict]:
    """List S3 keys. Runs in a separate process with hard timeout."""
    loader = MultiS3Loader(settings.bucket_list)
    all_meta = loader.list_keys_with_meta()
    if prefix_filter:
        all_meta = [m for m in all_meta if m["key"].startswith(prefix_filter)]
    return [m for m in all_meta if any(m["key"].lower().endswith(e) for e in _SUPPORTED)]


async def _list_pdf_keys_with_timeout(prefix_filter: str, timeout: float | None = None) -> list[dict]:
    """List S3 keys off the event loop, bounded by a timeout (a per-listing
    safety net, not an overall run deadline).

    This used to fork a subprocess for isolation — os.fork() from a
    multi-threaded async server (uvicorn's event loop + its thread pool +
    model-loading threads) is a well-known deadlock trap: a lock held by
    any *other* thread at the instant of fork (malloc arena locks, import
    locks, an HTTP client's connection-pool lock) is inherited "locked
    forever" in the child, since the thread that would release it doesn't
    exist there. That's exactly what was happening — every forked listing
    call hung until it hit the timeout, while the plain to_thread listing
    used by /ingest/status (no fork) worked every time. Matching that
    proven-safe pattern here removes the deadlock risk entirely; a genuinely
    hung call just ties up one thread-pool worker rather than pegging an
    orphaned process at full CPU.
    """
    timeout = timeout if timeout is not None else settings.INGEST_LIST_TIMEOUT_SECONDS
    try:
        return await asyncio.wait_for(asyncio.to_thread(_list_pdf_keys, prefix_filter), timeout=timeout)
    except asyncio.TimeoutError:
        # Distinct from "listing succeeded, zero keys matched" — the caller
        # needs to know the run stopped because listing didn't finish, not
        # because there was genuinely nothing to sync.
        raise TimeoutError(f"S3 listing did not complete within {timeout:.0f}s") from None


def check_s3_connectivity(timeout: float = 5.0) -> bool:
    """Quick S3 connectivity check. Returns True if S3 is reachable."""
    import socket
    try:
        sock = socket.create_connection(("s3.us-east-1.amazonaws.com", 443), timeout=timeout)
        sock.close()
        return True
    except OSError:
        return False


# Last-completed-run summary — persisted to disk (like the manifest) so it
# survives a backend restart or the user closing and reopening the app. The
# live `_sync_state` above is reset to defaults on process restart; this is
# not, which is what lets the UI answer "when did it last stop, and how did
# it go" even after the app was closed mid-run or the server bounced.
_LAST_SYNC_PATH = Path(__file__).parent.parent.parent.parent / ".last_sync.json"


def _load_last_sync() -> dict | None:
    if _LAST_SYNC_PATH.exists():
        try:
            return json.loads(_LAST_SYNC_PATH.read_text())
        except Exception:
            return None
    return None


def _save_last_sync(data: dict) -> None:
    try:
        _LAST_SYNC_PATH.write_text(json.dumps(data, indent=2))
    except Exception:
        logger.exception("Failed to persist last sync summary")


_status_snapshot: dict | None = None
_status_snapshot_at = 0.0
_status_snapshot_lock = asyncio.Lock()


def _check_s3_vs_manifest() -> dict:
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
        "last_sync": _load_last_sync(),
    }


async def get_sync_status() -> dict:
    """Returns how many keys are ingested vs pending across all configured S3
    buckets, merged with live in-progress counters.

    The S3 listing is the expensive part (a full bucket LIST, per bucket) —
    it's cached for INGEST_STATUS_CACHE_TTL_SECONDS so frequent frontend
    polling doesn't repeatedly hammer S3 for a number that barely changes
    between polls. Live progress fields (processed/ingested/current_key/
    concurrency/cpu_percent) are never cached — they're read fresh every call.
    """
    global _status_snapshot, _status_snapshot_at

    now = time.time()
    async with _status_snapshot_lock:
        stale = _status_snapshot is None or (now - _status_snapshot_at) >= settings.INGEST_STATUS_CACHE_TTL_SECONDS
        if stale:
            _status_snapshot = await asyncio.to_thread(_check_s3_vs_manifest)
            _status_snapshot_at = now
        base = _status_snapshot

    sync_state = get_sync_state()
    # Merge without overwriting base ingestion counters with in-memory zeros.
    merged = {**base}
    for k, v in sync_state.items():
        if k not in base:
            merged[k] = v
    return merged
