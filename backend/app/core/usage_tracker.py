"""
Token usage and cost tracker.

Accumulates token counts from every Anthropic API call and calculates
estimated costs based on published pricing. Data is persisted in
data/usage.json and survives restarts.

Pricing (per million tokens) — updated March 2026:
  claude-sonnet-4-5:  $3 input  / $15 output
  claude-opus-4-5:    $5 input  / $25 output
"""
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import get_settings
from app.config.pricing import (
    ANTHROPIC_PRICING_NOTE,
    ANTHROPIC_PRICING_USD_PER_MILLION,
)

logger = logging.getLogger(__name__)

def _price_for(model: str) -> dict[str, float]:
    for key, pricing in ANTHROPIC_PRICING_USD_PER_MILLION.items():
        if key in model:
            return pricing
    return ANTHROPIC_PRICING_USD_PER_MILLION["_default"]


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    p = _price_for(model)
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


def _default_data() -> dict[str, Any]:
    return {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost_usd": 0.0,
        "daily": {},
        "by_model": {},
        "calls": 0,
        "structured_outputs": {"by_flow": {}},
    }


def _default_last_failure() -> dict[str, Any]:
    return {
        "at": None,
        "request_name": None,
        "channel": None,
        "error_kind": "unknown",
        "stop_reason": None,
        "validation_failed": False,
        "message": None,
    }


def _default_flow_entry() -> dict[str, Any]:
    return {
        "calls": 0,
        "successes": 0,
        "failures": 0,
        "channels": {},
        "last_request_name": None,
        "last_seen_at": None,
        "failures_by_kind": {},
        "last_failure": None,
    }


def _flow_name_from_request(request_name: str) -> str:
    text = str(request_name or "").strip()
    if not text:
        return "unknown"
    return text.split(":", 1)[0] or "unknown"


class UsageTracker:
    def __init__(self):
        settings = get_settings()
        self._file = Path(settings.data_dir) / "usage.json"
        self._lock = threading.Lock()
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    return _default_data()
                data.setdefault("daily", {})
                data.setdefault("by_model", {})
                data.setdefault("calls", 0)
                data.setdefault("total_input_tokens", 0)
                data.setdefault("total_output_tokens", 0)
                data.setdefault("total_cost_usd", 0.0)
                structured_outputs = data.setdefault("structured_outputs", {})
                if not isinstance(structured_outputs, dict):
                    structured_outputs = {}
                    data["structured_outputs"] = structured_outputs
                by_flow = structured_outputs.setdefault("by_flow", {})
                if isinstance(by_flow, dict):
                    for flow_name, flow_entry in by_flow.items():
                        if not isinstance(flow_entry, dict):
                            by_flow[flow_name] = _default_flow_entry()
                            continue
                        flow_entry.setdefault("calls", 0)
                        flow_entry.setdefault("successes", 0)
                        flow_entry.setdefault("failures", 0)
                        flow_entry.setdefault("channels", {})
                        flow_entry.setdefault("last_request_name", None)
                        flow_entry.setdefault("last_seen_at", None)
                        flow_entry.setdefault("failures_by_kind", {})
                        last_failure = flow_entry.setdefault("last_failure", None)
                        if isinstance(last_failure, dict):
                            for key, value in _default_last_failure().items():
                                last_failure.setdefault(key, value)
                return data
            except Exception:
                pass
        return _default_data()

    def _save(self):
        self._file.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def log(self, model: str, input_tokens: int, output_tokens: int):
        cost = _cost_usd(model, input_tokens, output_tokens)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        with self._lock:
            self._data["total_input_tokens"] += input_tokens
            self._data["total_output_tokens"] += output_tokens
            self._data["total_cost_usd"] = round(self._data["total_cost_usd"] + cost, 6)
            self._data["calls"] += 1

            # Daily
            day = self._data["daily"].setdefault(today, {"input": 0, "output": 0, "cost": 0.0})
            day["input"] += input_tokens
            day["output"] += output_tokens
            day["cost"] = round(day["cost"] + cost, 6)

            # By model (normalize to base model name)
            model_key = next(
                (
                    key
                    for key in ANTHROPIC_PRICING_USD_PER_MILLION
                    if key in model and key != "_default"
                ),
                model,
            )
            m = self._data["by_model"].setdefault(model_key, {"input": 0, "output": 0, "cost": 0.0})
            m["input"] += input_tokens
            m["output"] += output_tokens
            m["cost"] = round(m["cost"] + cost, 6)

            self._save()

        logger.debug(f"[usage] {model} +{input_tokens}in +{output_tokens}out ${cost:.6f}")

    def log_structured_output(
        self,
        *,
        request_name: str,
        generation_channel: str,
        success: bool,
        failure_kind: str | None = None,
        stop_reason: str | None = None,
        validation_failed: bool = False,
        failure_message: str | None = None,
    ) -> None:
        flow_name = _flow_name_from_request(request_name)
        channel_name = str(generation_channel or "unknown")
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._lock:
            structured_outputs = self._data.setdefault("structured_outputs", {})
            by_flow = structured_outputs.setdefault("by_flow", {})
            flow_entry = by_flow.setdefault(
                flow_name, _default_flow_entry(),
            )
            flow_entry["calls"] += 1
            if success:
                flow_entry["successes"] += 1
            else:
                flow_entry["failures"] += 1
                normalized_kind = str(failure_kind or "unknown")
                flow_entry["failures_by_kind"][normalized_kind] = int(
                    flow_entry["failures_by_kind"].get(normalized_kind, 0)
                ) + 1
                message = str(failure_message or "").strip() or None
                if message and len(message) > 240:
                    message = message[:239].rstrip() + "…"
                flow_entry["last_failure"] = {
                    "at": now_iso,
                    "request_name": request_name,
                    "channel": channel_name,
                    "error_kind": normalized_kind,
                    "stop_reason": str(stop_reason or "").strip() or None,
                    "validation_failed": bool(validation_failed),
                    "message": message,
                }
            flow_entry["channels"][channel_name] = int(flow_entry["channels"].get(channel_name, 0)) + 1
            flow_entry["last_request_name"] = request_name
            flow_entry["last_seen_at"] = now_iso
            self._save()

    def summary(self) -> dict:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._lock:
            today_data = self._data["daily"].get(today, {"input": 0, "output": 0, "cost": 0.0})
            return {
                "today": {
                    "input_tokens":  today_data["input"],
                    "output_tokens": today_data["output"],
                    "cost_usd":      round(today_data["cost"], 4),
                },
                "total": {
                    "input_tokens":  self._data["total_input_tokens"],
                    "output_tokens": self._data["total_output_tokens"],
                    "cost_usd":      round(self._data["total_cost_usd"], 4),
                    "calls":         self._data["calls"],
                },
                "by_model": {
                    model: {
                        "input_tokens":  v["input"],
                        "output_tokens": v["output"],
                        "cost_usd":      round(v["cost"], 4),
                    }
                    for model, v in self._data["by_model"].items()
                },
                "structured_outputs": {
                    "by_flow": dict(self._data.get("structured_outputs", {}).get("by_flow", {}))
                },
                "pricing_note": ANTHROPIC_PRICING_NOTE,
            }


_tracker: Optional[UsageTracker] = None


def get_usage_tracker() -> UsageTracker:
    global _tracker
    if _tracker is None:
        _tracker = UsageTracker()
    return _tracker
