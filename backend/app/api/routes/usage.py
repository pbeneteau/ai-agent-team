from fastapi import APIRouter
from app.core.usage_tracker import get_usage_tracker

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/")
def get_usage():
    """Return token usage and estimated cost breakdown (including daily history)."""
    tracker = get_usage_tracker()
    data = tracker.summary()
    # Expose the full daily breakdown (not in summary() by default)
    with tracker._lock:
        data["daily"] = dict(tracker._data.get("daily", {}))
    return data


@router.post("/reset")
def reset_usage():
    """Reset all usage counters to zero."""
    tracker = get_usage_tracker()
    with tracker._lock:
        tracker._data = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "daily": {},
            "by_model": {},
            "calls": 0,
        }
        tracker._save()
    return {"ok": True}
