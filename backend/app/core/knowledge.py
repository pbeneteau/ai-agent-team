import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from anthropic import Anthropic
from pydantic import BaseModel, Field

from app.config import get_settings
from app.config.knowledge import (
    KNOWLEDGE_AUDIT_DOCUMENT_LIMIT,
    KNOWLEDGE_AUDIT_SKILL_LIMIT,
    KNOWLEDGE_EVIDENCE_EXCERPT_MAX_CHARS,
    KNOWLEDGE_MAX_RECOMMENDATIONS,
    KNOWLEDGE_MAX_SUMMARIES,
    KNOWLEDGE_MISSING_ITEM_MAX_CHARS,
    KNOWLEDGE_RECOMMENDATION_REASON_MAX_CHARS,
    KNOWLEDGE_RECOMMENDATION_SUMMARY_MAX_CHARS,
    KNOWLEDGE_RECOMMENDATION_TITLE_MAX_CHARS,
    KNOWLEDGE_SOURCE_LABEL_MAX_CHARS,
    KNOWLEDGE_SOURCE_MAX_CHARS,
    KNOWLEDGE_SOURCE_TYPE_MAX_CHARS,
    KNOWLEDGE_SUGGESTED_TOPIC_MAX_CHARS,
    KNOWLEDGE_SUMMARY_MAX_CHARS,
)
from app.config.prompts import KNOWLEDGE_AUDIT_PROMPT, KNOWLEDGE_AUDIT_SCHEMA_HINT
from app.config.token_budgets import (
    KNOWLEDGE_AGENT_SECTION_LIMIT,
    KNOWLEDGE_AUDIT_MAX_TOKENS,
    KNOWLEDGE_AUDIT_PROMPT_BUDGET,
    KNOWLEDGE_AUDIT_SKILL_CHARS,
    KNOWLEDGE_DOCUMENTS_SECTION_LIMIT,
    KNOWLEDGE_PROJECT_CONTEXT_SECTION_LIMIT,
    KNOWLEDGE_SKILLS_SECTION_LIMIT,
)
from app.core.agent_factory import get_agent_factory
from app.core.document_store import get_document_store
from app.core.project_brief import render_project_brief_summary, summarize_documents_for_brief
from app.core.structured_json import StructuredJsonError, request_native_structured_json
from app.core.workspace import get_workspace_manager
from app.models.agent import AgentConfig
from app.models.knowledge import (
    AgentKnowledgeReadiness,
    GlobalKnowledgeGap,
    GlobalKnowledgeReadiness,
    KnowledgeGenerationSource,
    KnowledgeReadinessLevel,
    KnowledgeRecommendation,
    KnowledgeRecommendationAction,
    KnowledgeRecommendationEvidence,
    KnowledgeRecommendationPriority,
    KnowledgeRecommendationStatus,
    KnowledgeRecommendationType,
)
from app.memory.project_context import get_project_context_store

logger = logging.getLogger(__name__)

_KnowledgeAuditSummary = Annotated[str, Field(max_length=KNOWLEDGE_SUMMARY_MAX_CHARS)]
_KnowledgeAuditMissingItem = Annotated[str, Field(max_length=KNOWLEDGE_MISSING_ITEM_MAX_CHARS)]
_KnowledgeAuditTitle = Annotated[str, Field(max_length=KNOWLEDGE_RECOMMENDATION_TITLE_MAX_CHARS)]
_KnowledgeAuditRecommendationSummary = Annotated[
    str, Field(max_length=KNOWLEDGE_RECOMMENDATION_SUMMARY_MAX_CHARS)
]
_KnowledgeAuditReason = Annotated[str, Field(max_length=KNOWLEDGE_RECOMMENDATION_REASON_MAX_CHARS)]
_KnowledgeAuditSourceLabel = Annotated[str, Field(max_length=KNOWLEDGE_SOURCE_LABEL_MAX_CHARS)]
_KnowledgeAuditSourceType = Annotated[str, Field(max_length=KNOWLEDGE_SOURCE_TYPE_MAX_CHARS)]
_KnowledgeAuditSource = Annotated[str, Field(max_length=KNOWLEDGE_SOURCE_MAX_CHARS)]
_KnowledgeAuditSuggestedTopic = Annotated[str, Field(max_length=KNOWLEDGE_SUGGESTED_TOPIC_MAX_CHARS)]
_KnowledgeAuditExcerpt = Annotated[str, Field(max_length=KNOWLEDGE_EVIDENCE_EXCERPT_MAX_CHARS)]

# Temporary compatibility aliases for tests and incremental migration.
_PROMPT_BUDGET = KNOWLEDGE_AUDIT_PROMPT_BUDGET


