import json
import threading
from functools import lru_cache
from pathlib import Path
from typing import Optional
import logging

from app.config import get_settings
from app.memory.vector_store import get_vector_store

logger = logging.getLogger(__name__)

PROJECT_COLLECTION = "project_context"


class ProjectContextStore:
    def __init__(self):
        settings = get_settings()
        self.data_dir = Path(settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.context_file = self.data_dir / "project_context.json"
        self.vector_store = get_vector_store()
        self._save_lock = threading.Lock()

    def save_context(self, context: dict):
        with self._save_lock:
            self.context_file.write_text(json.dumps(context, indent=2, ensure_ascii=False), encoding="utf-8")

    def load_context(self) -> Optional[dict]:
        if self.context_file.exists():
            return json.loads(self.context_file.read_text(encoding="utf-8"))
        return None

    def index_text(self, text: str, doc_id: str, metadata: Optional[dict] = None):
        self.vector_store.upsert(
            collection_name=PROJECT_COLLECTION,
            documents=[text],
            ids=[doc_id],
            metadatas=[metadata or {}],
        )

    def search(self, query: str, n_results: int = 5) -> list[dict]:
        return self.vector_store.query(
            collection_name=PROJECT_COLLECTION,
            query_texts=[query],
            n_results=n_results,
        )


@lru_cache(maxsize=1)
def get_project_context_store() -> ProjectContextStore:
    return ProjectContextStore()
