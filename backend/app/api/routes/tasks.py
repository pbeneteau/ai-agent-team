from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from app.core.orchestrator import get_orchestrator
from app.api.websocket_manager import get_manager
from app.models.task import TaskCreate, TaskDeliverable, TaskResponse

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/", response_model=list[TaskResponse])
def list_tasks():
    return get_orchestrator().list_tasks()


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str):
    task = get_orchestrator().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/", response_model=TaskResponse)
async def create_task(req: TaskCreate):
    orchestrator = get_orchestrator()
    task = orchestrator.create_task(
        title=req.title,
        description=req.description,
        priority=req.priority,
        team_id=req.assigned_team_id,
        assigned_agent_id=req.assigned_agent_id,
        execution_mode=req.execution_mode,
        context_document_ids=req.context_document_ids,
    )
    return task


@router.post("/{task_id}/execute", response_model=TaskResponse)
async def execute_task(task_id: str, background_tasks: BackgroundTasks):
    orchestrator = get_orchestrator()
    manager = get_manager()
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        orchestrator.ensure_task_execution_eligible(task)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(orchestrator.execute_task, task.id, manager.broadcast)
    return task


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    orchestrator = get_orchestrator()
    manager = get_manager()
    try:
        deleted = orchestrator.delete_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    await manager.broadcast({"type": "task_deleted", "data": {"id": task_id}})
    return {"ok": True}


@router.get("/{task_id}/deliverables", response_model=list[TaskDeliverable])
def list_task_deliverables(task_id: str):
    orchestrator = get_orchestrator()
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return orchestrator.list_task_deliverables(task_id)


@router.get("/{task_id}/deliverables/read")
def read_task_deliverable(task_id: str, path: str):
    orchestrator = get_orchestrator()
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        return orchestrator.read_task_deliverable(task_id, path)
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{task_id}/deliverables/download")
def download_task_deliverable(task_id: str, path: str):
    orchestrator = get_orchestrator()
    task = orchestrator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        deliverable_path = orchestrator.get_task_deliverable_path(task_id, path)
        return FileResponse(
            deliverable_path,
            filename=deliverable_path.name,
            media_type="application/octet-stream",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
