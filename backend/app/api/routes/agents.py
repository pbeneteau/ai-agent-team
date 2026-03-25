from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from typing import Optional
from app.api.websocket_manager import get_manager
from app.config import get_settings, has_github_access, has_model_override, has_web_search
from app.core.git_provider_store import get_git_provider_store
from app.core.mcp_connection_store import get_mcp_connection_store
from app.core.agent_factory import get_agent_factory
from app.core.knowledge import get_knowledge_audit_service
from app.core.learning import run_agent_reflection, run_agent_research, run_targeted_rebriefing
from app.core.workspace import get_workspace_manager
from app.models.knowledge import AgentKnowledgeReadiness, GlobalKnowledgeReadiness
from app.models.agent import AgentLearningProfile, AgentResponse, AgentModelUpdate, ModelTier
from app.models.git_providers import (
    AgentGitBindingResolved,
    AgentGitBindingUpdateRequest,
)
from app.models.mcp import (
    AgentMcpBindingUpdateRequest,
    AgentMcpToolBindingResolved,
)


class SkillWrite(BaseModel):
    content: str
    author: Optional[str] = "api"

router = APIRouter(prefix="/agents", tags=["agents"])


def _resolve_agent_git_bindings(agent) -> list[AgentGitBindingResolved]:
    store = get_git_provider_store()
    resolved: list[AgentGitBindingResolved] = []
    for binding in agent.git_bindings:
        connection = store.get_connection(binding.connection_id)
        if connection is None:
            continue
        repo = store.get_repo(binding.connection_id, binding.repo_full_name)
        if repo is None:
            continue
        resolved.append(
            AgentGitBindingResolved(
                connection_id=connection.id,
                connection_name=connection.name,
                provider=connection.provider,
                repo_full_name=repo.full_name,
                repo_web_url=repo.web_url,
                default_branch=repo.default_branch,
                enabled=binding.enabled,
                can_push=binding.can_push,
                can_open_pr=binding.can_open_pr,
                branch_prefix=binding.branch_prefix,
                connection_status=connection.status,
            )
        )
    return resolved


def _resolve_agent_mcp_tool_bindings(agent) -> list[AgentMcpToolBindingResolved]:
    store = get_mcp_connection_store()
    resolved: list[AgentMcpToolBindingResolved] = []
    for binding in agent.mcp_tool_bindings:
        connection = store.get_connection(binding.connection_id)
        if connection is None:
            continue
        descriptors = {tool.name: tool for tool in store.list_tools(connection.id)}
        descriptor = descriptors.get(binding.tool_name)
        if descriptor is None:
            continue
        resolved.append(
            AgentMcpToolBindingResolved(
                connection_id=connection.id,
                connection_name=connection.name,
                tool_name=binding.tool_name,
                enabled=binding.enabled,
                alias=binding.alias,
                approval_mode=binding.approval_mode,
                description=descriptor.description,
                read_only=descriptor.read_only,
                capability_class=descriptor.capability_class,
                connection_status=connection.status,
            )
        )
    return resolved


def _to_response(a) -> AgentResponse:
    return AgentResponse(
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
        git_bindings=_resolve_agent_git_bindings(a),
        mcp_tool_bindings=_resolve_agent_mcp_tool_bindings(a),
        model_tier=a.model_tier,
        max_iter=a.max_iter,
    )


@router.get("/", response_model=list[AgentResponse])
def list_agents():
    return [_to_response(a) for a in get_agent_factory().list_agents()]


# All static paths must be declared BEFORE /{agent_id} to avoid routing conflicts

@router.get("/workspaces/all")
def list_all_workspaces():
    """List all agent workspaces with their disk usage."""
    wm = get_workspace_manager()
    return wm.list_workspaces()


@router.get("/capabilities")
def get_capabilities():
    """Return which optional capabilities are available based on configured API keys."""
    settings = get_settings()
    return {
        "web_search": has_web_search(settings),
        "github_search": has_github_access(settings),
        "model_override": has_model_override(settings),
        "mcp_connections": True,
        "git_provider_connections": True,
    }


@router.get("/{agent_id}/git-bindings", response_model=list[AgentGitBindingResolved])
def get_agent_git_bindings(agent_id: str):
    agent = get_agent_factory().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _resolve_agent_git_bindings(agent)


@router.put("/{agent_id}/git-bindings", response_model=list[AgentGitBindingResolved])
def update_agent_git_bindings(agent_id: str, body: AgentGitBindingUpdateRequest):
    factory = get_agent_factory()
    agent = factory.update_agent_git_bindings(agent_id, body.bindings)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _resolve_agent_git_bindings(agent)


