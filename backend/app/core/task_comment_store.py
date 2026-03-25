"""
Task comment store — JSON-backed persistence for task comments.
"""
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.models.task_comment import TaskCommentCreate, TaskCommentResponse

logger = logging.getLogger(__name__)


class TaskCommentStore:
    def __init__(self):
        settings = get_settings()
        self._dir = Path(settings.data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "task_comments.json"
        self._save_lock = threading.Lock()
        self._index: dict[str, TaskCommentResponse] = {}
        self._load()

    def _load(self):
        if self._file.exists():
            try:
                raw = json.loads(self._file.read_text(encoding="utf-8"))
                self._index = {
                    k: TaskCommentResponse.model_validate(v) for k, v in raw.items()
                }
            except Exception:
                logger.warning("Failed to load task_comments.json, starting fresh")

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

    def list_for_task(self, task_id: str) -> list[TaskCommentResponse]:
        return sorted(
            [c for c in self._index.values() if c.task_id == task_id],
            key=lambda c: c.created_at,
        )

    def create_comment(self, task_id: str, req: TaskCommentCreate) -> TaskCommentResponse:
        comment = TaskCommentResponse(
            id=str(uuid.uuid4()),
            task_id=task_id,
            author_type=req.author_type,
            author_name=req.author_name,
            body=req.body,
            comment_type=req.comment_type,
            node_id=req.node_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._index[comment.id] = comment
        self._save()
        return comment

    def resolve_comment(self, comment_id: str) -> TaskCommentResponse | None:
        comment = self._index.get(comment_id)
        if not comment:
            return None
        data = comment.model_dump()
        data["resolved"] = True
        updated = TaskCommentResponse.model_validate(data)
        self._index[comment_id] = updated
        self._save()
        return updated

    def delete_comments_for_task(self, task_id: str) -> int:
        to_delete = [
            cid for cid, c in self._index.items()
            if c.task_id == task_id
        ]
        for cid in to_delete:
            del self._index[cid]
        if to_delete:
            self._save()
        return len(to_delete)


_store: TaskCommentStore | None = None


def get_task_comment_store() -> TaskCommentStore:
    global _store
    if _store is None:
        _store = TaskCommentStore()
    return _store