class _KnowledgeAuditPayload(BaseModel):
    readiness_level: KnowledgeReadinessLevel
    readiness_score: int = Field(ge=0, le=100)
    summary: _KnowledgeAuditSummary
    missing_knowledge_summary: list[_KnowledgeAuditMissingItem] = Field(
        default_factory=list,
        max_length=KNOWLEDGE_MAX_SUMMARIES,
    )
    recommendations: list["_KnowledgeAuditRecommendationPayload"] = Field(
        default_factory=list,
        max_length=KNOWLEDGE_MAX_RECOMMENDATIONS,
    )


class _KnowledgeAuditEvidencePayload(BaseModel):
    source_label: _KnowledgeAuditSourceLabel
    source_type: _KnowledgeAuditSourceType
    excerpt: _KnowledgeAuditExcerpt


class _KnowledgeAuditRecommendationPayload(BaseModel):
    title: _KnowledgeAuditTitle
    summary: _KnowledgeAuditRecommendationSummary
    reason: _KnowledgeAuditReason
    priority: KnowledgeRecommendationPriority
    knowledge_type: KnowledgeRecommendationType
    action_type: KnowledgeRecommendationAction
    can_be_found_on_web: bool
    recommended_source: _KnowledgeAuditSource
    suggested_topic: _KnowledgeAuditSuggestedTopic | None = None
    evidence: list[_KnowledgeAuditEvidencePayload] = Field(default_factory=list, max_length=1)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "knowledge-gap"


