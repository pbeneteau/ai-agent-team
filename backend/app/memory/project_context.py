import logging
import json
import threading
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.core.project_brief import (
    compute_project_brief_completeness,
    diff_project_brief_fields,
    normalize_project_brief_payload,
    project_brief_fingerprint,
    render_project_brief_summary,
)
from app.config import get_settings
from app.models.brief import ProjectBriefSnapshot, ProjectBriefStateResponse, ProjectBriefStatus
from app.memory.vector_store import get_vector_store

logger = logging.getLogger(__name__)

PROJECT_COLLECTION = "project_context"
BRIEF_STATE_VERSION = 1


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ProjectContextStore:
    def __init__(self):
        settings = get_settings()
        self.data_dir = Path(settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.context_file = self.data_dir / "project_context.json"
        self.vector_store = get_vector_store()
        self._save_lock = threading.Lock()

    def _empty_storage_payload(self) -> dict[str, Any]:
        return {
            "schema_version": BRIEF_STATE_VERSION,
            "draft": None,
            "published": None,
        }

    def _read_storage_payload(self) -> dict[str, Any]:
        if not self.context_file.exists():
            return self._empty_storage_payload()

        payload = json.loads(self.context_file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return self._empty_storage_payload()

        if "draft" in payload or "published" in payload:
            return {
                "schema_version": int(payload.get("schema_version") or BRIEF_STATE_VERSION),
                "draft": payload.get("draft"),
                "published": payload.get("published"),
            }

        normalized = normalize_project_brief_payload(payload)
        if not any(normalized.values()) and not payload.get("revision") and not payload.get("updated_at"):
            return self._empty_storage_payload()

        revision = int(payload.get("revision") or 1)
        updated_at = str(payload.get("updated_at") or payload.get("published_at") or _now_iso())
        published_at = str(payload.get("published_at") or updated_at)
        return {
            "schema_version": BRIEF_STATE_VERSION,
            "draft": {
                "revision": revision,
                "updated_at": updated_at,
                **normalized,
            },
            "published": {
                "revision": revision,
                "updated_at": updated_at,
                "published_at": published_at,
                **normalized,
            },
        }

    def _write_storage_payload(self, payload: dict[str, Any]) -> None:
        self.context_file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _snapshot_from_raw(
        self,
        raw: dict[str, Any] | None,
        *,
        status: ProjectBriefStatus,
    ) -> Optional[ProjectBriefSnapshot]:
        if not raw:
            return None
        normalized = normalize_project_brief_payload(raw)
        if not any(normalized.values()) and not raw.get("updated_at") and not raw.get("published_at"):
            return None
        updated_at = str(raw.get("updated_at") or raw.get("published_at") or _now_iso())
        published_at = raw.get("published_at")
        return ProjectBriefSnapshot(
            revision=int(raw.get("revision") or 1),
            status=status,
            updated_at=updated_at,
            published_at=str(published_at) if published_at else None,
            brief_fingerprint=project_brief_fingerprint(normalized),
            completeness_score=compute_project_brief_completeness(normalized),
            **normalized,
        )

    def _matches_payload(self, normalized: dict[str, str], raw: dict[str, Any] | None) -> bool:
        if not raw:
            return False
        return normalize_project_brief_payload(raw) == normalized

    def _next_revision(self, payload: dict[str, Any]) -> int:
        revisions = [
            int(item.get("revision") or 0)
            for item in (payload.get("draft"), payload.get("published"))
            if isinstance(item, dict)
        ]
        return (max(revisions) if revisions else 0) + 1

    def _sync_active_context_index(self) -> None:
        active = self.get_active_brief()
        if not active:
            return
        self.index_text(
            text=render_project_brief_summary(active.model_dump(mode="json"), include_meta=True),
            doc_id="project_context_active",
            metadata={
                "type": "project_context",
                "revision": active.revision,
                "status": active.status.value,
            },
        )

    def load_state(self) -> ProjectBriefStateResponse:
        payload = self._read_storage_payload()
        draft = self._snapshot_from_raw(payload.get("draft"), status=ProjectBriefStatus.DRAFT)
        published = self._snapshot_from_raw(payload.get("published"), status=ProjectBriefStatus.PUBLISHED)
        active = published or draft
        has_unpublished_changes = bool(
            draft
            and published
            and diff_project_brief_fields(draft.model_dump(mode="json"), published.model_dump(mode="json"))
        )
        return ProjectBriefStateResponse(
            draft=draft,
            published=published,
            active=active,
            has_unpublished_changes=has_unpublished_changes,
        )

    def get_active_brief(self) -> Optional[ProjectBriefSnapshot]:
        return self.load_state().active

    def save_draft(self, context: dict) -> ProjectBriefStateResponse:
        normalized = normalize_project_brief_payload(context)
        now = _now_iso()
        with self._save_lock:
            payload = self._read_storage_payload()
            if self._matches_payload(normalized, payload.get("draft")):
                revision = int((payload.get("draft") or {}).get("revision") or 1)
            elif self._matches_payload(normalized, payload.get("published")):
                revision = int((payload.get("published") or {}).get("revision") or 1)
            else:
                revision = self._next_revision(payload)
            payload["draft"] = {
                "revision": revision,
                "updated_at": now,
                **normalized,
            }
            self._write_storage_payload(payload)
        self._sync_active_context_index()
        return self.load_state()

    def publish_context(self, context: Optional[dict] = None) -> tuple[ProjectBriefStateResponse, bool]:
        now = _now_iso()
        with self._save_lock:
            payload = self._read_storage_payload()
            if context is not None:
                normalized = normalize_project_brief_payload(context)
                if self._matches_payload(normalized, payload.get("draft")):
                    revision = int((payload.get("draft") or {}).get("revision") or 1)
                elif self._matches_payload(normalized, payload.get("published")):
                    revision = int((payload.get("published") or {}).get("revision") or 1)
                else:
                    revision = self._next_revision(payload)
                payload["draft"] = {
                    "revision": revision,
                    "updated_at": now,
                    **normalized,
                }

            draft = payload.get("draft")
            if not isinstance(draft, dict):
                raise ValueError("No draft context available to publish")

            normalized_draft = normalize_project_brief_payload(draft)
            published = payload.get("published")
            changed = not self._matches_payload(normalized_draft, published)
            revision = int(draft.get("revision") or (self._next_revision(payload) if changed else 1))
            payload["draft"] = {
                "revision": revision,
                "updated_at": now,
                **normalized_draft,
            }
            if changed:
                payload["published"] = {
                    "revision": revision,
                    "updated_at": now,
                    "published_at": now,
                    **normalized_draft,
                }
            self._write_storage_payload(payload)
        self._sync_active_context_index()
        return self.load_state(), changed

    def save_context(self, context: dict):
        state, _changed = self.publish_context(context)
        return state

    def load_context(self) -> Optional[dict]:
        active = self.get_active_brief()
        if not active:
            return None
        return active.model_dump(mode="json")

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
