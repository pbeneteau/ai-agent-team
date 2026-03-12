import hashlib
import json
import logging
import re
import threading
from pathlib import Path
from typing import Literal, Optional

from anthropic import Anthropic
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.agents.specialists.templates import TEAM_TEMPLATES
from app.config import get_settings
from app.config.models import get_default_model_tier
from app.config.prompts import RECOMMEND_TEAMS_PROMPT
from app.config.team_recommendations import (
    TEAM_RECOMMENDATION_CACHE_VERSION as RECOMMENDATION_CACHE_VERSION,
    TEAM_CONTEXT_TEXT_MAX_CHARS,
    TEAM_RECOMMENDATION_AGENT_BACKSTORY_MAX_CHARS,
    TEAM_RECOMMENDATION_AGENT_GOAL_MAX_CHARS,
    TEAM_RECOMMENDATION_AGENT_NAME_MAX_CHARS,
    TEAM_RECOMMENDATION_AGENT_SPECIALIZATION_MAX_CHARS,
    TEAM_RECOMMENDATION_AGENT_TITLE_MAX_CHARS,
    TEAM_RECOMMENDATION_DESCRIPTION_MAX_CHARS,
    TEAM_RECOMMENDATION_DOMAIN_MAX_CHARS,
    TEAM_RECOMMENDATION_MAX_CHANGES,
    TEAM_RECOMMENDATION_MAX_NEW_TEAMS,
    TEAM_RECOMMENDATION_NAME_MAX_CHARS,
    TEAM_RECOMMENDATION_REASON_MAX_CHARS,
    TEAM_RECOMMENDATION_SCOPE_UPDATE_MAX_CHARS,
)
from app.config.token_budgets import (
    TEAM_RECOMMENDATION_MAX_TOKENS as TEAM_RECOMMENDATION_RESPONSE_MAX_TOKENS,
)
from app.core.agent_factory import get_agent_factory
from app.core.knowledge import get_knowledge_audit_service
from app.core.learning import run_learning_phase, run_learning_phase_for_team, run_project_briefing
from app.core.project_brief import normalize_project_brief_payload, render_project_brief_summary
from app.core.structured_json import StructuredJsonError, request_native_structured_json
from app.core.workspace import get_workspace_manager
from app.models.agent import AgentConfig, AgentResponse
from app.models.brief import (
    ProjectBriefMutationResponse,
    ProjectBriefStateResponse,
    ProjectContextDraftRequest,
    ProjectContextPublishRequest,
)
from app.models.team_recommendations import (
    RecommendationCachePayload,
    RecommendationLLMPayload,
    RecommendationResponse,
    RecommendedAgentSpec,
    TeamChangeRecommendation,
    TeamRecommendation,
)
from app.models.team import TeamConfig, TeamResponse, OrganigrammeNode
from app.memory.project_context import get_project_context_store

router = APIRouter(prefix="/teams", tags=["teams"])
logger = logging.getLogger(__name__)
_recommendation_cache_lock = threading.Lock()


class CreateTeamFromTemplateRequest(BaseModel):
    template: str


class CreateCustomTeamRequest(BaseModel):
    name: str
    description: str
    domain: str
    agents: list[dict]


class AddTeamAgentRequest(BaseModel):
    agent: dict


class UpdateTeamScopeRequest(BaseModel):
    description: str
    scope_note: str


def _project_context_summary(ctx: dict) -> str:
    return render_project_brief_summary(ctx)


def _default_model_tier(*, is_lead: bool) -> str:
    settings = get_settings()
    return get_default_model_tier(settings, is_lead=is_lead).value


def _existing_teams_text() -> str:
    factory = get_agent_factory()
    teams = factory.list_teams()
    if not teams:
        return "No teams created yet."

    lines = []
    for team in teams:
        agents = factory.get_team_agents(team.id)
        agent_summary = ", ".join(
            f"{a.name} (agent_id: {a.id}, title: {a.title}, specialization: {a.specialization}, role: {a.role.value})"
            for a in agents
        )
        lines.append(
            f"- {team.name} (team_id: {team.id}) | domain={team.domain} | focus={_truncate(team.description, TEAM_CONTEXT_TEXT_MAX_CHARS)} | scope={_truncate(team.scope_note, TEAM_CONTEXT_TEXT_MAX_CHARS)} | lead_agent_id={team.lead_agent_id} | agents={agent_summary}"
        )
    return "\n".join(lines)


def _recommendation_cache_file() -> Path:
    settings = get_settings()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "team_recommendations_cache.json"