def _truncate(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _normalize_text_list(items: object, *, limit: int, item_limit: int) -> list[str]:
    if not isinstance(items, list):
        return []
    values: list[str] = []
    seen: set[str] = set()
    for raw in items:
        text = _truncate(str(raw or ""), item_limit)
        key = text.lower()
        if len(text) < 8 or key in seen:
            continue
        seen.add(key)
        values.append(text)
        if len(values) >= limit:
            break
    return values


def _format_audit_documents(items: list[dict]) -> str:
    if not items:
        return "No document summaries available."
    lines: list[str] = []
    for item in items[:KNOWLEDGE_AUDIT_DOCUMENT_LIMIT]:
        filename = _truncate(str(item.get("filename", "")).strip() or "unknown", 60)
        description = _truncate(str(item.get("description", "")).strip(), 100)
        excerpt = _truncate(str(item.get("excerpt", "")).strip(), 140)
        chunk_count = int(item.get("chunk_count", 0) or 0)
        lines.append(
            f"- {filename} | chunks={chunk_count} | description={description or 'n/a'} | excerpt={excerpt or 'n/a'}"
        )
    return "\n".join(lines)


def _format_audit_knowledge_sections(snapshot: dict) -> str:
    sections: list[str] = []
    combined_items = [
        *snapshot["skills"].items(),
        *snapshot["research"].items(),
    ]
    for name, content in combined_items:
        text = _truncate(str(content or "").strip(), KNOWLEDGE_AUDIT_SKILL_CHARS)
        if not text:
            continue
        sections.append(f"## {name}\n{text}")
        if len(sections) >= KNOWLEDGE_AUDIT_SKILL_LIMIT:
            break
    return "\n\n".join(sections) or "No agent knowledge files yet."


def _build_prompt_section(title: str, content: str, *, limit: int) -> str:
    body = _truncate(content.strip() or "n/a", limit)
    return f"{title}\n{body}"


def _compose_prompt_with_budget(*, intro: str, sections: list[tuple[str, str, int]], total_limit: int) -> str:
    rendered_sections = [
        _build_prompt_section(title, content, limit=limit)
        for title, content, limit in sections
    ]
    prompt = f"{intro}\n\n" + "\n\n".join(rendered_sections)
    if len(prompt) <= total_limit:
        return prompt

    shrink_order = ["## Existing agent knowledge", "## Available document summaries", "## Project context", "## Agent"]
    minimum_limits = {
        "## Existing agent knowledge": 700,
        "## Available document summaries": 260,
        "## Project context": 520,
        "## Agent": 260,
    }
    mutable_sections = {title: content for title, content, _limit in sections}
    current_limits = {title: limit for title, _content, limit in sections}

    def _render() -> str:
        return f"{intro}\n\n" + "\n\n".join(
            _build_prompt_section(title, mutable_sections[title], limit=current_limits[title])
            for title, _content, _limit in sections
        )

    prompt = _render()
    for title in shrink_order:
        if len(prompt) <= total_limit:
            break
        overflow = len(prompt) - total_limit
        current_limit = current_limits[title]
        min_limit = minimum_limits[title]
        if current_limit <= min_limit:
            continue
        current_limits[title] = max(min_limit, current_limit - overflow)
        prompt = _render()

    if len(prompt) <= total_limit:
        return prompt

    return _truncate(prompt, total_limit)


def _truncate_optional_text(value: object, limit: int) -> str | None:
    text = _truncate(str(value or "").strip(), limit)
    return text or None


def _sanitize_knowledge_audit_payload(payload: object) -> tuple[object, bool]:
    if not isinstance(payload, dict):
        return payload, False

    changed = False
    normalized = dict(payload)

    score = normalized.get("readiness_score")
    if isinstance(score, (int, float)):
        clamped_score = max(0, min(int(score), 100))
        if clamped_score != score:
            normalized["readiness_score"] = clamped_score
            changed = True

    summary = _truncate_optional_text(normalized.get("summary"), 140)
    if summary is not None and summary != normalized.get("summary"):
        normalized["summary"] = summary
        changed = True

    missing_items = normalized.get("missing_knowledge_summary")
    if isinstance(missing_items, list):
        sanitized_missing = _normalize_text_list(
            missing_items,
            limit=KNOWLEDGE_MAX_SUMMARIES,
            item_limit=KNOWLEDGE_MISSING_ITEM_MAX_CHARS,
        )
        if sanitized_missing != missing_items:
            normalized["missing_knowledge_summary"] = sanitized_missing
            changed = True

    recommendations = normalized.get("recommendations")
    if isinstance(recommendations, list):
        sanitized_recommendations: list[dict] = []
        for raw_recommendation in recommendations[:KNOWLEDGE_MAX_RECOMMENDATIONS]:
            if not isinstance(raw_recommendation, dict):
                sanitized_recommendations.append(raw_recommendation)
                continue

            sanitized_recommendation = dict(raw_recommendation)
            action_value = str(sanitized_recommendation.get("action_type", "")).strip().lower()

            title = _truncate_optional_text(sanitized_recommendation.get("title"), 60)
            summary = _truncate_optional_text(sanitized_recommendation.get("summary"), 80)
            reason = _truncate_optional_text(sanitized_recommendation.get("reason"), 140)
            recommended_source = _truncate_optional_text(sanitized_recommendation.get("recommended_source"), 80)

            if title is not None and title != sanitized_recommendation.get("title"):
                sanitized_recommendation["title"] = title
                changed = True
            if summary is not None and summary != sanitized_recommendation.get("summary"):
                sanitized_recommendation["summary"] = summary
                changed = True
            if reason is not None and reason != sanitized_recommendation.get("reason"):
                sanitized_recommendation["reason"] = reason
                changed = True
            if recommended_source is not None and recommended_source != sanitized_recommendation.get("recommended_source"):
                sanitized_recommendation["recommended_source"] = recommended_source
                changed = True

            if action_value == KnowledgeRecommendationAction.LAUNCH_RESEARCH.value:
                suggested_topic = _truncate_optional_text(sanitized_recommendation.get("suggested_topic"), 120)
            else:
                suggested_topic = None
            if suggested_topic != sanitized_recommendation.get("suggested_topic"):
                sanitized_recommendation["suggested_topic"] = suggested_topic
                changed = True

            evidence = sanitized_recommendation.get("evidence")
            if isinstance(evidence, list):
                sanitized_evidence: list[dict] = []
                for raw_evidence in evidence[:1]:
                    if not isinstance(raw_evidence, dict):
                        sanitized_evidence.append(raw_evidence)
                        continue
                    sanitized_item = dict(raw_evidence)
                    source_label = _truncate_optional_text(sanitized_item.get("source_label"), 60)
                    source_type = _truncate_optional_text(sanitized_item.get("source_type"), 40)
                    excerpt = _truncate_optional_text(sanitized_item.get("excerpt"), 80)
                    if source_label is not None:
                        sanitized_item["source_label"] = source_label
                    if source_type is not None:
                        sanitized_item["source_type"] = source_type
                    if excerpt is not None:
                        sanitized_item["excerpt"] = excerpt
                    sanitized_evidence.append(sanitized_item)
                if sanitized_evidence != evidence:
                    sanitized_recommendation["evidence"] = sanitized_evidence
                    changed = True

            sanitized_recommendations.append(sanitized_recommendation)

        if sanitized_recommendations != recommendations:
            normalized["recommendations"] = sanitized_recommendations
            changed = True

    return normalized, changed


def _priority_weight(priority: KnowledgeRecommendationPriority) -> int:
    if priority == KnowledgeRecommendationPriority.HIGH:
        return 25
    if priority == KnowledgeRecommendationPriority.MEDIUM:
        return 12
    return 6


def _level_from_score(score: int) -> KnowledgeReadinessLevel:
    if score >= 80:
        return KnowledgeReadinessLevel.SUFFICIENT
    if score >= 50:
        return KnowledgeReadinessLevel.PARTIAL
    return KnowledgeReadinessLevel.INSUFFICIENT


class KnowledgeAuditService:
    def __init__(self):
        settings = get_settings()
        self.settings = settings
        self.data_dir = Path(settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def get_agent_readiness(self, agent_id: str, *, force_refresh: bool = False) -> AgentKnowledgeReadiness:
        factory = get_agent_factory()
        agent = factory.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Unknown agent: {agent_id}")

        fingerprint, snapshot = self._build_agent_fingerprint(agent)
        cache_path = self._agent_cache_path(agent)
        previous = self._load_agent_cache(cache_path)

        if not force_refresh and previous and previous.context_fingerprint == fingerprint:
            return previous

        readiness = self._compute_agent_readiness(agent, snapshot, fingerprint, previous)
        self._save_agent_cache(cache_path, readiness)
        return readiness

    def get_global_readiness(self, *, force_refresh: bool = False) -> GlobalKnowledgeReadiness:
        agents = sorted(get_agent_factory().list_agents(), key=lambda item: (item.role.value, item.name.lower()))
        readiness_items = [self.get_agent_readiness(agent.id, force_refresh=force_refresh) for agent in agents]
        global_fingerprint = hashlib.sha256(
            "::".join(item.context_fingerprint for item in readiness_items).encode("utf-8")
        ).hexdigest()
        fallback_agent_count = sum(
            1 for item in readiness_items if item.generation_source == KnowledgeGenerationSource.HEURISTIC_FALLBACK
        )
        generation_channels = sorted({item.generation_channel for item in readiness_items if item.generation_channel})
        global_generation_channel = None
        if len(generation_channels) == 1:
            global_generation_channel = generation_channels[0]
        elif generation_channels:
            global_generation_channel = "mixed"

        shared_gaps: dict[str, GlobalKnowledgeGap] = {}
        for item in readiness_items:
            for rec in item.recommendations:
                if rec.status == KnowledgeRecommendationStatus.DISMISSED:
                    continue
                key = f"{rec.action_type.value}::{_slugify(rec.title)}"
                if key not in shared_gaps:
                    shared_gaps[key] = GlobalKnowledgeGap(
                        id=key,
                        title=rec.title,
                        action_type=rec.action_type,
                        priority=rec.priority,
                        can_be_found_on_web=rec.can_be_found_on_web,
                    )
                gap = shared_gaps[key]
                if item.agent_id not in gap.affected_agent_ids:
                    gap.affected_agent_ids.append(item.agent_id)
                    gap.affected_agent_names.append(item.agent_name)
                    gap.agent_count += 1
                if _priority_weight(rec.priority) > _priority_weight(gap.priority):
                    gap.priority = rec.priority

        return GlobalKnowledgeReadiness(
            generated_at=_now_iso(),
            fingerprint=global_fingerprint,
            total_agents=len(readiness_items),
            insufficient_agents=sum(1 for item in readiness_items if item.readiness_level == KnowledgeReadinessLevel.INSUFFICIENT),
            partial_agents=sum(1 for item in readiness_items if item.readiness_level == KnowledgeReadinessLevel.PARTIAL),
            sufficient_agents=sum(1 for item in readiness_items if item.readiness_level == KnowledgeReadinessLevel.SUFFICIENT),
            fallback_agent_count=fallback_agent_count,
            has_fallback_results=fallback_agent_count > 0,
            generation_channel=global_generation_channel,
            agents=sorted(readiness_items, key=lambda item: (item.readiness_score, item.agent_name.lower())),
            shared_gaps=sorted(
                shared_gaps.values(),
                key=lambda item: (-_priority_weight(item.priority), -item.agent_count, item.title.lower()),
            )[:8],
        )

    def dismiss_recommendation(self, agent_id: str, recommendation_id: str) -> AgentKnowledgeReadiness:
        readiness = self.get_agent_readiness(agent_id, force_refresh=False)
        for recommendation in readiness.recommendations:
            if recommendation.id == recommendation_id:
                recommendation.status = KnowledgeRecommendationStatus.DISMISSED
                readiness.updated_at = _now_iso()
                self._save_agent_cache(self._agent_cache_path_by_id(agent_id), readiness)
                return readiness
        raise ValueError(f"Unknown recommendation: {recommendation_id}")

    def mark_recommendation_applied(self, agent_id: str, recommendation_id: str) -> AgentKnowledgeReadiness:
        readiness = self.get_agent_readiness(agent_id, force_refresh=False)
        for recommendation in readiness.recommendations:
            if recommendation.id == recommendation_id:
                recommendation.status = KnowledgeRecommendationStatus.APPLIED
                readiness.updated_at = _now_iso()
                self._save_agent_cache(self._agent_cache_path_by_id(agent_id), readiness)
                return readiness
        raise ValueError(f"Unknown recommendation: {recommendation_id}")

    def invalidate_agent(self, agent_id: str) -> None:
        self._agent_cache_path_by_id(agent_id).unlink(missing_ok=True)

    def invalidate_all(self) -> None:
        cache_dir = self._cache_dir()
        if not cache_dir.exists():
            return
        for entry in cache_dir.glob("agent-*.json"):
            entry.unlink(missing_ok=True)

    def _compute_agent_readiness(
        self,
        agent: AgentConfig,
        snapshot: dict,
        fingerprint: str,
        previous: AgentKnowledgeReadiness | None,
    ) -> AgentKnowledgeReadiness:
        generation_source = KnowledgeGenerationSource.LLM
        generation_channel = "native_json_schema"
        generation_issue: str | None = None
        payload, generation_issue, llm_channel = self._llm_audit_agent(agent, snapshot)
        if payload is None:
            generation_source = KnowledgeGenerationSource.HEURISTIC_FALLBACK
            generation_channel = "heuristic_fallback"
            payload = self._heuristic_audit_agent(agent, snapshot)
        elif llm_channel:
            generation_channel = llm_channel

        recommendations = self._normalize_recommendations(
            agent=agent,
            items=payload.recommendations,
            previous=previous,
        )
        readiness_score = max(0, min(int(payload.readiness_score), 100))
        if recommendations:
            penalty = sum(
                _priority_weight(item.priority)
                for item in recommendations
                if item.status != KnowledgeRecommendationStatus.DISMISSED
            )
            readiness_score = min(readiness_score, max(0, 100 - penalty))

        return AgentKnowledgeReadiness(
            agent_id=agent.id,
            agent_name=agent.name,
            agent_title=agent.title,
            agent_role=agent.role.value,
            team_id=agent.team_id,
            readiness_level=_level_from_score(readiness_score),
            readiness_score=readiness_score,
            summary=_truncate(payload.summary, 140),
            missing_knowledge_summary=_normalize_text_list(
                payload.missing_knowledge_summary,
                limit=KNOWLEDGE_MAX_SUMMARIES,
                item_limit=80,
            ),
            recommendations=recommendations,
            generation_source=generation_source,
            generation_channel=generation_channel,
            generation_issue=_truncate(generation_issue or "", 220) or None,
            context_fingerprint=fingerprint,
            updated_at=_now_iso(),
        )

    def _build_agent_fingerprint(self, agent: AgentConfig) -> tuple[str, dict]:
        ctx_store = get_project_context_store()
        project_context = ctx_store.load_context() or {}
        document_store = get_document_store()
        document_summaries = summarize_documents_for_brief(document_store, max_documents=6, excerpt_chars=280)
        workspace = get_workspace_manager().get(agent.id, agent.name, agent.title)
        skill_names = [
            "project_context",
            "core_skills",
            "work_learnings",
        ]
        skills_snapshot = {
            name: workspace.read_skill(name) or ""
            for name in skill_names
        }
        research_skills = {}
        for skill in workspace.list_skills():
            if skill["name"].startswith("research_"):
                research_skills[skill["name"]] = workspace.read_skill(skill["name"]) or ""

        snapshot = {
            "agent": {
                "id": agent.id,
                "name": agent.name,
                "role": agent.role.value,
                "title": agent.title,
                "specialization": agent.specialization,
                "goal": agent.goal,
                "backstory": agent.backstory,
                "team_id": agent.team_id,
            },
            "project_context": project_context,
            "project_context_summary": render_project_brief_summary(
                project_context,
                include_meta=True,
                description_limit=700,
                domain_limit=120,
                short_term_goal_limit=220,
                target_audience_limit=240,
                business_model_limit=220,
                tech_stack_limit=200,
                notes_limit=320,
            ),
            "documents": document_summaries,
            "skills": skills_snapshot,
            "research": research_skills,
        }
        payload = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest(), snapshot

    def _normalize_recommendations(
        self,
        *,
        agent: AgentConfig,
        items: list[_KnowledgeAuditRecommendationPayload | dict],
        previous: AgentKnowledgeReadiness | None,
    ) -> list[KnowledgeRecommendation]:
        previous_statuses = {
            item.id: item.status
            for item in (previous.recommendations if previous else [])
        }
        normalized: list[KnowledgeRecommendation] = []
        seen: set[str] = set()

        for item in items[:KNOWLEDGE_MAX_RECOMMENDATIONS]:
            if isinstance(item, _KnowledgeAuditRecommendationPayload):
                raw_item = item.model_dump(mode="json")
            elif isinstance(item, dict):
                raw_item = item
            else:
                continue
            title = _truncate(str(raw_item.get("title", "")).strip(), 60)
            reason = _truncate(str(raw_item.get("reason", "")).strip(), 140)
            summary = _truncate(str(raw_item.get("summary", "")).strip(), 80)
            if not title or not reason or not summary:
                continue

            action_value = str(raw_item.get("action_type", "")).strip().lower() or KnowledgeRecommendationAction.NO_ACTION_NEEDED.value
            knowledge_value = str(raw_item.get("knowledge_type", "")).strip().lower() or KnowledgeRecommendationType.INTERNAL_CONTEXT.value
            priority_value = str(raw_item.get("priority", "")).strip().lower() or KnowledgeRecommendationPriority.MEDIUM.value

            try:
                action_type = KnowledgeRecommendationAction(action_value)
                knowledge_type = KnowledgeRecommendationType(knowledge_value)
                priority = KnowledgeRecommendationPriority(priority_value)
            except ValueError:
                continue
            can_be_found_on_web = raw_item.get("can_be_found_on_web")
            if can_be_found_on_web is None:
                can_be_found_on_web = action_type == KnowledgeRecommendationAction.LAUNCH_RESEARCH

            rec_id = f"{action_type.value}:{_slugify(title)}"
            if rec_id in seen:
                continue
            seen.add(rec_id)

            evidence_items: list[KnowledgeRecommendationEvidence] = []
            for raw_evidence in raw_item.get("evidence", []):
                if not isinstance(raw_evidence, dict):
                    continue
                evidence_items.append(
                    KnowledgeRecommendationEvidence(
                        source_label=_truncate(str(raw_evidence.get("source_label", "")).strip() or "unknown", 60),
                        source_type=_truncate(str(raw_evidence.get("source_type", "")).strip() or "unknown", 40),
                        excerpt=_truncate(str(raw_evidence.get("excerpt", "")).strip(), 80),
                    )
                )
                if len(evidence_items) >= 1:
                    break

            status = previous_statuses.get(rec_id, KnowledgeRecommendationStatus.SUGGESTED)
            normalized.append(
                KnowledgeRecommendation(
                    id=rec_id,
                    agent_id=agent.id,
                    title=title,
                    summary=summary,
                    reason=reason,
                    priority=priority,
                    knowledge_type=knowledge_type,
                    action_type=action_type,
                    can_be_found_on_web=bool(can_be_found_on_web),
                    recommended_source=_truncate(str(raw_item.get("recommended_source", "")).strip() or summary, 80),
                    suggested_topic=(
                        _truncate(str(raw_item.get("suggested_topic", "")).strip(), 120) or None
                        if action_type == KnowledgeRecommendationAction.LAUNCH_RESEARCH
                        else None
                    ),
                    status=status,
                    evidence=evidence_items,
                )
            )

        return normalized

    def _llm_audit_agent(self, agent: AgentConfig, snapshot: dict) -> tuple[_KnowledgeAuditPayload | None, str | None, str | None]:
        try:
            prompt = self._build_audit_prompt(agent, snapshot)
            client = Anthropic(api_key=self.settings.anthropic_api_key)
            structured = request_native_structured_json(
                client=client,
                model=self.settings.claude_model,
                prompt=prompt,
                response_model=_KnowledgeAuditPayload,
                max_tokens=KNOWLEDGE_AUDIT_MAX_TOKENS,
                request_name=f"knowledge_audit:{agent.id}",
                payload_sanitizer=_sanitize_knowledge_audit_payload,
            )
            return structured.value, None, structured.telemetry.generation_channel
        except StructuredJsonError as exc:
            exc.telemetry.fallback_used = True
            issue = (
                "LLM native structured output unavailable: "
                f"{exc.telemetry.provider_error or exc.telemetry.validation_error or exc.telemetry.parse_error or 'unknown error'}"
            )
            logger.warning(
                "knowledge_audit fallback_used agent=%s channel=%s parse_failed=%s validation_failed=%s parse_error=%s validation_error=%s provider_error=%s stop_reason=%s text_len=%s prompt_len=%s schema_len=%s block_types=%s empty_response=%s preview=%r",
                agent.name,
                exc.telemetry.generation_channel,
                exc.telemetry.parse_failed,
                exc.telemetry.validation_failed,
                exc.telemetry.parse_error,
                exc.telemetry.validation_error,
                exc.telemetry.provider_error,
                exc.telemetry.stop_reason,
                exc.telemetry.raw_text_length,
                exc.telemetry.prompt_length,
                exc.telemetry.schema_length,
                exc.telemetry.response_block_types,
                exc.telemetry.empty_response,
                exc.telemetry.raw_preview,
            )
            return None, issue, exc.telemetry.generation_channel
        except Exception as exc:
            logger.exception("knowledge_audit unexpected_error agent=%s", agent.name)
            logger.warning("Falling back to heuristic knowledge audit for %s: %s", agent.name, exc)
            return None, f"LLM audit failed: {exc}", None

    def _heuristic_audit_agent(self, agent: AgentConfig, snapshot: dict) -> _KnowledgeAuditPayload:
        project_context = snapshot["project_context"]
        skills = snapshot["skills"]
        documents = snapshot["documents"]
        research = snapshot["research"]

        recommendations: list[dict] = []
        summary_bits: list[str] = []

        if not project_context.get("description") or not project_context.get("short_term_goal"):
            recommendations.append(
                self._recommendation_dict(
                    title="Clarifier le contexte projet prioritaire",
                    summary="L’agent manque d’un contexte projet assez précis pour travailler avec le bon niveau de priorité.",
                    reason="Sans description claire et objectif court terme explicite, l’agent risque d’optimiser dans la mauvaise direction.",
                    priority=KnowledgeRecommendationPriority.HIGH,
                    knowledge_type=KnowledgeRecommendationType.INTERNAL_CONTEXT,
                    action_type=KnowledgeRecommendationAction.PROVIDE_DOCUMENT,
                    can_be_found_on_web=False,
                    recommended_source="Un brief projet à jour ou un document de cadrage interne",
                    evidence=[
                        {
                            "source_label": "project_context",
                            "source_type": "project_context",
                            "excerpt": "Le contexte projet global est incomplet ou ne contient pas encore d’objectif court terme exploitable.",
                        }
                    ],
                )
            )
            summary_bits.append("Le contexte projet global reste trop incomplet.")

        if len((skills.get("project_context") or "").strip()) < 220:
            recommendations.append(
                self._recommendation_dict(
                    title="Fournir un document interne spécifique à ce rôle",
                    summary="Le contexte métier propre à cet agent reste trop léger par rapport à sa mission.",
                    reason=f"{agent.name} a besoin d’un cadre plus spécifique à son rôle pour produire des livrables mieux ancrés dans la réalité du projet.",
                    priority=KnowledgeRecommendationPriority.HIGH,
                    knowledge_type=KnowledgeRecommendationType.PROJECT_PRIVATE,
                    action_type=KnowledgeRecommendationAction.PROVIDE_DOCUMENT,
                    can_be_found_on_web=False,
                    recommended_source=f"Un document interne directement utile pour le rôle {agent.title}",
                    evidence=[
                        {
                            "source_label": "project_context.md",
                            "source_type": "skill",
                            "excerpt": _truncate(skills.get("project_context") or "Fichier absent ou trop court.", 160),
                        }
                    ],
                )
            )
            summary_bits.append("Le contexte spécifique au rôle est encore léger.")

        if not documents:
            recommendations.append(
                self._recommendation_dict(
                    title="Partager au moins un document source de référence",
                    summary="Aucun document utilisateur n’est encore disponible pour ancrer les décisions de l’agent.",
                    reason="Sans source interne ou document produit, l’agent doit extrapoler à partir du brief seul.",
                    priority=KnowledgeRecommendationPriority.MEDIUM,
                    knowledge_type=KnowledgeRecommendationType.PROJECT_PRIVATE,
                    action_type=KnowledgeRecommendationAction.PROVIDE_DOCUMENT,
                    can_be_found_on_web=False,
                    recommended_source="PRD, deck, notes produit, manuel, notes client ou doc stratégique",
                    evidence=[],
                )
            )
            summary_bits.append("Aucun document de référence n’a encore été partagé.")

        if not research and agent.specialization not in {"general_management", "coordination"}:
            recommendations.append(
                self._recommendation_dict(
                    title="Compléter par une recherche web ciblée",
                    summary="L’agent ne dispose pas encore d’une recherche externe structurée sur son périmètre.",
                    reason="Une recherche ciblée peut combler rapidement les angles publics sans solliciter inutilement l’utilisateur.",
                    priority=KnowledgeRecommendationPriority.MEDIUM,
                    knowledge_type=KnowledgeRecommendationType.DOMAIN_CONTEXT,
                    action_type=KnowledgeRecommendationAction.LAUNCH_RESEARCH,
                    can_be_found_on_web=True,
                    recommended_source=f"Recherche web ciblée sur le périmètre de {agent.title}",
                    suggested_topic=f"{agent.title} for {project_context.get('name') or 'this project'}",
                    evidence=[
                        {
                            "source_label": "skills/",
                            "source_type": "skill",
                            "excerpt": "Aucun skill de recherche spécialisé n’a encore été trouvé dans le workspace.",
                        }
                    ],
                )
            )

        score = 100 - sum(_priority_weight(KnowledgeRecommendationPriority(item["priority"])) for item in recommendations)
        summary = (
            " ".join(summary_bits)
            if summary_bits
            else "L’agent semble globalement bien briefé, avec seulement quelques compléments potentiels."
        )
        selected_recommendations = sorted(
            recommendations,
            key=lambda item: (
                -_priority_weight(KnowledgeRecommendationPriority(item["priority"])),
                item.get("action_type") != KnowledgeRecommendationAction.LAUNCH_RESEARCH.value,
                str(item.get("title", "")).lower(),
            ),
        )[:KNOWLEDGE_MAX_RECOMMENDATIONS]
        return _KnowledgeAuditPayload(
            readiness_level=_level_from_score(max(0, score)),
            readiness_score=max(0, score),
            summary=_truncate(summary, 140),
            missing_knowledge_summary=_normalize_text_list(
                summary_bits,
                limit=KNOWLEDGE_MAX_SUMMARIES,
                item_limit=KNOWLEDGE_MISSING_ITEM_MAX_CHARS,
            ),
            recommendations=selected_recommendations,
        )

    def _build_audit_prompt(self, agent: AgentConfig, snapshot: dict) -> str:
        agent_context = (
            f"- Name: {agent.name}\n"
            f"- Role: {agent.role.value}\n"
            f"- Title: {agent.title}\n"
            f"- Specialization: {agent.specialization}\n"
            f"- Goal: {_truncate(agent.goal, 180)}\n"
            f"- Backstory: {_truncate(agent.backstory, 180)}"
        )
        return _compose_prompt_with_budget(
            intro=KNOWLEDGE_AUDIT_PROMPT,
            sections=[
                ("## Agent", agent_context, KNOWLEDGE_AGENT_SECTION_LIMIT),
                (
                    "## Project context",
                    snapshot["project_context_summary"],
                    KNOWLEDGE_PROJECT_CONTEXT_SECTION_LIMIT,
                ),
                (
                    "## Available document summaries",
                    _format_audit_documents(snapshot["documents"]),
                    KNOWLEDGE_DOCUMENTS_SECTION_LIMIT,
                ),
                (
                    "## Existing agent knowledge",
                    _format_audit_knowledge_sections(snapshot),
                    KNOWLEDGE_SKILLS_SECTION_LIMIT,
                ),
            ],
            total_limit=KNOWLEDGE_AUDIT_PROMPT_BUDGET,
        )

    def _recommendation_dict(
        self,
        *,
        title: str,
        summary: str,
        reason: str,
        priority: KnowledgeRecommendationPriority,
        knowledge_type: KnowledgeRecommendationType,
        action_type: KnowledgeRecommendationAction,
        can_be_found_on_web: bool,
        recommended_source: str,
        suggested_topic: str | None = None,
        evidence: list[dict] | None = None,
    ) -> dict:
        normalized_evidence: list[dict] = []
        for raw_evidence in (evidence or [])[:1]:
            if not isinstance(raw_evidence, dict):
                continue
            normalized_evidence.append(
                {
                    "source_label": _truncate(str(raw_evidence.get("source_label", "")).strip() or "unknown", 60),
                    "source_type": _truncate(str(raw_evidence.get("source_type", "")).strip() or "unknown", 40),
                    "excerpt": _truncate(str(raw_evidence.get("excerpt", "")).strip(), 80),
                }
            )
        return {
            "title": _truncate(title, 60),
            "summary": _truncate(summary, 80),
            "reason": _truncate(reason, 140),
            "priority": priority.value,
            "knowledge_type": knowledge_type.value,
            "action_type": action_type.value,
            "can_be_found_on_web": can_be_found_on_web,
            "recommended_source": _truncate(recommended_source, 80),
            "suggested_topic": _truncate(suggested_topic or "", 120) or None,
            "evidence": normalized_evidence,
        }

    def _cache_dir(self) -> Path:
        cache_dir = self.data_dir / "knowledge_readiness"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def _agent_cache_path(self, agent: AgentConfig) -> Path:
        return self._cache_dir() / f"agent-{agent.id}.json"

    def _agent_cache_path_by_id(self, agent_id: str) -> Path:
        return self._cache_dir() / f"agent-{agent_id}.json"

    def _load_agent_cache(self, path: Path) -> AgentKnowledgeReadiness | None:
        if not path.exists():
            return None
        try:
            return AgentKnowledgeReadiness.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.warning("Failed to load knowledge readiness cache %s: %s", path, exc)
            return None

    def _save_agent_cache(self, path: Path, readiness: AgentKnowledgeReadiness) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(readiness.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


@lru_cache(maxsize=1)
def get_knowledge_audit_service() -> KnowledgeAuditService:
    return KnowledgeAuditService()
