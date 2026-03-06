from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from typing import Optional
from app.config import get_settings
from app.core.agent_factory import get_agent_factory
from app.core.workspace import get_workspace_manager
from app.models.agent import AgentResponse, AgentModelUpdate, ModelTier


class SkillWrite(BaseModel):
    content: str
    author: Optional[str] = "api"

router = APIRouter(prefix="/agents", tags=["agents"])


def _to_response(a) -> AgentResponse:
    return AgentResponse(
        id=a.id,
        name=a.name,
        role=a.role,
        title=a.title,
        specialization=a.specialization,
        status=a.status,
        team_id=a.team_id,
        parent_id=a.parent_id,
        workspace_path=a.workspace_path,
        tools=a.tools,
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
        "web_search": bool(settings.serper_api_key),
    }


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: str):
    agent = get_agent_factory().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _to_response(agent)


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
    wm = get_workspace_manager()
    ws = wm.get(agent_id, agent.name, agent.title)
    path = ws.write_skill(skill_name, body.content, author=body.author or "api")
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
    from app.core.learning import run_targeted_rebriefing
    from app.api.websocket_manager import get_manager
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
    return {"ok": True, "source": source_name, "chars": len(text)}


@router.post("/{agent_id}/research")
async def launch_agent_research(agent_id: str, body: ResearchRequest, background_tasks: BackgroundTasks):
    """
    Launch an autonomous web research session for the agent on the given topic.
    Requires SERPER_API_KEY to be configured.
    """
    settings = get_settings()
    if not settings.serper_api_key:
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
    return {"ok": True}
