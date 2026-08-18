from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.schemas import (
    InteractAttachDeviceResponse,
    InteractDocumentOut,
    InteractDocumentsOut,
    InteractReuseRequest,
)
from app.config.settings import settings
from app.core.retrieval import session_store
from app.core.retrieval.session_store import InvalidSessionId

router = APIRouter()


def _check_doc_limit(session_id: str) -> None:
    if len(session_store.list_documents(session_id)) >= settings.INTERACT_MAX_DOCS_PER_SESSION:
        raise HTTPException(
            status_code=400,
            detail=f"Session already has the maximum of {settings.INTERACT_MAX_DOCS_PER_SESSION} documents",
        )


@router.post("/interact/documents", response_model=InteractAttachDeviceResponse)
async def attach_document(session_id: str = Form(...), file: UploadFile = File(...)):
    data = await file.read()
    max_bytes = settings.INTERACT_MAX_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.INTERACT_MAX_UPLOAD_MB}MB upload limit",
        )

    try:
        _check_doc_limit(session_id)
        record = session_store.add_document(session_id, file.filename or "upload", data)
    except InvalidSessionId:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    return InteractAttachDeviceResponse(session_id=session_id, document=InteractDocumentOut(**record))


@router.get("/interact/documents", response_model=InteractDocumentsOut)
async def list_documents(session_id: str):
    try:
        docs = session_store.list_documents(session_id)
    except InvalidSessionId:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    return InteractDocumentsOut(
        session_id=session_id,
        documents=[InteractDocumentOut(**d) for d in docs],
    )


@router.delete("/interact/documents/{file_hash}")
async def remove_document(session_id: str, file_hash: str):
    try:
        removed = session_store.remove_document(session_id, file_hash)
    except InvalidSessionId:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    if not removed:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"removed": True}


@router.post("/interact/documents/reuse", response_model=InteractAttachDeviceResponse)
async def reuse_document(body: InteractReuseRequest):
    try:
        _check_doc_limit(body.session_id)
        record = session_store.copy_document(body.source_session_id, body.session_id, body.file_hash)
    except InvalidSessionId:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    if record is None:
        raise HTTPException(status_code=404, detail="Source document not found")

    return InteractAttachDeviceResponse(session_id=body.session_id, document=InteractDocumentOut(**record))
