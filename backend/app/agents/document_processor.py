"""Document processing pipeline — text extraction, chunking, embedding.

Ref: TDD-02 Section 2 (chunking + embedding).
     TDD-02 Section 3.2 (process_document_upload Celery task).
     TDD-04 Section 7 (document upload flow).

Pipeline: Download from S3 → extract text → chunk → embed → insert document_chunks.
"""

from __future__ import annotations

import io
import logging
import uuid
from typing import Any

import tiktoken

from app.agents.memory import count_tokens

logger = logging.getLogger(__name__)

# Chunk parameters
CHUNK_SIZE_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 50

_encoder: tiktoken.Encoding = tiktoken.get_encoding("cl100k_base")


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def extract_text(file_bytes: bytes, mime_type: str, filename: str) -> str:
    """Extract plain text from a file based on its MIME type."""
    if mime_type == "application/pdf":
        return _extract_pdf(file_bytes)
    elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _extract_docx(file_bytes)
    elif mime_type in ("text/plain", "text/markdown", "text/csv"):
        return file_bytes.decode("utf-8", errors="replace")
    elif mime_type in ("application/json", "application/x-yaml", "text/yaml"):
        return file_bytes.decode("utf-8", errors="replace")
    else:
        # Fallback: attempt UTF-8 decode
        return file_bytes.decode("utf-8", errors="replace")


def _extract_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF using pymupdf (fitz)."""
    try:
        import fitz  # pymupdf
    except ImportError:
        logger.warning("pymupdf not installed — falling back to raw decode")
        return file_bytes.decode("utf-8", errors="replace")

    text_parts: list[str] = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "\n".join(text_parts)


def _extract_docx(file_bytes: bytes) -> str:
    """Extract text from DOCX using python-docx."""
    try:
        import docx
    except ImportError:
        logger.warning("python-docx not installed — falling back to raw decode")
        return file_bytes.decode("utf-8", errors="replace")

    doc = docx.Document(io.BytesIO(file_bytes))
    return "\n".join(para.text for para in doc.paragraphs)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE_TOKENS,
    overlap: int = CHUNK_OVERLAP_TOKENS,
) -> list[str]:
    """Split text into overlapping token-based chunks.

    Args:
        text: The full text to chunk.
        chunk_size: Target chunk size in tokens (default 512).
        overlap: Number of overlapping tokens between chunks (default 50).

    Returns:
        List of text chunks.
    """
    tokens = _encoder.encode(text)
    if not tokens:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunk_text = _encoder.decode(chunk_tokens)
        chunks.append(chunk_text)

        if end >= len(tokens):
            break
        start += chunk_size - overlap

    return chunks


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


async def compute_embeddings(chunks: list[str]) -> list[list[float]]:
    """Compute embeddings for a list of text chunks.

    Uses Voyage API if configured, otherwise returns placeholder zero vectors.
    The vector dimension is 1024 (matching document_chunks.embedding column).
    """
    from app.config.settings import settings

    if settings.VOYAGE_API_KEY:
        return await _voyage_embed(chunks, settings.VOYAGE_API_KEY)

    # Placeholder: return zero vectors for MVP (real embeddings added when Voyage configured)
    logger.warning("VOYAGE_API_KEY not set — using placeholder embeddings")
    return [[0.0] * 1024 for _ in chunks]


async def _voyage_embed(chunks: list[str], api_key: str) -> list[list[float]]:
    """Compute embeddings via Voyage AI API."""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "voyage-2",
                "input": chunks,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


async def process_document(document_id: str) -> None:
    """Run the full document processing pipeline.

    1. Download from S3
    2. Extract text
    3. Chunk
    4. Embed
    5. Insert document_chunks
    6. Update document status
    """
    from app.core.database import async_session_maker
    from app.core.s3_workspace import download_document
    from app.models.document import Document
    from app.models.document_chunk import DocumentChunk

    async with async_session_maker() as db_session:
        try:
            # Load document
            doc = await db_session.get(Document, document_id)
            if doc is None:
                logger.error("Document %s not found", document_id)
                return

            # Update status to processing
            doc.processing_status = "processing"
            await db_session.flush()

            # Download from S3
            file_bytes = download_document(doc.id, doc.filename)

            # Extract text
            text = extract_text(file_bytes, doc.mime_type, doc.filename)
            if not text.strip():
                doc.processing_status = "ready"
                doc.chunk_count = 0
                await db_session.commit()
                return

            # Chunk
            chunks = chunk_text(text)
            if not chunks:
                doc.processing_status = "ready"
                doc.chunk_count = 0
                await db_session.commit()
                return

            # Embed
            embeddings = await compute_embeddings(chunks)

            # Insert chunks
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                db_chunk = DocumentChunk(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    chunk_index=i,
                    content=chunk,
                    token_count=count_tokens(chunk),
                    embedding=embedding,
                )
                db_session.add(db_chunk)

            # Update document
            doc.chunk_count = len(chunks)
            doc.processing_status = "ready"

            await db_session.commit()

            logger.info(
                "Document %s processed: %d chunks from %s",
                document_id,
                len(chunks),
                doc.filename,
            )

        except Exception:
            await db_session.rollback()
            # Mark as failed
            try:
                doc = await db_session.get(Document, document_id)
                if doc:
                    doc.processing_status = "failed"
                await db_session.commit()
            except Exception:
                logger.exception(
                    "Failed to mark document %s as failed", document_id,
                )
            raise
