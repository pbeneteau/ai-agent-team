"""
Document store — handles upload, parsing, storage and RAG indexing of user documents.

Supported formats: PDF, DOCX, TXT, MD, CSV
Documents are stored in data/documents/ and indexed in ChromaDB for semantic search.
"""
import json
import logging
import threading
import uuid
from datetime import datetime, UTC
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.memory.vector_store import get_vector_store

logger = logging.getLogger(__name__)

DOCUMENTS_COLLECTION = "user_documents"
CHUNK_SIZE = 1000       # chars per ChromaDB chunk
CHUNK_OVERLAP = 100     # overlap between consecutive chunks


class DocumentMeta:
    def __init__(self, doc_id: str, filename: str, content_type: str,
                 size_bytes: int, created_at: str, chunk_count: int = 0,
                 description: str = ""):
        self.id = doc_id
        self.filename = filename
        self.content_type = content_type
        self.size_bytes = size_bytes
        self.created_at = created_at
        self.chunk_count = chunk_count
        self.description = description

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at,
            "chunk_count": self.chunk_count,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DocumentMeta":
        # 'id' in the stored dict maps to the 'doc_id' constructor parameter
        data = dict(d)
        data["doc_id"] = data.pop("id", data.pop("doc_id", ""))
        return cls(**data)


class DocumentStore:
    def __init__(self):
        settings = get_settings()
        self.docs_dir = Path(settings.data_dir) / "documents"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = Path(settings.data_dir) / "documents.json"
        self.vector_store = get_vector_store()
        self._index: dict[str, DocumentMeta] = {}
        self._save_lock = threading.Lock()
        self._load_index()

    def _load_index(self):
        if self.index_file.exists():
            raw = json.loads(self.index_file.read_text(encoding="utf-8"))
            self._index = {k: DocumentMeta.from_dict(v) for k, v in raw.items()}

    def _save_index(self):
        with self._save_lock:
            self.index_file.write_text(
                json.dumps({k: v.to_dict() for k, v in self._index.items()},
                           indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def list_documents(self) -> list[dict]:
        return [m.to_dict() for m in sorted(
            self._index.values(), key=lambda d: d.created_at, reverse=True
        )]

    def get_document(self, doc_id: str) -> Optional[DocumentMeta]:
        return self._index.get(doc_id)

    def save_and_index(self, filename: str, content_type: str, raw_bytes: bytes,
                       description: str = "") -> DocumentMeta:
        """Save file to disk, extract text, chunk and index in ChromaDB."""
        doc_id = str(uuid.uuid4())
        ext = Path(filename).suffix.lower()
        file_path = self.docs_dir / f"{doc_id}{ext}"
        file_path.write_bytes(raw_bytes)

        text = self._extract_text(file_path, ext, raw_bytes)
        chunks = self._chunk_text(text)

        if chunks:
            self.vector_store.upsert(
                collection_name=DOCUMENTS_COLLECTION,
                documents=chunks,
                ids=[f"{doc_id}_chunk_{i}" for i in range(len(chunks))],
                metadatas=[{
                    "doc_id": doc_id,
                    "filename": filename,
                    "chunk_index": i,
                    "description": description,
                } for i in range(len(chunks))],
            )

        meta = DocumentMeta(
            doc_id=doc_id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(raw_bytes),
            created_at=datetime.now(UTC).isoformat(),
            chunk_count=len(chunks),
            description=description,
        )
        self._index[doc_id] = meta
        self._save_index()
        logger.info(f"Document indexed: {filename} ({len(chunks)} chunks)")
        return meta

    def delete(self, doc_id: str) -> bool:
        meta = self._index.get(doc_id)
        if not meta:
            return False

        # Remove ChromaDB chunks
        chunk_ids = [f"{doc_id}_chunk_{i}" for i in range(meta.chunk_count)]
        if chunk_ids:
            try:
                self.vector_store.delete(DOCUMENTS_COLLECTION, chunk_ids)
            except Exception as e:
                logger.warning(f"Could not remove chunks from ChromaDB: {e}")

        # Remove file
        for f in self.docs_dir.glob(f"{doc_id}.*"):
            f.unlink(missing_ok=True)

        del self._index[doc_id]
        self._save_index()
        logger.info(f"Document deleted: {doc_id}")
        return True

    def search(self, query: str, n_results: int = 3) -> list[dict]:
        """Return the most relevant document chunks for a given query."""
        try:
            results = self.vector_store.query(
                collection_name=DOCUMENTS_COLLECTION,
                query_texts=[query],
                n_results=n_results,
            )
            return results
        except Exception as e:
            logger.warning(f"Document search failed: {e}")
            return []

    def format_for_context(self, query: str, max_chars: int = 1500) -> str:
        """Return a formatted string of relevant document excerpts for injection into prompts."""
        chunks = self.search(query, n_results=4)
        if not chunks:
            return ""

        parts = ["## Relevant documents\n"]
        total = 0
        seen_docs: set[str] = set()

        for chunk in chunks:
            doc_id = chunk.get("metadata", {}).get("doc_id", "")
            filename = chunk.get("metadata", {}).get("filename", "document")
            text = chunk.get("document", "")

            if not text:
                continue

            header = f"**{filename}**" if doc_id not in seen_docs else ""
            seen_docs.add(doc_id)
            entry = f"{header}\n{text}\n" if header else f"{text}\n"

            if total + len(entry) > max_chars:
                break
            parts.append(entry)
            total += len(entry)

        return "\n".join(parts) if len(parts) > 1 else ""

    # --- Text extraction ---

    def _extract_text(self, file_path: Path, ext: str, raw_bytes: bytes) -> str:
        try:
            if ext == ".pdf":
                return self._extract_pdf(file_path)
            if ext == ".docx":
                return self._extract_docx(file_path)
            if ext in (".txt", ".md", ".csv", ".json", ".yaml", ".yml"):
                return raw_bytes.decode("utf-8", errors="replace")
            # Fallback: try UTF-8
            return raw_bytes.decode("utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Text extraction failed for {file_path.name}: {e}")
            return ""

    def _extract_pdf(self, path: Path) -> str:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)

    def _extract_docx(self, path: Path) -> str:
        from docx import Document
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    def get_full_text(self, doc_id: str, max_chars: int = 20000) -> str:
        """Return the full extracted text of a document (capped at max_chars)."""
        meta = self._index.get(doc_id)
        if not meta:
            return ""
        matches = list(self.docs_dir.glob(f"{doc_id}.*"))
        if not matches:
            return ""
        path = matches[0]
        ext = path.suffix.lower()
        try:
            raw = path.read_bytes()
            text = self._extract_text(path, ext, raw)
            return text[:max_chars]
        except Exception as e:
            logger.error(f"get_full_text failed for {doc_id}: {e}")
            return ""

    # --- Chunking ---

    def _chunk_text(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        chunks = []
        start = 0
        while start < len(text):
            end = start + CHUNK_SIZE
            chunks.append(text[start:end])
            start += CHUNK_SIZE - CHUNK_OVERLAP
        return chunks


@lru_cache(maxsize=1)
def get_document_store() -> DocumentStore:
    return DocumentStore()
