import re

import chromadb
from chromadb.config import Settings as ChromaSettings
from functools import lru_cache
from typing import Optional
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(self):
        settings = get_settings()
        self._client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    def get_or_create_collection(self, name: str):
        return self._client.get_or_create_collection(name=name)

    def upsert(self, collection_name: str, documents: list[str], ids: list[str], metadatas: Optional[list[dict]] = None):
        collection = self.get_or_create_collection(collection_name)
        collection.upsert(documents=documents, ids=ids, metadatas=metadatas or [{}] * len(documents))

    def query(self, collection_name: str, query_texts: list[str], n_results: int = 5) -> list[dict]:
        try:
            collection = self.get_or_create_collection(collection_name)
            results = collection.query(query_texts=query_texts, n_results=n_results)
            output = []
            for i, doc_list in enumerate(results.get("documents", [])):
                for j, doc in enumerate(doc_list):
                    output.append({
                        "document": doc,
                        "id": results["ids"][i][j],
                        "metadata": results.get("metadatas", [[]])[i][j] if results.get("metadatas") else {},
                        "distance": results.get("distances", [[]])[i][j] if results.get("distances") else None,
                    })
            return output
        except Exception as e:
            logger.error(f"Vector query error: {e}")
            return []

    def upsert_chunked(
        self,
        collection_name: str,
        content: str,
        base_id: str,
        metadata: Optional[dict] = None,
        chunk_delimiter: str = "## ",
    ) -> int:
        """Split content by Markdown section headers and upsert each chunk."""
        # Split by ## headers, keeping the header with the chunk
        raw_chunks = re.split(r"(?=^## )", content, flags=re.MULTILINE)
        chunks = [c.strip() for c in raw_chunks if c.strip() and len(c.strip()) > 20]
        if not chunks:
            # Fall back to treating the whole content as one chunk
            chunks = [content.strip()]

        ids = [f"{base_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [{**(metadata or {}), "chunk_index": i} for i in range(len(chunks))]
        self.upsert(collection_name, documents=chunks, ids=ids, metadatas=metadatas)
        return len(chunks)

    def delete_by_prefix(self, collection_name: str, id_prefix: str) -> None:
        """Delete all documents whose ID starts with the given prefix."""
        try:
            collection = self.get_or_create_collection(collection_name)
            # ChromaDB doesn't support prefix queries natively, so we get all and filter
            all_ids = collection.get()["ids"]
            matching = [doc_id for doc_id in all_ids if doc_id.startswith(id_prefix)]
            if matching:
                collection.delete(ids=matching)
        except Exception as e:
            logger.warning(f"Vector delete_by_prefix error in {collection_name}: {e}")

    def delete(self, collection_name: str, ids: list[str]):
        """Delete specific documents by ID from a collection."""
        try:
            collection = self.get_or_create_collection(collection_name)
            collection.delete(ids=ids)
        except Exception as e:
            logger.warning(f"Vector delete error in {collection_name}: {e}")

    def delete_collection(self, name: str):
        try:
            self._client.delete_collection(name)
        except Exception:
            logger.debug("delete_collection '%s': collection not found or already deleted", name)


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    return VectorStore()
