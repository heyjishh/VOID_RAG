from contextlib import asynccontextmanager

import asyncio
import logging
import os

from app.config.settings import settings

# Must run before torch/numpy is imported anywhere in the process — OpenMP/MKL
# read these once, at first init. Unbounded, each concurrent inference call
# (embedder, reranker, ColBERT) spins up its own thread team sized to the full
# core count, so chat and ingestion running together multiplies into hundreds
# of OS threads thrashing on context switches instead of computing.
os.environ.setdefault("OMP_NUM_THREADS", str(settings.ML_NUM_THREADS))
os.environ.setdefault("MKL_NUM_THREADS", str(settings.ML_NUM_THREADS))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("juryai")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    logger.info("Lifespan startup begin")

    from app.core.db import ping, ensure_tables
    if not await ping():
        logger.warning("Postgres unreachable at startup — audit log writes will fail until it recovers")
    else:
        await ensure_tables()

    stop_event = asyncio.Event()
    interval = max(0, int(getattr(settings, "AUTO_SYNC_INTERVAL_MINUTES", 0) or 0))
    task = None
    if interval > 0 and settings.s3_bucket_names_list:
        from app.core.ingestion.scheduler import start_auto_sync
        task = start_auto_sync()
        logger.info("Auto-sync enabled: every %d minutes", interval)
    else:
        if not settings.s3_bucket_names_list:
            logger.info("Auto-sync disabled: no S3 buckets configured")
        else:
            logger.info("Auto-sync disabled: AUTO_SYNC_INTERVAL_MINUTES=0")

    yield

    if task:
        from app.core.ingestion.scheduler import stop_auto_sync
        stop_auto_sync()


def create_app() -> FastAPI:
    # Auto-configure S3 + gateway before settings are frozen
    from scripts.auto_configure import run_auto_configure
    written = run_auto_configure()
    if written:
        logging.getLogger("juryai").info(f"Auto-configured: {list(written.keys())}")

    app = FastAPI(title="JURYAI", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    from app.api.v1 import chat, ingest, documents, draft, auth, conversations, interact
    app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
    app.include_router(ingest.router, prefix="/api/v1", tags=["ingest"])
    app.include_router(documents.router, prefix="/api/v1", tags=["documents"])
    app.include_router(draft.router, prefix="/api/v1", tags=["draft"])
    app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
    app.include_router(conversations.router, prefix="/api/v1", tags=["conversations"])
    app.include_router(interact.router, prefix="/api/v1", tags=["interact"])

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8100, reload=True)
