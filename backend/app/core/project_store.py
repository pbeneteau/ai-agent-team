"""
Project store — JSON-backed persistence for projects.
"""
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.models.project import ProjectCreate, ProjectResponse, ProjectStatus

logger = logging.getLogger(__name__)


class ProjectStore:
    def __init__(self):
        settings = get_settings()
        self._dir = Path(settings.data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "projects.json"
        self._save_lock = threading.Lock()
        self._index: dict[str, ProjectResponse] = {}
        self._identifier_counter: int = 0
        self._load()

    def _load(self):
        if self._file.exists():
            try:
                raw = json.loads(self._file.read_text(encoding="utf-8"))
                data = raw.get("projects", {}) if isinstance(raw, dict) else {}
                self._index = {
                    k: ProjectResponse.model_validate(v) for k, v in data.items()
                }
                self._identifier_counter = raw.get("_identifier_counter", len(self._index))
            except Exception:
                logger.warning("Failed to load projects.json, starting fresh")

    def _save(self):
        with self._save_lock:
            payload = {
                "_identifier_counter": self._identifier_counter,
                "projects": {k: v.model_dump() for k, v in self._index.items()},
            }
            self._file.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def list_projects(self) -> list[ProjectResponse]:
        return sorted(self._index.values(), key=lambda p: p.sort_order)

    def get_project(self, project_id: str) -> ProjectResponse | None:
        return self._index.get(project_id)

    def create_project(self, req: ProjectCreate) -> ProjectResponse:
        now = datetime.now(timezone.utc).isoformat()
        self._identifier_counter += 1
        project = ProjectResponse(
            id=str(uuid.uuid4()),
            identifier=f"PRJ-{self._identifier_counter}",
            name=req.name,
            description=req.description,
            color=req.color,
            icon=req.icon,
            default_team_id=req.default_team_id,
            target_date=req.target_date,
            sort_order=float(self._identifier_counter),
            created_at=now,
            updated_at=now,
        )
        self._index[project.id] = project
        self._save()
        return project

    def update_project(self, project_id: str, **fields) -> ProjectResponse | None:
        project = self._index.get(project_id)
        if not project:
            return None
        data = project.model_dump()
        for k, v in fields.items():
            if v is not None and k in data:
                data[k] = v
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated = ProjectResponse.model_validate(data)
        self._index[project_id] = updated
        self._save()
        return updated

    def delete_project(self, project_id: str) -> bool:
        if project_id not in self._index:
            return False
        del self._index[project_id]
        self._save()
        return True


_store: ProjectStore | None = None


def get_project_store() -> ProjectStore:
    global _store
    if _store is None:
        _store = ProjectStore()
    return _store
