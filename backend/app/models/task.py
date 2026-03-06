from enum import Enum
from pydantic import BaseModel
from typing import Optional
import uuid


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskCreate(BaseModel):
    title: str
    description: str
    priority: TaskPriority = TaskPriority.MEDIUM
    assigned_team_id: Optional[str] = None


class TaskResponse(BaseModel):
    id: str
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    assigned_team_id: Optional[str] = None
    assigned_agent_ids: list[str] = []
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str
    progress_log: list[dict] = []


class TaskUpdate(BaseModel):
    status: Optional[TaskStatus] = None
    result: Optional[str] = None
    error: Optional[str] = None
    progress_entry: Optional[dict] = None
