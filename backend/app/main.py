from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Connectivity check only — Alembic owns schema/table creation, never
    # Base.metadata.create_all here. A down Postgres logs loudly but must
    # not block startup (the audit log write path already degrades safely).
    import logging
    from app.core.db import ping
    if not await ping():
        logging.getLogger("juryai").warning(
            "Postgres unreachable at startup — audit log writes will fail until it recovers"
        )
    yield


def create_app() -> FastAPI:
    # Auto-configure S3 + gateway before settings are frozen
    from scripts.auto_configure import run_auto_configure
    written = run_auto_configure()
    if written:
        import logging
        logging.getLogger("juryai").info(f"Auto-configured: {list(written.keys())}")

    app = FastAPI(title="JURYAI", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    from app.api.v1 import chat, ingest, documents, draft, auth
    app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
    app.include_router(ingest.router, prefix="/api/v1", tags=["ingest"])
    app.include_router(documents.router, prefix="/api/v1", tags=["documents"])
    app.include_router(draft.router, prefix="/api/v1", tags=["draft"])
    app.include_router(auth.router, prefix="/api/v1", tags=["auth"])

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8100, reload=True)
