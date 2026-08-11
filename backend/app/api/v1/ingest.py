from fastapi import APIRouter
from app.api.schemas import IngestRequest, IngestResponse, SyncStatusResponse
from app.core.ingestion.pipeline import run_ingestion_pipeline, get_sync_status

router = APIRouter()


@router.post("/ingest/s3", response_model=IngestResponse)
async def ingest_s3(request: IngestRequest):
    result = await run_ingestion_pipeline(
        prefix_filter=request.prefix_filter,
        sync_only=request.sync_only,
    )
    return IngestResponse(**result)


@router.get("/ingest/status", response_model=SyncStatusResponse)
async def ingest_status():
    return SyncStatusResponse(**(await get_sync_status()))
