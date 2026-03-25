"""
Label store — JSON-backed persistence for labels.
"""
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.models.label import LabelCreate, LabelResponse

logger = logging.getLogger(__name__)


class LabelStore:
    def __init__(self):
        settings = get_settings()
        self._dir = Path(settings.data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "labels.json"
        self._save_lock = threading.Lock()
        self._index: dict[str, LabelResponse] = {}
        self._load()

    def _load(self):
        if self._file.exists():
            try:
                raw = json.loads(self._file.read_text(encoding="utf-8"))
                self._index = {
                    k: LabelResponse.model_validate(v) for k, v in raw.items()
                }
            except Exception:
                logger.warning("Failed to load labels.json, starting fresh")

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

    def list_labels(self) -> list[LabelResponse]:
        return sorted(self._index.values(), key=lambda l: l.name)

    def get_label(self, label_id: str) -> LabelResponse | None:
        return self._index.get(label_id)

    def create_label(self, req: LabelCreate) -> LabelResponse:
        label = LabelResponse(
            id=str(uuid.uuid4()),
            name=req.name,
            color=req.color,
            group=req.group,
            description=req.description,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._index[label.id] = label
        self._save()
        return label

    def update_label(self, label_id: str, **fields) -> LabelResponse | None:
        label = self._index.get(label_id)
        if not label:
            return None
        data = label.model_dump()
        for k, v in fields.items():
            if v is not None and k in data:
                data[k] = v
        updated = LabelResponse.model_validate(data)
        self._index[label_id] = updated
        self._save()
        return updated

    def delete_label(self, label_id: str) -> bool:
        if label_id not in self._index:
            return False
        del self._index[label_id]
        self._save()
        return True


_store: LabelStore | None = None


def get_label_store() -> LabelStore:
    global _store
    if _store is None:
        _store = LabelStore()
    return _store
