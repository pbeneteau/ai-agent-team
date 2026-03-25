from fastapi import APIRouter, HTTPException

from app.api.websocket_manager import get_manager
from app.core.task_comment_store import get_task_comment_store
from app.models.task_comment import TaskCommentCreate, TaskCommentResponse

router = APIRouter(prefix="/tasks", tags=["task-comments"])


@router.get("/{task_id}/comments/", response_model=list[TaskCommentResponse])
def list_task_comments(task_id: str):
    return get_task_comment_store().list_for_task(task_id)


@router.post("/{task_id}/comments/", response_model=TaskCommentResponse)
async def create_task_comment(task_id: str, req: TaskCommentCreate):
    comment = get_task_comment_store().create_comment(task_id, req)
    await get_manager().broadcast({
        "type": "task_comment",
        "data": {"task_id": task_id, "comment": comment.model_dump()},
    })
    return comment
