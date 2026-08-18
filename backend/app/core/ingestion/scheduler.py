from __future__ import annotations
import asyncio
import logging
from typing import Optional

from app.config.settings import settings
from app.core.ingestion.pipeline import run_ingestion_pipeline, get_sync_state

logger = logging.getLogger("juryai.scheduler")

_stop_event: Optional[asyncio.Event] = None
_sync_task: Optional[asyncio.Task] = None


async def _auto_sync_loop():
    global _stop_event
    _stop_event = asyncio.Event()
    interval = max(0, int(getattr(settings, "AUTO_SYNC_INTERVAL_MINUTES", 0) or 0))
    if interval <= 0:
        return

    logger.info("Auto-sync loop started: every %d minutes", interval)
    while not _stop_event.is_set():
        try:
            await asyncio.sleep(interval * 60)
            if _stop_event.is_set():
                break
            logger.info("Auto-sync: starting incremental S3 ingestion")
            await run_ingestion_pipeline(prefix_filter="", sync_only=True)
            logger.info("Auto-sync completed")
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Auto-sync failed: %s", exc)


def start_auto_sync() -> asyncio.Task:
    global _sync_task
    if _sync_task is None or _sync_task.done():
        _sync_task = asyncio.create_task(_auto_sync_loop())
    return _sync_task


def stop_auto_sync():
    global _stop_event, _sync_task
    if _stop_event:
        _stop_event.set()
    if _sync_task and not _sync_task.done():
        _sync_task.cancel()
    _sync_task = None
