from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.websocket_manager import get_manager
from app.core.label_store import get_label_store
from app.models.label import LabelCreate, LabelResponse

router = APIRouter(prefix="/labels", tags=["labels"])


class LabelUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    group: Optional[str] = None
    description: Optional[str] = None


@router.get("/", response_model=list[LabelResponse])
def list_labels():
    return get_label_store().list_labels()


@router.post("/", response_model=LabelResponse)
async def create_label(req: LabelCreate):
    label = get_label_store().create_label(req)
    await get_manager().broadcast({"type": "label_created", "data": label.model_dump()})
    return label


@router.patch("/{label_id}", response_model=LabelResponse)
async def update_label(label_id: str, req: LabelUpdate):
    label = get_label_store().update_label(label_id, **req.model_dump(exclude_none=True))
    if not label:
        raise HTTPException(status_code=404, detail="Label not found")
    await get_manager().broadcast({"type": "label_updated", "data": label.model_dump()})
    return label


@router.delete("/{label_id}")
async def delete_label(label_id: str):
    from app.core.orchestrator import get_orchestrator

    store = get_label_store()
    if not store.get_label(label_id):
        raise HTTPException(status_code=404, detail="Label not found")

    # Remove label from all tasks that reference it
    orchestrator = get_orchestrator()
    for task in orchestrator.list_tasks():
        if label_id in task.labels:
            orchestrator.patch_task(task.id, labels=[l for l in task.labels if l != label_id])

    store.delete_label(label_id)
    await get_manager().broadcast({"type": "label_deleted", "data": {"id": label_id}})
    return {"ok": True}