@router.get("/{agent_id}/mcp-tools", response_model=list[AgentMcpToolBindingResolved])
def get_agent_mcp_tools(agent_id: str):
    agent = get_agent_factory().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _resolve_agent_mcp_tool_bindings(agent)


@router.put("/{agent_id}/mcp-tools", response_model=list[AgentMcpToolBindingResolved])
def update_agent_mcp_tools(agent_id: str, body: AgentMcpBindingUpdateRequest):
    factory = get_agent_factory()
    agent = factory.update_agent_mcp_tool_bindings(agent_id, body.bindings)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _resolve_agent_mcp_tool_bindings(agent)


def _get_global_knowledge_readiness_payload() -> GlobalKnowledgeReadiness:
    return get_knowledge_audit_service().get_global_readiness()


@router.get("/readiness/global", response_model=GlobalKnowledgeReadiness)
def get_global_knowledge_readiness():
    """Return a global summary of agent knowledge readiness."""
    return _get_global_knowledge_readiness_payload()


@router.get("/knowledge-readiness", response_model=GlobalKnowledgeReadiness)
def get_knowledge_readiness():
    """Return a global summary of agent knowledge readiness."""
    return _get_global_knowledge_readiness_payload()


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: str):
    agent = get_agent_factory().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _to_response(agent)


@router.get("/{agent_id}/knowledge-recommendations", response_model=AgentKnowledgeReadiness)
def get_agent_knowledge_recommendations(agent_id: str):
    """Return knowledge readiness and recommendations for a single agent."""
    agent = get_agent_factory().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return get_knowledge_audit_service().get_agent_readiness(agent_id)


