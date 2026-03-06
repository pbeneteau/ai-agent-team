"""
Document upload and management endpoints.
Uploaded documents are parsed, chunked and indexed in ChromaDB for RAG.
"""
import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Form, HTTPException

from app.core.document_store import get_document_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".yaml", ".yml"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


@router.get("/")
def list_documents():
    """List all uploaded documents with metadata."""
    store = get_document_store()
    return store.list_documents()


@router.post("/")
async def upload_document(
    file: UploadFile = File(...),
    description: str = Form(default=""),
):
    """Upload a document. Supported: PDF, DOCX, TXT, MD, CSV, JSON, YAML."""
    from pathlib import Path
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")
    if not raw:
        raise HTTPException(status_code=400, detail="File is empty")

    store = get_document_store()
    meta = store.save_and_index(
        filename=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        raw_bytes=raw,
        description=description,
    )
    return meta.to_dict()


@router.post("/{doc_id}/brief-agents")
async def brief_agents_with_document(doc_id: str, background_tasks: BackgroundTasks):
    """
    Re-generate each agent's project_context.md using the content of this document.
    Runs in the background; returns immediately.
    """
    store = get_document_store()
    if not store.get_document(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")

    from app.core.learning import run_document_rebriefing
    from app.api.websocket_manager import get_manager
    manager = get_manager()
    background_tasks.add_task(run_document_rebriefing, doc_id, manager.broadcast)
    return {"ok": True, "message": "Rebriefing lancé en arrière-plan"}


@router.delete("/{doc_id}")
def delete_document(doc_id: str):
    """Delete a document and remove it from the vector index."""
    store = get_document_store()
    if not store.delete(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return {"ok": True}
