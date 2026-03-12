"""
Document upload and management endpoints.
Uploaded documents are parsed, chunked and indexed in ChromaDB for RAG.
"""
import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, Form, HTTPException

from app.core.knowledge import get_knowledge_audit_service
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
    get_knowledge_audit_service().invalidate_all()
    return meta.to_dict()


@router.get("/{doc_id}/preview")
def get_document_preview(doc_id: str):
    """Return document metadata plus a short extracted preview."""
    store = get_document_store()
    meta = store.get_document(doc_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Document not found")

    max_chars = 2400
    preview_with_guard = store.get_full_text(doc_id, max_chars=max_chars + 1)
    truncated = len(preview_with_guard) > max_chars
    preview = preview_with_guard[:max_chars]

    return {
        **meta.to_dict(),
        "preview": preview,
        "truncated": truncated,
    }


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
    get_knowledge_audit_service().invalidate_all()
    return {"ok": True, "message": "Rebriefing lancé en arrière-plan"}


@router.delete("/{doc_id}")
def delete_document(doc_id: str):
    """Delete a document and remove it from the vector index."""
    store = get_document_store()
    if not store.delete(doc_id):
        raise HTTPException(status_code=404, detail="Document not found")
    get_knowledge_audit_service().invalidate_all()
    return {"ok": True}
