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


_spice_proc: asyncio.subprocess.Process | None = None
_spice_container_id: str | None = None


_PROVIDER_SECRET_ENV = {
    "gemini": "GOOGLE_GEMINI_KEY",
    "groq": "GROQ_API_KEY",
    "nvidia": "NVIDIA_API_KEY",
    "sambanova": "SAMBANOVA_KEY",
    "cloudflare": "CLOUDFLARE_KEY",
    "gateway": "GATEWAY_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def _provider_secret_env(provider_name: str) -> str | None:
    """Env var name backing a provider's api_key — never the value itself.
    SpiceAI resolves ${secrets:VAR} against its own env/`.env` store, so the
    generated spicepod never needs to carry the live key."""
    if provider_name == "mistral":
        return "MISTRAL_KEY" if settings.MISTRAL_KEY else "MISTRAL_API_KEY"
    return _PROVIDER_SECRET_ENV.get(provider_name)


_SPICE_NQL_INCOMPATIBLE_PROVIDERS = {"groq"}


def _generate_spicepod():
    from pathlib import Path

    spicepod_dir = Path(__file__).resolve().parent.parent
    spicepod_path = spicepod_dir / "spicepod.yaml"

    models = []
    chain = [
        p for p in settings.llm_provider_chain
        if p.get("provider_name") not in _SPICE_NQL_INCOMPATIBLE_PROVIDERS
    ]
    if chain:
        p = chain[0]
        model_id = p.get("model") or ""
        model_entry = {
            "from": f"openai:{model_id}" if model_id else "openai",
            "name": settings.SPICE_MODEL,
            "params": {},
        }
        if p.get("base_url"):
            model_entry["params"]["endpoint"] = p["base_url"]
        secret_env = _provider_secret_env(p.get("provider_name", ""))
        if secret_env:
            model_entry["params"]["openai_api_key"] = f"${{secrets:{secret_env}}}"
        models.append(model_entry)

    pg_host = settings.POSTGRES_HOST
    pg_db = settings.POSTGRES_DB
    pg_schema = settings.POSTGRES_SCHEMA

    def _pg_dataset(name: str, table: str, *, full_text_search: bool = False) -> list[str]:
        block = [
            f"  - from: postgres:{pg_db}.{pg_schema}.{table}",
            f"    name: {name}",
            "    time_column: created_at",
            "    time_format: timestamptz",
            "    params:",
            f"      pg_host: {pg_host}",
            f'      pg_port: "{settings.POSTGRES_PORT}"',
            f"      pg_db: {pg_db}",
            f"      pg_user: {settings.POSTGRES_USER}",
            "      pg_pass: ${secrets:POSTGRES_PASSWORD}",
            "      pg_sslmode: disable",
            "    acceleration:",
            "      enabled: true",
            "      engine: duckdb",
            "      refresh_mode: append",
            "      refresh_check_interval: 2m",
        ]
        if full_text_search:
            block += [
                "    columns:",
                "      - name: chunk_text",
                "        full_text_search:",
                "          enabled: true",
                "          row_id:",
                "            - id",
            ]
        return block

    lines = [
        "version: v1",
        "kind: Spicepod",
        "name: juryai",
        "",
        "runtime:",
        f"  dataset_load_parallelism: {os.cpu_count() or 4}",
        "",
        "datasets:",
        *_pg_dataset(settings.SPICE_DATASET, "legal_chunks", full_text_search=True),
        "",
        *_pg_dataset("juris_void_chunks", "juris_void_chunks"),
    ]

    if models:
        lines.append("")
        lines.append("models:")
        for m in models:
            lines.append(f'  - from: "{m["from"]}"')
            lines.append(f"    name: {m['name']}")
            if m.get("params"):
                lines.append("    params:")
                for k, v in m["params"].items():
                    lines.append(f"      {k}: {v}")

    lines.append("")
    spicepod_path.write_text("\n".join(lines) + "\n")
    logger.info("Generated spicepod.yaml at %s", spicepod_path)
    return spicepod_dir


async def _spice_health_check() -> bool:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.SPICE_HTTP_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False


async def _start_spice_binary(spicepod_dir: str) -> bool:
    global _spice_proc
    import shutil

    if not shutil.which("spice"):
        if not settings.SPICE_AUTO_INSTALL:
            return False
        logger.info("SpiceAI binary not found — attempting install...")
        try:
            proc = await asyncio.create_subprocess_shell(
                "curl -fsSL https://install.spiceai.org | /bin/bash",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "SPICE_INSTALL_DIR": os.path.expanduser("~/.spice/bin")},
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            home_spice = os.path.expanduser("~/.spice/bin")
            if os.path.isdir(home_spice):
                os.environ["PATH"] = home_spice + ":" + os.environ.get("PATH", "")
            if not shutil.which("spice"):
                logger.info("Binary install failed (%s), will try Docker", stderr.decode()[:200])
                return False
            logger.info("SpiceAI binary installed")
        except (asyncio.TimeoutError, Exception) as exc:
            logger.info("Binary install failed (%s), will try Docker", exc)
            return False

    _spice_proc = await asyncio.create_subprocess_exec(
        "spice", "run",
        cwd=spicepod_dir,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return True


async def _start_spice_docker(spicepod_dir: str) -> bool:
    global _spice_container_id
    import shutil
    if not shutil.which("docker"):
        logger.warning("Neither spice binary nor docker available — SpiceAI disabled")
        return False

    logger.info("Starting SpiceAI via Docker...")
    spice_port = settings.SPICE_HTTP_URL.split(":")[-1].rstrip("/")

    proc = await asyncio.create_subprocess_exec(
        "docker", "run", "-d",
        "--name", "voidrag-spice",
        "--rm",
        "-p", f"{spice_port}:{spice_port}",
        "-v", f"{spicepod_dir}:/app",
        "-w", "/app",
        "--add-host", "host.docker.internal:host-gateway",
        "--cpus", str(os.cpu_count() or 4),
        "spiceai/spiceai:latest",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    if proc.returncode != 0:
        err = stderr.decode()[:300]
        if "Conflict" in err:
            logger.info("SpiceAI container already exists — removing and retrying")
            await (await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", "voidrag-spice",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )).wait()
            return await _start_spice_docker(spicepod_dir)
        logger.warning("Docker start failed: %s", err)
        return False
    _spice_container_id = stdout.decode().strip()[:12]
    logger.info("SpiceAI Docker container started: %s", _spice_container_id)
    return True


async def _start_spice():
    if not settings.SPICE_ENABLED:
        logger.info("SpiceAI disabled via SPICE_ENABLED=false")
        return
    if await _spice_health_check():
        logger.info("SpiceAI already running at %s", settings.SPICE_HTTP_URL)
        return
    try:
        spicepod_dir = str(_generate_spicepod())
    except Exception as exc:
        logger.warning("Failed to generate spicepod.yaml: %s", exc)
        return

    started = await _start_spice_binary(spicepod_dir)
    if not started:
        started = await _start_spice_docker(spicepod_dir)
    if not started:
        return

    for _ in range(20):
        await asyncio.sleep(1)
        if await _spice_health_check():
            logger.info("SpiceAI healthy at %s", settings.SPICE_HTTP_URL)
            return
    logger.warning("SpiceAI started but health check timed out after 20s")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    logger.info("Lifespan startup begin")

    from app.core.db import ping, ensure_tables
    if not await ping():
        logger.warning("Postgres unreachable at startup — audit log writes will fail until it recovers")
    else:
        await ensure_tables()

    asyncio.create_task(_start_spice())

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

    global _spice_proc, _spice_container_id
    if _spice_proc and _spice_proc.returncode is None:
        _spice_proc.terminate()
        try:
            await asyncio.wait_for(_spice_proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            _spice_proc.kill()
        logger.info("SpiceAI process terminated")
    if _spice_container_id:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", "voidrag-spice",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=5)
            logger.info("SpiceAI Docker container removed")
        except Exception:
            pass


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
    from app.api.v1 import chat, ingest, documents, draft, auth, conversations, interact, juris_void
    app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
    app.include_router(ingest.router, prefix="/api/v1", tags=["ingest"])
    app.include_router(documents.router, prefix="/api/v1", tags=["documents"])
    app.include_router(draft.router, prefix="/api/v1", tags=["draft"])
    app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
    app.include_router(conversations.router, prefix="/api/v1", tags=["conversations"])
    app.include_router(interact.router, prefix="/api/v1", tags=["interact"])
    app.include_router(juris_void.router, prefix="/api/v1", tags=["juris-void"])

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8100, reload=True)
