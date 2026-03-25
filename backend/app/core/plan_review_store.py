import json
from pathlib import Path
from threading import Lock

from app.config.settings import get_settings
from app.models.plan import (
    PlanReviewSnapshot,
    PlanReviewWorkflow,
    PlanSessionState,
    PlanState,
)


class PlanReviewStore:
    def __init__(self) -> None:
        settings = get_settings()
        data_dir = Path(settings.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        self._file = data_dir / "plan_reviews.json"
        self._lock = Lock()
        self._reviews: dict[str, PlanReviewSnapshot] = {}
        self._load()

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            raw = json.loads(self._file.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(raw, list):
            return
        for item in raw:
            try:
                snapshot = PlanReviewSnapshot.model_validate(item)
            except Exception:
                continue
            self._reviews[snapshot.id] = snapshot

    def _save(self) -> None:
        ordered = sorted(
            self._reviews.values(),
            key=lambda snapshot: snapshot.updated_at,
            reverse=True,
        )[:50]
        self._reviews = {snapshot.id: snapshot for snapshot in ordered}
        self._file.write_text(
            json.dumps([snapshot.model_dump(mode="json") for snapshot in ordered], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def list(self) -> list[PlanReviewSnapshot]:
        with self._lock:
            return sorted(
                self._reviews.values(),
                key=lambda snapshot: snapshot.updated_at,
                reverse=True,
            )

    def get(self, review_id: str) -> PlanReviewSnapshot | None:
        with self._lock:
            return self._reviews.get(review_id)

    def upsert_from_session(
        self,
        *,
        workflow: PlanReviewWorkflow,
        session: PlanSessionState,
        updated_at: str,
        error: str | None,
    ) -> PlanReviewSnapshot | None:
        if session.kind is None or session.draft is None:
            return None
        if session.state not in {PlanState.AWAITING_CONFIRMATION, PlanState.FAILED}:
            return None
        snapshot = PlanReviewSnapshot(
            id=session.draft.id,
            session_id=session.session_id,
            workflow=workflow,
            kind=session.kind,
            state=session.state,
            draft=session.draft,
            updated_at=updated_at,
            error=error,
            session=session,
        )
        with self._lock:
            self._reviews[snapshot.id] = snapshot
            self._save()
        return snapshot

    def remove(self, review_id: str) -> None:
        with self._lock:
            if review_id not in self._reviews:
                return
            self._reviews.pop(review_id, None)
            self._save()


_store: PlanReviewStore | None = None


def get_plan_review_store() -> PlanReviewStore:
    global _store
    if _store is None:
        _store = PlanReviewStore()
    return _store


def restore_plan_session(review_id: str) -> tuple[PlanReviewWorkflow, PlanSessionState] | None:
    snapshot = get_plan_review_store().get(review_id)
    if snapshot is None:
        return None
    return snapshot.workflow, snapshot.session
