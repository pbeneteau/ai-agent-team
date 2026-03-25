from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.websocket_manager import get_manager
from app.core.project_store import get_project_store
from app.models.project import ProjectCreate, ProjectResponse, ProjectStatus

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    lead_agent_id: Optional[str] = None
    default_team_id: Optional[str] = None
    target_date: Optional[str] = None
    sort_order: Optional[float] = None


@router.get("/", response_model=list[ProjectResponse])
def list_projects():
    return get_project_store().list_projects()


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str):
    project = get_project_store().get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/", response_model=ProjectResponse)
async def create_project(req: ProjectCreate):
    project = get_project_store().create_project(req)
    await get_manager().broadcast({"type": "project_created", "data": project.model_dump()})
    return project


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, req: ProjectUpdate):
    project = get_project_store().update_project(
        project_id, **req.model_dump(exclude_none=True)
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await get_manager().broadcast({"type": "project_updated", "data": project.model_dump()})
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    from app.core.orchestrator import get_orchestrator

    store = get_project_store()
    if not store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    # Orphan tasks — remove project_id reference without deleting tasks
    orchestrator = get_orchestrator()
    for task in orchestrator.list_tasks():
        if task.project_id == project_id:
            orchestrator.patch_task(task.id, project_id=None)

    store.delete_project(project_id)
    await get_manager().broadcast({"type": "project_deleted", "data": {"id": project_id}})
    return {"ok": True}
