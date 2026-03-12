from fastapi import APIRouter
from app.core.git_provider_store import get_git_provider_store
from app.core.mcp_connection_store import get_mcp_connection_store
from app.core.usage_tracker import _default_data, get_usage_tracker

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/")
def get_usage():
    """Return token usage and estimated cost breakdown (including daily history)."""
    tracker = get_usage_tracker()
    data = tracker.summary()
    # Expose the full daily breakdown (not in summary() by default)
    with tracker._lock:
        data["daily"] = dict(tracker._data.get("daily", {}))
    data["mcp"] = get_mcp_connection_store().summarize_usage().model_dump(mode="json")
    data["git_providers"] = get_git_provider_store().summarize_usage().model_dump(mode="json")
    return data


@router.post("/reset")
def reset_usage():
    """Reset all usage counters to zero."""
    tracker = get_usage_tracker()
    with tracker._lock:
        tracker._data = _default_data()
        tracker._save()
    return {"ok": True}
