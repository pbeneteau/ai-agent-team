from fastapi import APIRouter, HTTPException

from app.api.websocket_manager import get_manager
from app.core.task_relation_store import get_task_relation_store
from app.models.task_relation import RelationType, TaskRelationCreate, TaskRelationResponse

router = APIRouter(prefix="/tasks", tags=["task-relations"])


@router.get("/{task_id}/relations/", response_model=list[TaskRelationResponse])
def list_task_relations(task_id: str):
    return get_task_relation_store().list_for_task(task_id)


@router.post("/{task_id}/relations/", response_model=TaskRelationResponse)
async def create_task_relation(task_id: str, req: TaskRelationCreate):
    # Validate no self-relation
    if req.source_task_id == req.target_task_id:
        raise HTTPException(status_code=400, detail="A task cannot be related to itself.")

    # Ensure the task_id matches source or target
    if task_id not in (req.source_task_id, req.target_task_id):
        raise HTTPException(
            status_code=400,
            detail="task_id must match source_task_id or target_task_id.",
        )

    store = get_task_relation_store()

    # Check for duplicate
    existing = store.list_for_task(task_id)
    for rel in existing:
        if (
            rel.type == req.type
            and rel.source_task_id == req.source_task_id
            and rel.target_task_id == req.target_task_id
        ):
            raise HTTPException(status_code=409, detail="Relation already exists.")

    # Circular blocks check: A blocks B — reject if B already blocks A
    if req.type == RelationType.BLOCKS:
        for rel in existing:
            if (
                rel.type == RelationType.BLOCKS
                and rel.source_task_id == req.target_task_id
                and rel.target_task_id == req.source_task_id
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Circular blocking relation detected.",
                )

    relation = store.create_relation(req)
    await get_manager().broadcast({"type": "task_relation_created", "data": relation.model_dump()})
    return relation


@router.delete("/{task_id}/relations/{relation_id}")
async def delete_task_relation(task_id: str, relation_id: str):
    store = get_task_relation_store()
    deleted = store.delete_relation(relation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Relation not found.")
    await get_manager().broadcast({"type": "task_relation_deleted", "data": {"id": relation_id, "task_id": task_id}})
    return {"ok": True}
