"""
Task relation store — JSON-backed persistence for inter-task relations.
"""
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.models.task_relation import TaskRelationCreate, TaskRelationResponse

logger = logging.getLogger(__name__)


class TaskRelationStore:
    def __init__(self):
        settings = get_settings()
        self._dir = Path(settings.data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "task_relations.json"
        self._save_lock = threading.Lock()
        self._index: dict[str, TaskRelationResponse] = {}
        self._load()

    def _load(self):
        if self._file.exists():
            try:
                raw = json.loads(self._file.read_text(encoding="utf-8"))
                self._index = {
                    k: TaskRelationResponse.model_validate(v) for k, v in raw.items()
                }
            except Exception:
                logger.warning("Failed to load task_relations.json, starting fresh")

    def _save(self):
        with self._save_lock:
            self._file.write_text(
                json.dumps(
                    {k: v.model_dump() for k, v in self._index.items()},
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    def list_all(self) -> list[TaskRelationResponse]:
        return list(self._index.values())

    def list_for_task(self, task_id: str) -> list[TaskRelationResponse]:
        return [
            r for r in self._index.values()
            if r.source_task_id == task_id or r.target_task_id == task_id
        ]

    def create_relation(self, req: TaskRelationCreate) -> TaskRelationResponse:
        relation = TaskRelationResponse(
            id=str(uuid.uuid4()),
            type=req.type,
            source_task_id=req.source_task_id,
            target_task_id=req.target_task_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._index[relation.id] = relation
        self._save()
        return relation

    def delete_relation(self, relation_id: str) -> bool:
        if relation_id not in self._index:
            return False
        del self._index[relation_id]
        self._save()
        return True

    def delete_relations_for_task(self, task_id: str) -> int:
        to_delete = [
            rid for rid, r in self._index.items()
            if r.source_task_id == task_id or r.target_task_id == task_id
        ]
        for rid in to_delete:
            del self._index[rid]
        if to_delete:
            self._save()
        return len(to_delete)


_store: TaskRelationStore | None = None


def get_task_relation_store() -> TaskRelationStore:
    global _store
    if _store is None:
        _store = TaskRelationStore()
    return _store
