from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from app.core.agent_factory import get_agent_factory
from app.core.learning import run_project_briefing
from app.models.team import TeamConfig, TeamResponse, OrganigrammeNode
from app.models.agent import AgentConfig, AgentResponse
from app.memory.project_context import get_project_context_store

router = APIRouter(prefix="/teams", tags=["teams"])


class CreateTeamFromTemplateRequest(BaseModel):
    template: str


class CreateCustomTeamRequest(BaseModel):
    name: str
    description: str
    domain: str
    agents: list[dict]


class ProjectContextRequest(BaseModel):
    name: str
    description: str
    domain: Optional[str] = None
    tech_stack: Optional[str] = None
    target_audience: Optional[str] = None
    business_model: Optional[str] = None
    notes: Optional[str] = None


def _build_team_response(team: TeamConfig, agents: list[AgentConfig]) -> TeamResponse:
    return TeamResponse(
        id=team.id,
        name=team.name,
        description=team.description,
        domain=team.domain,
        lead_agent_id=team.lead_agent_id,
        agents=[AgentResponse(
            id=a.id,
            name=a.name,
            role=a.role,
            title=a.title,
            specialization=a.specialization,
            status=a.status,
            team_id=a.team_id,
            parent_id=a.parent_id,
            tools=a.tools,
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


@router.get("/project-context")
def get_project_context():
    """Return the current global project context."""
    ctx_store = get_project_context_store()
    ctx = ctx_store.load_context()
    return ctx or {}


@router.put("/project-context")
def save_project_context(req: ProjectContextRequest, background_tasks: BackgroundTasks):
    """
    Save global project context and trigger a project briefing for all teams.
    The briefing writes domain-scoped project_context.md to each agent's workspace.
    """
    ctx_store = get_project_context_store()
    ctx_store.save_context(req.model_dump(exclude_none=True))

    factory = get_agent_factory()
    for team in factory.list_teams():
        background_tasks.add_task(run_project_briefing, team.id)

    return {"ok": True, "message": "Project context saved. Briefing agents in background."}


@router.post("/from-template", response_model=TeamResponse)
def create_team_from_template(req: CreateTeamFromTemplateRequest):
    factory = get_agent_factory()
    from app.agents.specialists.templates import TEAM_TEMPLATES
    if req.template not in TEAM_TEMPLATES:
        raise HTTPException(status_code=400, detail=f"Unknown template: {req.template}")
    team, agents = factory.create_team_from_template(req.template)
    return _build_team_response(team, agents)


@router.post("/custom", response_model=TeamResponse)
def create_custom_team(req: CreateCustomTeamRequest):
    factory = get_agent_factory()
    team, agents = factory.create_custom_team(
        name=req.name,
        description=req.description,
        domain=req.domain,
        agent_specs=req.agents,
    )
    return _build_team_response(team, agents)


@router.post("/reset")
def reset_all():
    factory = get_agent_factory()
    factory.reset()
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
    from app.core.workspace import get_workspace_manager
    team = factory.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    wm = get_workspace_manager()
    for agent_id in team.agent_ids:
        wm.delete_workspace(agent_id)
    factory.delete_team(team_id)
    return {"ok": True}
