from fastapi import APIRouter
from app.api.schemas import IngestRequest, IngestResponse, SyncStatusResponse
from app.core.ingestion.pipeline import start_background_ingestion, get_sync_status, get_sync_state
from app.core.ingestion.scheduler import start_auto_sync, stop_auto_sync, get_sync_state as get_scheduler_state

router = APIRouter()


@router.post("/ingest/s3", response_model=IngestResponse)
async def ingest_s3(request: IngestRequest):
    # Fire-and-forget: ingestion runs to completion as a detached background
    # task, not inside this request's response cycle — a large batch used to
    # run bound by the request, which meant it always blew past the
    # frontend's HTTP client timeout for anything but a small sync. Progress
    # is tracked entirely via /ingest/status polling from here on.
    started = await start_background_ingestion(
        prefix_filter=request.prefix_filter,
        sync_only=request.sync_only,
    )
    state = get_sync_state()
    return IngestResponse(
        ingested=0,
        failed=0,
        skipped=0,
        total_keys=state.get("total", 0),
        running=True,
        processed=state.get("processed", 0),
        total=state.get("total", 0),
        current_key=state.get("current_key", ""),
        already_running=not started,
    )


@router.get("/ingest/status", response_model=SyncStatusResponse)
async def ingest_status():
    return SyncStatusResponse(**(await get_sync_status()))


@router.post("/ingest/s3/schedule")
async def schedule_ingest():
    start_auto_sync()
    return {"scheduled": True, "state": get_scheduler_state()}


@router.post("/ingest/s3/unschedule")
async def unschedule_ingest():
    stop_auto_sync()
    return {"scheduled": False, "state": get_scheduler_state()}


@router.get("/ingest/s3/status")
async def scheduler_status():
    return get_scheduler_state()
