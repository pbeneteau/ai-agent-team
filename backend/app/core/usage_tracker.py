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
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

# Pricing in USD per million tokens
PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-5": {"input": 3.0,  "output": 15.0},
    "claude-opus-4-5":   {"input": 5.0,  "output": 25.0},
    # Fallback for unknown models — use sonnet pricing
    "_default":          {"input": 3.0,  "output": 15.0},
}


def _price_for(model: str) -> dict[str, float]:
    for key, pricing in PRICING.items():
        if key in model:
            return pricing
    return PRICING["_default"]


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    p = _price_for(model)
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


class UsageTracker:
    def __init__(self):
        settings = get_settings()
        self._file = Path(settings.data_dir) / "usage.json"
        self._lock = threading.Lock()
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self._file.exists():
            try:
                return json.loads(self._file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "daily": {},      # {"2026-03-06": {"input": N, "output": N, "cost": X}}
            "by_model": {},   # {"claude-sonnet-4-5": {"input": N, "output": N, "cost": X}}
            "calls": 0,
        }

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
            model_key = next((k for k in PRICING if k in model and k != "_default"), model)
            m = self._data["by_model"].setdefault(model_key, {"input": 0, "output": 0, "cost": 0.0})
            m["input"] += input_tokens
            m["output"] += output_tokens
            m["cost"] = round(m["cost"] + cost, 6)

            self._save()

        logger.debug(f"[usage] {model} +{input_tokens}in +{output_tokens}out ${cost:.6f}")

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
                "pricing_note": "Estimated cost based on published Anthropic pricing (March 2026). Excludes prompt caching discounts.",
            }


_tracker: Optional[UsageTracker] = None


def get_usage_tracker() -> UsageTracker:
    global _tracker
    if _tracker is None:
        _tracker = UsageTracker()
    return _tracker
