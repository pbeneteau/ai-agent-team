import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any, Optional

from app.config.brief import (
    DEFAULT_BRIEF_NOTES_LIMIT,
    PROJECT_BRIEF_COMPLETENESS_WEIGHTS,
    PROJECT_BRIEF_FIELDS,
)
from app.config.document_limits import (
    BRIEF_SUMMARY_DOCUMENT_LIMIT,
    BRIEF_SUMMARY_EXCERPT_CHARS,
)


def _clean_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _truncate(value: str, limit: Optional[int]) -> str:
    if not limit or len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def normalize_project_brief_payload(payload: Mapping[str, Any] | None) -> dict[str, str]:
    data = payload or {}
    return {
        field: _clean_text(data.get(field, ""))
        for field in PROJECT_BRIEF_FIELDS
    }


def has_project_brief_content(payload: Mapping[str, Any] | None) -> bool:
    normalized = normalize_project_brief_payload(payload)
    return any(normalized.values())


def project_brief_fingerprint(payload: Mapping[str, Any] | None) -> str:
    normalized = normalize_project_brief_payload(payload)
    raw = json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_project_brief_completeness(
    payload: Mapping[str, Any] | None,
    *,
    document_count: int = 0,
) -> int:
    normalized = normalize_project_brief_payload(payload)
    score = 0
    for field, weight in PROJECT_BRIEF_COMPLETENESS_WEIGHTS.items():
        if normalized[field]:
            score += weight
    if document_count > 0:
        score += 10
    return min(score, 100)


def diff_project_brief_fields(
    left: Mapping[str, Any] | None,
    right: Mapping[str, Any] | None,
) -> list[str]:
    normalized_left = normalize_project_brief_payload(left)
    normalized_right = normalize_project_brief_payload(right)
    return [
        field
        for field in PROJECT_BRIEF_FIELDS
        if normalized_left[field] != normalized_right[field]
    ]


def render_project_brief_summary(
    payload: Mapping[str, Any] | None,
    *,
    include_meta: bool = False,
    description_limit: Optional[int] = None,
    domain_limit: Optional[int] = None,
    short_term_goal_limit: Optional[int] = None,
    target_audience_limit: Optional[int] = None,
    business_model_limit: Optional[int] = None,
    tech_stack_limit: Optional[int] = None,
    notes_limit: Optional[int] = DEFAULT_BRIEF_NOTES_LIMIT,
) -> str:
    normalized = normalize_project_brief_payload(payload)
    if not any(normalized.values()):
        return "No project context defined yet."

    parts: list[str] = []
    if include_meta:
        revision = payload.get("revision") if payload else None
        published_at = payload.get("published_at") if payload else None
        if revision is not None:
            parts.append(f"Brief revision: {revision}")
        if published_at:
            parts.append(f"Published at: {published_at}")

    parts.extend(
        [
            f"Project: {normalized['name'] or 'Unknown'}",
            f"Description: {_truncate(normalized['description'] or 'No description provided yet.', description_limit)}",
        ]
    )

    optional_labels = [
        ("domain", "Domain"),
        ("short_term_goal", "Current short-term goal"),
        ("target_audience", "Target audience"),
        ("business_model", "Business model"),
        ("tech_stack", "Tech stack"),
    ]
    optional_limits = {
        "domain": domain_limit,
        "short_term_goal": short_term_goal_limit,
        "target_audience": target_audience_limit,
        "business_model": business_model_limit,
        "tech_stack": tech_stack_limit,
    }
    for field, label in optional_labels:
        if normalized[field]:
            parts.append(f"{label}: {_truncate(normalized[field], optional_limits[field])}")
    if normalized["notes"]:
        parts.append(f"Additional context: {_truncate(normalized['notes'], notes_limit)}")
    return "\n".join(parts)


def summarize_documents_for_brief(
    document_store,
    *,
    max_documents: int = BRIEF_SUMMARY_DOCUMENT_LIMIT,
    excerpt_chars: int = BRIEF_SUMMARY_EXCERPT_CHARS,
) -> list[dict[str, str | int]]:
    summaries: list[dict[str, str | int]] = []
    for document in document_store.list_documents()[:max_documents]:
        excerpt = _clean_text(document_store.get_full_text(document["id"], max_chars=excerpt_chars))
        summaries.append(
            {
                "id": str(document["id"]),
                "filename": str(document["filename"]),
                "description": _clean_text(document.get("description", "")),
                "chunk_count": int(document.get("chunk_count", 0)),
                "excerpt": excerpt,
            }
        )
    return summaries