def _recommendation_input_snapshot(project_ctx: dict) -> dict:
    factory = get_agent_factory()
    teams_snapshot = []
    for team in sorted(factory.list_teams(), key=lambda item: item.id):
        agents = factory.get_team_agents(team.id)
        teams_snapshot.append(
            {
                "id": team.id,
                "name": team.name,
                "description": team.description,
                "domain": team.domain,
                "lead_agent_id": team.lead_agent_id,
                "scope_note": team.scope_note,
                "agents": [
                    {
                        "id": agent.id,
                        "name": agent.name,
                        "role": agent.role.value,
                        "title": agent.title,
                        "specialization": agent.specialization,
                        "team_id": agent.team_id,
                        "parent_id": agent.parent_id,
                    }
                    for agent in sorted(agents, key=lambda item: item.id)
                ],
            }
        )
    return {
        "version": RECOMMENDATION_CACHE_VERSION,
        "project_context": normalize_project_brief_payload(project_ctx),
        "teams": teams_snapshot,
    }


def _recommendation_fingerprint(snapshot: dict) -> str:
    payload = json.dumps(snapshot, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_cached_recommendations(fingerprint: str) -> Optional[RecommendationResponse]:
    cache_file = _recommendation_cache_file()
    if not cache_file.exists():
        return None

    try:
        with _recommendation_cache_lock:
            raw_payload = json.loads(cache_file.read_text(encoding="utf-8"))
        if not isinstance(raw_payload, dict):
            return None
        if int(raw_payload.get("version", 0) or 0) != RECOMMENDATION_CACHE_VERSION:
            return None
        if str(raw_payload.get("fingerprint", "")) != fingerprint:
            return None
        payload = RecommendationCachePayload.model_validate(raw_payload)
        logger.info("Team recommendations cache hit")
        return payload.recommendations
    except Exception as exc:
        logger.warning("Failed to load team recommendations cache: %s", exc)
        return None


def _save_cached_recommendations(fingerprint: str, recommendations: RecommendationResponse) -> None:
    cache_file = _recommendation_cache_file()
    payload = RecommendationCachePayload(
        version=RECOMMENDATION_CACHE_VERSION,
        fingerprint=fingerprint,
        recommendations=recommendations,
    )
    try:
        with _recommendation_cache_lock:
            cache_file.write_text(
                json.dumps(payload.model_dump(mode="json"), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
    except Exception as exc:
        logger.warning("Failed to save team recommendations cache: %s", exc)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "team-recommendation"


def _truncate(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _heuristic_team_recommendations(project_ctx: dict) -> list[TeamRecommendation]:
    text = " ".join(
        [
            project_ctx.get("name", ""),
            project_ctx.get("description", ""),
            project_ctx.get("domain", ""),
            project_ctx.get("short_term_goal", ""),
            project_ctx.get("tech_stack", ""),
            project_ctx.get("business_model", ""),
            project_ctx.get("notes", ""),
        ]
    ).lower()
    project_name = project_ctx.get("name", "le projet")

    recommendations: list[TeamRecommendation] = []
    if any(keyword in text for keyword in ["manufacturer", "device", "support", "ticket", "customer", "documentation"]):
        recommendations.append(
            TeamRecommendation(
                id="manufacturer-success",
                name="Équipe Manufacturer Success",
                description="Accélère le déploiement chez les fabricants et structure l'onboarding B2B.",
                domain="manufacturer_success",
                reason="Le projet vise des fabricants : une équipe dédiée à l'onboarding et à l'adoption est un vrai levier.",
                urgency="now",
                score=88,
                agents=[
                    RecommendedAgentSpec(
                        name="Nora",
                        title="Manufacturer Success Lead",
                        specialization="customer_success_b2b",
                        goal=f"Structurer l'onboarding des fabricants et maximiser l'adoption de {project_name}.",
                        backstory="Experte en customer success B2B SaaS enterprise, spécialisée dans l'onboarding et l'adoption de comptes stratégiques.",
                        is_lead=True,
                        model_tier=_default_model_tier(is_lead=True),
                    ),
                    RecommendedAgentSpec(
                        name="Liam",
                        title="Implementation Specialist",
                        specialization="implementation_ops",
                        goal=f"Transformer la documentation métier en déploiements fluides pour {project_name}.",
                        backstory="Spécialiste des déploiements SaaS complexes, focalisé sur intégration, runbooks et activation.",
                        model_tier=_default_model_tier(is_lead=True),
                    ),
                ],
            )
        )

    if any(keyword in text for keyword in ["b2b", "saas", "revenue", "pricing", "market", "sales"]):
        recommendations.append(
            TeamRecommendation(
                id="strategic-gtm",
                name="Équipe GTM Stratégique",
                description="Clarifie le positionnement, l'ICP et le motion commercial du projet.",
                domain="go_to_market",
                reason="Le projet a une dimension B2B claire : une équipe GTM custom aidera à cibler le bon segment et le bon message.",
                urgency="soon",
                score=81,
                agents=[
                    RecommendedAgentSpec(
                        name="Maya",
                        title="GTM Lead",
                        specialization="go_to_market_strategy",
                        goal=f"Définir le segment prioritaire, le messaging et le plan de traction de {project_name}.",
                        backstory="Leader GTM spécialisée dans les lancements SaaS B2B early-stage et le positionnement de nouvelles offres.",
                        is_lead=True,
                        model_tier=_default_model_tier(is_lead=True),
                    ),
                    RecommendedAgentSpec(
                        name="Ethan",
                        title="Partnerships Specialist",
                        specialization="strategic_partnerships",
                        goal=f"Identifier des partenaires et canaux de distribution crédibles pour accélérer l'adoption de {project_name}.",
                        backstory="Spécialiste des partenariats B2B et des écosystèmes sectoriels, orienté distribution et leverage commercial.",
                        model_tier=_default_model_tier(is_lead=True),
                    ),
                ],
            )
        )

    if any(keyword in text for keyword in ["ios", "camera", "experience", "workflow", "user", "voice", "spoken"]):
        recommendations.append(
            TeamRecommendation(
                id="field-ux-research",
                name="Équipe UX Terrain",
                description="Capte les frictions réelles d'usage et les transforme en décisions produit.",
                domain="field_ux_research",
                reason="Le produit repose sur une expérience terrain sensible : une équipe dédiée aux frictions réelles d'usage apportera plus de fluidité.",
                urgency="soon",
                score=76,
                agents=[
                    RecommendedAgentSpec(
                        name="Chloe",
                        title="Field UX Lead",
                        specialization="ux_research",
                        goal=f"Comprendre les blocages utilisateurs en situation réelle et améliorer les workflows critiques de {project_name}.",
                        backstory="UX researcher spécialisée en workflows complexes, observation terrain et synthèse d'insights actionnables.",
                        is_lead=True,
                        model_tier="sonnet",
                    ),
                    RecommendedAgentSpec(
                        name="Noah",
                        title="Conversation Design Specialist",
                        specialization="conversation_design",
                        goal=f"Améliorer les réponses guidées et les consignes de {project_name} pour réduire la friction utilisateur.",
                        backstory="Spécialiste du conversation design et des interfaces guidées, focalisé sur clarté et compréhension utilisateur.",
                        model_tier="sonnet",
                    ),
                ],
            )
        )

    if not recommendations:
        recommendations.append(
            TeamRecommendation(
                id="customer-discovery",
                name="Équipe Customer Discovery",
                description="Valide les besoins réels du marché avant d'élargir l'organisation.",
                domain="customer_discovery",
                reason="Avant d'ajouter des cellules plus spécialisées, une équipe discovery aide à confirmer les besoins les plus urgents.",
                urgency="soon",
                score=68,
                agents=[
                    RecommendedAgentSpec(
                        name="Iris",
                        title="Customer Discovery Lead",
                        specialization="customer_research",
                        goal=f"Structurer les entretiens et synthétiser les besoins prioritaires pour {project_name}.",
                        backstory="Experte en discovery produit B2B, spécialisée dans les entretiens qualitatifs et la structuration d'insights exploitables.",
                        is_lead=True,
                        model_tier="sonnet",
                    ),
                ],
            )
        )

    return recommendations[:TEAM_RECOMMENDATION_MAX_NEW_TEAMS]


def _heuristic_team_change_recommendations(project_ctx: dict) -> list[TeamChangeRecommendation]:
    factory = get_agent_factory()
    teams = factory.list_teams()
    if not teams:
        return []

    text = " ".join(
        [
            project_ctx.get("name", ""),
            project_ctx.get("description", ""),
            project_ctx.get("domain", ""),
            project_ctx.get("short_term_goal", ""),
            project_ctx.get("tech_stack", ""),
            project_ctx.get("business_model", ""),
            project_ctx.get("notes", ""),
        ]
    ).lower()
    project_name = project_ctx.get("name", "le projet")

    team_changes: list[TeamChangeRecommendation] = []
    fundraising_focus = any(
        keyword in text
        for keyword in ["fundraising", "fundraising deck", "pitch deck", "pre-seed", "investor", "seed round"]
    )
    if fundraising_focus:
        business_like_team = next(
            (
                team for team in teams
                if any(keyword in team.domain.lower() for keyword in ["business", "market", "go_to_market", "finance"])
                or any(keyword in team.name.lower() for keyword in ["business", "gtm", "market", "finance"])
            ),
            teams[0],
        )
        team_agents = factory.get_team_agents(business_like_team.id)
        specializations = {agent.specialization.lower() for agent in team_agents}

        if not any("fundraising" in specialization or "investor" in specialization for specialization in specializations):
            team_changes.append(
                TeamChangeRecommendation(
                    id="add-fundraising-specialist",
                    team_id=business_like_team.id,
                    team_name=business_like_team.name,
                    change_type="add_specialist",
                    urgency="now",
                    score=90,
                    reason="L'objectif court terme est centré sur un pitch deck pre-seed : il manque un spécialiste fundraising pour structurer le narratif investisseur.",
                    suggested_agent=RecommendedAgentSpec(
                        name="Sophie",
                        title="Fundraising Specialist",
                        specialization="fundraising",
                        goal=f"Construire un pitch deck pre-seed crédible et convaincant pour {project_name}.",
                        backstory="Experte en fundraising early-stage, spécialisée dans le narratif investisseur, la préparation de decks pre-seed et les objections fonds/business angels.",
                        is_lead=False,
                        model_tier="sonnet",
                    ),
                )
            )

        if not any(
            keyword in specialization
            for specialization in specializations
            for keyword in ["finance", "financial", "business_analysis", "market_research"]
        ):
            team_changes.append(
                TeamChangeRecommendation(
                    id="add-investor-analysis-specialist",
                    team_id=business_like_team.id,
                    team_name=business_like_team.name,
                    change_type="add_specialist",
                    urgency="now",
                    score=84,
                    reason="Le deck pre-seed demandera des hypothèses marché et financières solides : l'équipe manque d'un profil analysis/finance.",
                    suggested_agent=RecommendedAgentSpec(
                        name="Marcus",
                        title="Investor Readiness Analyst",
                        specialization="financial_strategy",
                        goal=f"Renforcer le business case, les hypothèses financières et la taille de marché de {project_name}.",
                        backstory="Analyste orienté early-stage, capable de transformer données marché, hypothèses business et logique financière en argumentaire investisseur.",
                        is_lead=False,
                        model_tier="sonnet",
                    ),
                )
            )

    return team_changes[:TEAM_RECOMMENDATION_MAX_CHANGES]


def _find_team(team_id: Optional[str], team_name: Optional[str]) -> Optional[TeamConfig]:
    factory = get_agent_factory()
    if team_id:
        team = factory.get_team(team_id)
        if team:
            return team
    if team_name:
        normalized_name = _slugify(team_name)
        for team in factory.list_teams():
            if _slugify(team.name) == normalized_name:
                return team
    return None


def _find_team_agent(team: TeamConfig, agent_id: Optional[str], agent_name: Optional[str]) -> Optional[AgentConfig]:
    factory = get_agent_factory()
    team_agents = factory.get_team_agents(team.id)
    if agent_id:
        for agent in team_agents:
            if agent.id == agent_id:
                return agent
    if agent_name:
        normalized_name = _slugify(agent_name)
        for agent in team_agents:
            if _slugify(agent.name) == normalized_name:
                return agent
    return None


def _team_already_exists(team_name: str, domain: str) -> bool:
    factory = get_agent_factory()
    normalized_name = _slugify(team_name)
    normalized_domain = _slugify(domain)
    for team in factory.list_teams():
        if _slugify(team.name) == normalized_name:
            return True
        if normalized_domain and _slugify(team.domain) == normalized_domain:
            return True
    return False


def _normalize_recommendation(item: dict) -> Optional[TeamRecommendation]:
    try:
        name = str(item.get("name", "")).strip()
        domain = str(item.get("domain", "")).strip()
        description = str(item.get("description", "")).strip()
        reason = str(item.get("reason", "")).strip()
        urgency = str(item.get("urgency", "soon")).strip().lower()
        if not name or not domain or not description or not reason:
            return None

        if urgency not in {"now", "soon", "later"}:
            urgency = "soon"

        agents: list[RecommendedAgentSpec] = []
        for index, agent_item in enumerate(item.get("agents", [])):
            if not isinstance(agent_item, dict):
                continue
            is_lead = bool(agent_item.get("is_lead", index == 0))
            requested_tier = str(agent_item.get("model_tier", "")).strip().lower()
            model_tier = requested_tier if requested_tier in {"sonnet", "opus"} else _default_model_tier(is_lead=is_lead)
            agents.append(
                RecommendedAgentSpec(
                    name=_truncate(
                        str(agent_item.get("name", "")).strip() or f"Agent {index + 1}",
                        TEAM_RECOMMENDATION_AGENT_NAME_MAX_CHARS,
                    ),
                    title=_truncate(
                        str(agent_item.get("title", "")).strip() or "Specialist",
                        TEAM_RECOMMENDATION_AGENT_TITLE_MAX_CHARS,
                    ),
                    specialization=_truncate(
                        str(agent_item.get("specialization", "")).strip() or "general",
                        TEAM_RECOMMENDATION_AGENT_SPECIALIZATION_MAX_CHARS,
                    ),
                    goal=_truncate(
                        str(agent_item.get("goal", "")).strip() or "Contribuer au besoin clé de l'équipe.",
                        TEAM_RECOMMENDATION_AGENT_GOAL_MAX_CHARS,
                    ),
                    backstory=_truncate(
                        str(agent_item.get("backstory", "")).strip() or "Profil expérimenté, adapté au besoin du projet.",
                        TEAM_RECOMMENDATION_AGENT_BACKSTORY_MAX_CHARS,
                    ),
                    is_lead=is_lead,
                    model_tier=model_tier,
                )
            )

        if not agents:
            return None
        if not any(agent.is_lead for agent in agents):
            agents[0].is_lead = True
            agents[0].model_tier = _default_model_tier(is_lead=True)

        return TeamRecommendation(
            id=_slugify(str(item.get("id", "")).strip() or name),
            name=_truncate(name, TEAM_RECOMMENDATION_NAME_MAX_CHARS),
            description=_truncate(description, TEAM_RECOMMENDATION_DESCRIPTION_MAX_CHARS),
            domain=_truncate(domain, TEAM_RECOMMENDATION_DOMAIN_MAX_CHARS),
            reason=_truncate(reason, TEAM_RECOMMENDATION_REASON_MAX_CHARS),
            urgency=urgency,
            score=max(0, min(int(item.get("score", 0)), 100)),
            agents=agents,
        )
    except Exception:
        return None


def _normalize_team_change(item: dict) -> Optional[TeamChangeRecommendation]:
    try:
        team = _find_team(
            str(item.get("team_id", "")).strip() or None,
            str(item.get("team_name", "")).strip() or None,
        )
        if not team:
            return None

        change_type = str(item.get("change_type", "")).strip().lower()
        if change_type not in {"add_specialist", "remove_agent", "adjust_scope"}:
            return None

        urgency = str(item.get("urgency", "soon")).strip().lower()
        if urgency not in {"now", "soon", "later"}:
            urgency = "soon"

        target_agent = _find_team_agent(
            team,
            str(item.get("target_agent_id", "")).strip() or None,
            str(item.get("target_agent_name", "")).strip() or None,
        )

        suggested_agent = None
        if change_type == "add_specialist":
            suggested_agent = _normalize_suggested_change_agent(item.get("suggested_agent"))
            if not suggested_agent:
                return None

        scope_update = None
        if change_type == "adjust_scope":
            scope_update = str(item.get("scope_update", "")).strip() or str(item.get("reason", "")).strip()
            if not scope_update:
                return None

        if change_type == "remove_agent" and not target_agent:
            return None
        if change_type == "remove_agent" and target_agent and target_agent.role.value == "team_lead":
            return None

        return TeamChangeRecommendation(
            id=_slugify(str(item.get("id", "")).strip() or f"{team.id}-{change_type}"),
            team_id=team.id,
            team_name=_truncate(team.name, TEAM_RECOMMENDATION_NAME_MAX_CHARS),
            change_type=change_type,
            urgency=urgency,
            score=max(0, min(int(item.get("score", 0)), 100)),
            reason=_truncate(
                str(item.get("reason", "")).strip() or "Pas de justification fournie.",
                TEAM_RECOMMENDATION_REASON_MAX_CHARS,
            ),
            target_agent_id=target_agent.id if target_agent else None,
            target_agent_name=_truncate(target_agent.name, TEAM_RECOMMENDATION_NAME_MAX_CHARS) if target_agent else None,
            suggested_agent=suggested_agent,
            scope_update=_truncate(scope_update, TEAM_RECOMMENDATION_SCOPE_UPDATE_MAX_CHARS) if scope_update else None,
        )
    except Exception:
        return None


def _normalize_suggested_change_agent(raw: object) -> Optional[RecommendedAgentSpec]:
    if not isinstance(raw, dict):
        return None
    try:
        return RecommendedAgentSpec(
            name=_truncate(
                str(raw.get("name", "")).strip() or "Suggested Specialist",
                TEAM_RECOMMENDATION_AGENT_NAME_MAX_CHARS,
            ),
            title=_truncate(
                str(raw.get("title", "")).strip() or "Specialist",
                TEAM_RECOMMENDATION_AGENT_TITLE_MAX_CHARS,
            ),
            specialization=_truncate(
                str(raw.get("specialization", "")).strip() or "general",
                TEAM_RECOMMENDATION_AGENT_SPECIALIZATION_MAX_CHARS,
            ),
            goal=_truncate(
                str(raw.get("goal", "")).strip() or "Apporter une expertise manquante à l'équipe.",
                TEAM_RECOMMENDATION_AGENT_GOAL_MAX_CHARS,
            ),
            backstory=_truncate(
                str(raw.get("backstory", "")).strip() or "Profil expérimenté adapté au besoin identifié.",
                TEAM_RECOMMENDATION_AGENT_BACKSTORY_MAX_CHARS,
            ),
            is_lead=False,
            model_tier=_default_model_tier(is_lead=False),
        )
    except Exception:
        return None


def _finalize_team_recommendations(recommendations: list[TeamRecommendation]) -> list[TeamRecommendation]:
    deduped: dict[str, TeamRecommendation] = {}
    for rec in recommendations:
        if _team_already_exists(rec.name, rec.domain):
            continue
        key = f"{_slugify(rec.name)}::{_slugify(rec.domain)}"
        existing = deduped.get(key)
        if not existing or rec.score > existing.score:
            deduped[key] = rec
    return sorted(deduped.values(), key=lambda item: item.score, reverse=True)[
        :TEAM_RECOMMENDATION_MAX_NEW_TEAMS
    ]


def _finalize_team_changes(changes: list[TeamChangeRecommendation]) -> list[TeamChangeRecommendation]:
    factory = get_agent_factory()
    deduped: dict[str, TeamChangeRecommendation] = {}
    for change in changes:
        team = factory.get_team(change.team_id)
        if not team:
            continue

        if change.change_type == "add_specialist":
            if not change.suggested_agent:
                continue
            existing_specializations = {agent.specialization.lower() for agent in factory.get_team_agents(team.id)}
            if change.suggested_agent.specialization.lower() in existing_specializations:
                continue
            key = f"{change.team_id}::add::{change.suggested_agent.specialization.lower()}"
        elif change.change_type == "remove_agent":
            target_agent = _find_team_agent(team, change.target_agent_id, change.target_agent_name)
            if not change.target_agent_id or not target_agent:
                continue
            if target_agent.role.value == "team_lead":
                continue
            key = f"{change.team_id}::remove::{change.target_agent_id}"
        else:
            if not change.scope_update:
                continue
            key = f"{change.team_id}::adjust_scope::{_slugify(change.scope_update[:80])}"

        existing = deduped.get(key)
        if not existing or change.score > existing.score:
            deduped[key] = change
    return sorted(deduped.values(), key=lambda item: item.score, reverse=True)[
        :TEAM_RECOMMENDATION_MAX_CHANGES
    ]


def _build_team_response(team: TeamConfig, agents: list[AgentConfig]) -> TeamResponse:
    return TeamResponse(
        id=team.id,
        name=team.name,
        description=team.description,
        domain=team.domain,
        lead_agent_id=team.lead_agent_id,
        scope_note=team.scope_note,
        agents=[AgentResponse(
            id=a.id,
            name=a.name,
            role=a.role,
            title=a.title,
            specialization=a.specialization,
            goal=a.goal,
            backstory=a.backstory,
            status=a.status,
            occupancy_status=a.occupancy_status,
            occupancy_reason=a.occupancy_reason,
            current_task_id=a.current_task_id,
            current_task_title=a.current_task_title,
            current_node_id=a.current_node_id,
            current_node_title=a.current_node_title,
            busy_since=a.busy_since,
            team_id=a.team_id,
            parent_id=a.parent_id,
            workspace_path=a.workspace_path,
            tools=a.tools,
            model_tier=a.model_tier,
            max_iter=a.max_iter,
        ) for a in agents],
    )


@router.get("/", response_model=list[TeamResponse])
def list_teams():
    factory = get_agent_factory()
    return [
        _build_team_response(team, factory.get_team_agents(team.id))
        for team in factory.list_teams()
    ]


@router.get("/organigramme", response_model=list[OrganigrammeNode])
def get_organigramme():
    factory = get_agent_factory()
    factory.get_or_create_associate()
    agents = factory.list_agents()

    nodes: dict[str, OrganigrammeNode] = {}
    associate_id: str | None = None

    for agent in agents:
        nodes[agent.id] = OrganigrammeNode(
            id=agent.id,
            name=agent.name,
            title=agent.title,
            role=agent.role.value,
            status=agent.status.value,
            occupancy_status=agent.occupancy_status.value,
            occupancy_reason=agent.occupancy_reason.value if agent.occupancy_reason else None,
            current_task_id=agent.current_task_id,
            current_task_title=agent.current_task_title,
            current_node_id=agent.current_node_id,
            current_node_title=agent.current_node_title,
            busy_since=agent.busy_since,
            parent_id=agent.parent_id,
        )
        if agent.role.value == "associate":
            associate_id = agent.id

    # Virtually attach orphan team_leads to the associate so the hierarchy is correct
    for node in nodes.values():
        if node.role == "team_lead" and not node.parent_id and associate_id:
            node.parent_id = associate_id

    roots = []
    for node in nodes.values():
        if node.parent_id and node.parent_id in nodes:
            nodes[node.parent_id].children.append(node)
        else:
            roots.append(node)

    return roots


@router.get("/project-context", response_model=ProjectBriefStateResponse)
def get_project_context() -> ProjectBriefStateResponse:
    """Return the current draft/published state for the global project brief."""
    return get_project_context_store().load_state()


def _schedule_project_briefing_refresh(background_tasks: BackgroundTasks) -> None:
    factory = get_agent_factory()
    for team in factory.list_teams():
        background_tasks.add_task(run_project_briefing, team.id)


def _publish_project_context(
    payload: dict,
    background_tasks: BackgroundTasks,
) -> ProjectBriefMutationResponse:
    ctx_store = get_project_context_store()
    state, changed = ctx_store.publish_context(payload)
    if changed:
        get_knowledge_audit_service().invalidate_all()
        _schedule_project_briefing_refresh(background_tasks)
        message = "Brief publié. Rebriefing des équipes lancé en arrière-plan."
    else:
        message = "Le brief publié est déjà à jour. Aucun rebriefing supplémentaire n'a été lancé."
    return ProjectBriefMutationResponse(ok=True, message=message, state=state)


@router.put("/project-context/draft", response_model=ProjectBriefMutationResponse)
def save_project_context_draft(req: ProjectContextDraftRequest):
    """Save a draft project brief without rebriefing the teams yet."""
    ctx_store = get_project_context_store()
    state = ctx_store.save_draft(req.model_dump())
    if state.published is None:
        get_knowledge_audit_service().invalidate_all()
    return ProjectBriefMutationResponse(
        ok=True,
        message="Brouillon du brief enregistré.",
        state=state,
    )


@router.get("/recommendations", response_model=RecommendationResponse)
def get_team_recommendations():
    """Return AI-based recommendations for new teams and existing team adjustments."""
    ctx_store = get_project_context_store()
    project_ctx = normalize_project_brief_payload(ctx_store.load_context() or {})
    snapshot = _recommendation_input_snapshot(project_ctx)
    fingerprint = _recommendation_fingerprint(snapshot)

    cached = _load_cached_recommendations(fingerprint)
    if cached is not None:
        return cached

    generation_source: Literal["llm", "heuristic_fallback"] = "llm"
    generation_channel: str | None = "native_json_schema"
    generation_issue: Optional[str] = None
    new_teams: list[TeamRecommendation]
    team_changes: list[TeamChangeRecommendation]
    try:
        settings = get_settings()
        client = Anthropic(api_key=settings.anthropic_api_key)
        prompt = RECOMMEND_TEAMS_PROMPT.format(
            project_context=_project_context_summary(project_ctx),
            existing_teams=_existing_teams_text(),
            default_lead_model_tier=_default_model_tier(is_lead=True),
            default_agent_model_tier=_default_model_tier(is_lead=False),
        )
        structured = request_native_structured_json(
            client=client,
            model=settings.claude_model,
            prompt=prompt,
            response_model=RecommendationLLMPayload,
            max_tokens=TEAM_RECOMMENDATION_RESPONSE_MAX_TOKENS,
            request_name="teams_recommendations",
        )
        new_teams = []
        for item in structured.value.new_teams:
            normalized = _normalize_recommendation(item.model_dump(mode="json"))
            if not normalized:
                continue
            new_teams.append(normalized)

        team_changes = []
        for item in structured.value.team_changes:
            normalized_change = _normalize_team_change(item.model_dump(mode="json"))
            if not normalized_change:
                continue
            team_changes.append(normalized_change)
    except StructuredJsonError as exc:
        exc.telemetry.fallback_used = True
        generation_source = "heuristic_fallback"
        generation_channel = "heuristic_fallback"
        generation_issue = (
            "LLM native structured output unavailable: "
            f"{exc.telemetry.provider_error or exc.telemetry.validation_error or exc.telemetry.parse_error or 'unknown error'}"
        )
        logger.warning(
            "teams_recommendations fallback_used channel=%s parse_failed=%s validation_failed=%s parse_error=%s validation_error=%s provider_error=%s stop_reason=%s text_len=%s prompt_len=%s schema_len=%s block_types=%s empty_response=%s preview=%r",
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
        new_teams = _heuristic_team_recommendations(project_ctx)
        team_changes = _heuristic_team_change_recommendations(project_ctx)
    except Exception as exc:
        generation_source = "heuristic_fallback"
        generation_channel = "heuristic_fallback"
        generation_issue = f"LLM recommendations failed: {exc}"
        logger.exception("teams_recommendations unexpected_error")
        logger.warning("Falling back to heuristic team recommendations: %s", exc)
        new_teams = _heuristic_team_recommendations(project_ctx)
        team_changes = _heuristic_team_change_recommendations(project_ctx)

    final_recommendations = RecommendationResponse(
        new_teams=_finalize_team_recommendations(new_teams),
        team_changes=_finalize_team_changes(team_changes),
        generation_source=generation_source,
        generation_channel=generation_channel,
        generation_issue=generation_issue,
    )
    _save_cached_recommendations(fingerprint, final_recommendations)
    return final_recommendations


@router.post("/project-context/publish", response_model=ProjectBriefMutationResponse)
def publish_project_context(req: ProjectContextPublishRequest, background_tasks: BackgroundTasks):
    """
    Publish the current project brief and trigger a project briefing for all teams.
    The briefing writes domain-scoped project_context.md to each agent's workspace.
    """
    return _publish_project_context(req.model_dump(), background_tasks)


@router.put("/project-context", response_model=ProjectBriefMutationResponse)
def save_project_context(req: ProjectContextPublishRequest, background_tasks: BackgroundTasks):
    """
    Backward-compatible alias that publishes the provided brief immediately.
    """
    return _publish_project_context(req.model_dump(), background_tasks)


@router.post("/from-template", response_model=TeamResponse)
def create_team_from_template(req: CreateTeamFromTemplateRequest, background_tasks: BackgroundTasks):
    factory = get_agent_factory()
    if req.template not in TEAM_TEMPLATES:
        raise HTTPException(status_code=400, detail=f"Unknown template: {req.template}")
    team, agents = factory.create_team_from_template(req.template)
    background_tasks.add_task(run_learning_phase_for_team, team.id)
    get_knowledge_audit_service().invalidate_all()
    return _build_team_response(team, agents)


@router.post("/custom", response_model=TeamResponse)
def create_custom_team(req: CreateCustomTeamRequest, background_tasks: BackgroundTasks):
    factory = get_agent_factory()
    team, agents = factory.create_custom_team(
        name=req.name,
        description=req.description,
        domain=req.domain,
        agent_specs=req.agents,
    )
    background_tasks.add_task(run_learning_phase_for_team, team.id)
    get_knowledge_audit_service().invalidate_all()
    return _build_team_response(team, agents)


@router.post("/{team_id}/agents", response_model=TeamResponse)
def add_agent_to_team(team_id: str, req: AddTeamAgentRequest, background_tasks: BackgroundTasks):
    factory = get_agent_factory()
    team = factory.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    agent_spec = RecommendedAgentSpec.model_validate(req.agent)
    created_agent = factory.add_agent_to_team(team_id, agent_spec.model_dump())
    if not created_agent:
        raise HTTPException(status_code=400, detail="Unable to add agent to team")

    background_tasks.add_task(run_learning_phase, created_agent)
    get_knowledge_audit_service().invalidate_all()
    return _build_team_response(team, factory.get_team_agents(team_id))


@router.patch("/{team_id}/scope", response_model=TeamResponse)
def update_team_scope(team_id: str, req: UpdateTeamScopeRequest):
    factory = get_agent_factory()
    team = factory.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    updated_team = factory.update_team_scope(
        team_id,
        description=req.description,
        scope_note=req.scope_note,
    )
    if not updated_team:
        raise HTTPException(status_code=400, detail="Unable to update team scope")

    for agent in factory.get_team_agents(team_id):
        workspace = get_workspace_manager().get(agent.id, agent.name, agent.title)
        workspace.write_skill(
            "team_scope",
            (
                f"# Team Scope\n\n"
                f"## Current focus\n{req.description}\n\n"
                f"## Why this matters now\n{req.scope_note}\n"
            ),
            author="team_scope_update",
        )

    get_knowledge_audit_service().invalidate_all()
    return _build_team_response(updated_team, factory.get_team_agents(team_id))


@router.post("/reset")
def reset_all():
    factory = get_agent_factory()
    factory.reset()
    get_knowledge_audit_service().invalidate_all()
    return {"ok": True}


@router.get("/{team_id}", response_model=TeamResponse)
def get_team(team_id: str):
    factory = get_agent_factory()
    team = factory.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return _build_team_response(team, factory.get_team_agents(team_id))


@router.delete("/{team_id}")
def delete_team(team_id: str):
    factory = get_agent_factory()
    team = factory.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    wm = get_workspace_manager()
    for agent_id in team.agent_ids:
        wm.delete_workspace(agent_id)
    factory.delete_team(team_id)
    get_knowledge_audit_service().invalidate_all()
    return {"ok": True}
