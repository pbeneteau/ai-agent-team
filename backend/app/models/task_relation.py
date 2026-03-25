from enum import Enum

from pydantic import BaseModel


class RelationType(str, Enum):
    BLOCKS = "blocks"
    RELATED = "related"
    DUPLICATE = "duplicate"


class TaskRelationCreate(BaseModel):
    type: RelationType
    source_task_id: str
    target_task_id: str


class TaskRelationResponse(BaseModel):
    id: str
    type: RelationType
    source_task_id: str
    target_task_id: str
    created_at: str = ""