@router.post("/{agent_id}/knowledge-recommendations/{recommendation_id}/dismiss", response_model=AgentKnowledgeReadiness)
def dismiss_agent_knowledge_recommendation(agent_id: str, recommendation_id: str):
    """Dismiss a knowledge recommendation for this agent."""
    agent = get_agent_factory().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        return get_knowledge_audit_service().dismiss_recommendation(agent_id, recommendation_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{agent_id}/knowledge-recommendations/{recommendation_id}/apply", response_model=AgentKnowledgeReadiness)
async def apply_agent_knowledge_recommendation(agent_id: str, recommendation_id: str, background_tasks: BackgroundTasks):
    """
    Apply a recommendation when it can be executed automatically.
    Currently supported: launch an autonomous web research topic.
    """
    settings = get_settings()
    if not has_web_search(settings):
        raise HTTPException(
            status_code=400,
            detail="Web search is not configured. Add SERPER_API_KEY to your .env file.",
        )

    service = get_knowledge_audit_service()
    try:
        readiness = service.get_agent_readiness(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    recommendation = next((item for item in readiness.recommendations if item.id == recommendation_id), None)
    if recommendation is None:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if recommendation.status == "dismissed":
        raise HTTPException(status_code=400, detail="Recommendation already dismissed")
    if recommendation.action_type != "launch_research":
        raise HTTPException(status_code=400, detail="This recommendation requires manual user input")
    if not recommendation.suggested_topic:
        raise HTTPException(status_code=400, detail="Recommendation has no research topic")

    manager = get_manager()
    background_tasks.add_task(run_agent_research, agent_id, recommendation.suggested_topic, manager.broadcast)
    return service.mark_recommendation_applied(agent_id, recommendation_id)


@router.get("/{agent_id}/workspace")
def get_agent_workspace(agent_id: str):
    """List the contents of an agent's workspace."""
    agent = get_agent_factory().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    wm = get_workspace_manager()
    ws = wm.get(agent_id, agent.name, agent.title)
    return ws.info()


@router.get("/{agent_id}/workspace/browse")
def browse_agent_workspace(agent_id: str, path: str = "."):
    """Browse a specific sub-directory of an agent's workspace."""
    agent = get_agent_factory().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    wm = get_workspace_manager()
    ws = wm.get(agent_id, agent.name, agent.title)
    try:
        return {"path": path, "entries": ws.list_dir(path)}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/{agent_id}/workspace/read")
def read_workspace_file(agent_id: str, path: str):
    """Read a text file from the agent's workspace."""
    agent = get_agent_factory().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    wm = get_workspace_manager()
    ws = wm.get(agent_id, agent.name, agent.title)
    try:
        content = ws.read(path)
        return {"path": path, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.patch("/{agent_id}/model")
def update_agent_model(agent_id: str, body: AgentModelUpdate):
    """Switch an agent between Sonnet and Opus tiers."""
    factory = get_agent_factory()
    agent = factory.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.model_tier = body.model_tier
    factory._save()
    get_knowledge_audit_service().invalidate_agent(agent_id)
    return _to_response(agent)


@router.get("/{agent_id}/skills")
def list_agent_skills(agent_id: str):
    """List all skills in an agent's skills/ directory."""
    agent = get_agent_factory().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    wm = get_workspace_manager()
    ws = wm.get(agent_id, agent.name, agent.title)
    return {"agent_id": agent_id, "agent_name": agent.name, "skills": ws.list_skills()}


@router.get("/{agent_id}/skills/{skill_name}")
def get_agent_skill(agent_id: str, skill_name: str):
    """Read a specific skill from an agent's skills/ directory."""
    agent = get_agent_factory().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    wm = get_workspace_manager()
    ws = wm.get(agent_id, agent.name, agent.title)
    content = ws.read_skill(skill_name)
    if content is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
    return {"agent_id": agent_id, "skill_name": skill_name, "content": content}


@router.put("/{agent_id}/skills/{skill_name}")
def write_agent_skill(agent_id: str, skill_name: str, body: SkillWrite):
    """Write or update a skill for an agent (e.g. authored by Alex via the API)."""
    agent = get_agent_factory().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if skill_name.strip().lower() == "project_context":
        raise HTTPException(
            status_code=400,
            detail="project_context is reserved for the project briefing pipeline",
        )
    wm = get_workspace_manager()
    ws = wm.get(agent_id, agent.name, agent.title)
    path = ws.write_skill(skill_name, body.content, author=body.author or "api")
    get_knowledge_audit_service().invalidate_agent(agent_id)
    return {"ok": True, "path": str(path), "skill_name": skill_name}


@router.delete("/{agent_id}/skills/{skill_name}")
def delete_agent_skill(agent_id: str, skill_name: str):
    """Delete a skill from an agent's skills/ directory."""
    agent = get_agent_factory().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    wm = get_workspace_manager()
    ws = wm.get(agent_id, agent.name, agent.title)
    skill_path = ws.skills / f"{skill_name}.md"
    if not skill_path.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
    skill_path.unlink()
    get_knowledge_audit_service().invalidate_agent(agent_id)
    return {"ok": True}


class ResearchRequest(BaseModel):
    topic: str


KNOWLEDGE_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv", ".json", ".yaml", ".yml"}
KNOWLEDGE_MAX_FILE_SIZE = 20 * 1024 * 1024


@router.post("/{agent_id}/knowledge")
async def add_agent_knowledge(
    agent_id: str,
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(default=None),
    url: Optional[str] = Form(default=None),
    description: str = Form(default=""),
):
    """
    Share a document (PDF, DOCX…) or a URL directly with a specific agent.
    Updates the agent's project_context.md and saves the source to workspace/downloads/.
    """
    factory = get_agent_factory()
    agent = factory.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not file and not url:
        raise HTTPException(status_code=400, detail="Provide either a file or a url")

    from pathlib import Path as _Path
    wm = get_workspace_manager()
    workspace = wm.get(agent_id, agent.name, agent.title)

    if file:
        ext = _Path(file.filename or "").suffix.lower()
        if ext not in KNOWLEDGE_ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported format '{ext}'")
        raw = await file.read()
        if len(raw) > KNOWLEDGE_MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large (max 20 MB)")
        # Save to workspace/downloads/
        dest = workspace.downloads / (file.filename or "document")
        dest.write_bytes(raw)
        # Extract text using DocumentStore helpers
        from app.core.document_store import get_document_store
        doc_store = get_document_store()
        text = doc_store._extract_text(dest, ext, raw)
        source_name = file.filename or "document"
    else:
        # Fetch URL content
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                raw_text = resp.text
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not fetch URL: {e}")

        # Try to extract readable text (strip HTML tags if needed)
        try:
            from html.parser import HTMLParser

            class _MLStripper(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.fed: list[str] = []
                def handle_data(self, d: str):
                    self.fed.append(d)
                def get_data(self):
                    return " ".join(self.fed)

            stripper = _MLStripper()
            stripper.feed(raw_text)
            text = stripper.get_data()
        except Exception:
            text = raw_text

        # Sanitize URL to filename
        import re
        slug = re.sub(r"[^\w\-.]", "_", (url or "url").split("//")[-1])[:80]
        dest = workspace.downloads / f"{slug}.txt"
        dest.write_text(text[:50000], encoding="utf-8")
        source_name = url or "url"

    manager = get_manager()
    background_tasks.add_task(run_targeted_rebriefing, agent_id, text, source_name, manager.broadcast)
    get_knowledge_audit_service().invalidate_agent(agent_id)
    return {"ok": True, "source": source_name, "chars": len(text)}


@router.post("/{agent_id}/research")
async def launch_agent_research(agent_id: str, body: ResearchRequest, background_tasks: BackgroundTasks):
    """
    Launch an autonomous web research session for the agent on the given topic.
    Requires SERPER_API_KEY to be configured.
    """
    settings = get_settings()
    if not has_web_search(settings):
        raise HTTPException(
            status_code=400,
            detail="Web search is not configured. Add SERPER_API_KEY to your .env file.",
        )
    factory = get_agent_factory()
    agent = factory.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    from app.core.learning import run_agent_research
    from app.api.websocket_manager import get_manager
    manager = get_manager()
    background_tasks.add_task(run_agent_research, agent_id, body.topic, manager.broadcast)
    get_knowledge_audit_service().invalidate_agent(agent_id)
    return {"ok": True, "topic": body.topic}


@router.delete("/{agent_id}")
def delete_agent(agent_id: str):
    factory = get_agent_factory()
    agent = factory.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    wm = get_workspace_manager()
    wm.delete_workspace(agent_id)
    factory.delete_agent(agent_id)
    get_knowledge_audit_service().invalidate_agent(agent_id)
    return {"ok": True}


@router.get("/{agent_id}/learning-profile", response_model=AgentLearningProfile)
def get_learning_profile(agent_id: str):
    """Get the learning profile for an agent: task count, quality, learnings, progression."""
    import json
    import re

    factory = get_agent_factory()
    agent = factory.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    wm = get_workspace_manager()
    workspace = wm.get(agent.id, agent.name, agent.title)

    # Read agent stats
    completed_task_nodes = 0
    last_reflection_at = None
    stats_path = workspace.skills / "agent_stats.json"
    if stats_path.exists():
        try:
            stats = json.loads(stats_path.read_text(encoding="utf-8"))
            completed_task_nodes = stats.get("completed_task_nodes", 0)
            last_reflection_at = stats.get("last_reflection_at")
        except Exception:
            pass

    # Read last 5 learnings from work_learnings.md
    last_5_learnings: list[str] = []
    work_learnings = workspace.read_skill("work_learnings")
    if work_learnings:
        for line in work_learnings.splitlines():
            stripped = line.strip()
            if stripped.startswith(("-", "*", "•")) and len(stripped) > 12:
                item = stripped.lstrip("-*• ").strip()
                if item.lower().startswith(("insight:", "caution:")):
                    item = item.split(":", 1)[1].strip()
                last_5_learnings.append(item)
                if len(last_5_learnings) >= 5:
                    break

    # Compute avg quality from episodes
    avg_quality_score = None
    episode_count = 0
    episodes = workspace.read_skill("episodes")
    if episodes:
        quality_scores: list[int] = []
        for match in re.finditer(r"\*\*Quality:\*\*\s*(\d+)/100", episodes):
            quality_scores.append(int(match.group(1)))
            episode_count += 1
        if quality_scores:
            avg_quality_score = round(sum(quality_scores) / len(quality_scores), 1)

    # Readiness score (from cached audit if available)
    readiness_score = None

    # Progression level
    if completed_task_nodes >= 8:
        progression_level = "expert"
    elif completed_task_nodes >= 3:
        progression_level = "operationnel"
    else:
        progression_level = "apprenti"

    return AgentLearningProfile(
        agent_id=agent_id,
        completed_task_nodes=completed_task_nodes,
        avg_quality_score=avg_quality_score,
        last_5_learnings=last_5_learnings,
        readiness_score=readiness_score,
        progression_level=progression_level,
        last_reflection_at=last_reflection_at,
        episode_count=episode_count,
    )


@router.post("/{agent_id}/reflect")
async def trigger_reflection(agent_id: str, background_tasks: BackgroundTasks):
    """Manually trigger a periodic reflection for an agent."""
    agent = get_agent_factory().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    manager = get_manager()
    background_tasks.add_task(run_agent_reflection, agent, manager.broadcast)
    return {"status": "reflection_started", "agent_id": agent_id}
