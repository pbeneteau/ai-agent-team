import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from app.core.orchestrator import get_orchestrator
from app.api.websocket_manager import get_manager
from app.models.task import TaskResponse, TaskCreate, TaskPriority

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
async def create_and_run_task(req: TaskCreate, background_tasks: BackgroundTasks):
    orchestrator = get_orchestrator()
    manager = get_manager()
    task = orchestrator.create_task(
        title=req.title,
        description=req.description,
        priority=req.priority,
        team_id=req.assigned_team_id,
    )
    background_tasks.add_task(orchestrator.execute_task, task.id, manager.broadcast)
    return task


@router.delete("/{task_id}")
def delete_task(task_id: str):
    orchestrator = get_orchestrator()
    if not orchestrator.delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}
