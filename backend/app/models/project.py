from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ProjectStatus(str, Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    color: str = "#6366f1"
    icon: Optional[str] = None
    default_team_id: Optional[str] = None
    target_date: Optional[str] = None


class ProjectResponse(BaseModel):
    id: str
    identifier: str = ""
    name: str
    description: Optional[str] = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    color: str = "#6366f1"
    icon: Optional[str] = None
    lead_agent_id: Optional[str] = None
    default_team_id: Optional[str] = None
    labels: list[str] = Field(default_factory=list)
    target_date: Optional[str] = None
    sort_order: float = 0.0
    created_at: str = ""
    updated_at: str = ""
    total_estimated_cost_usd: float = 0.0
    total_actual_cost_usd: float = 0.0
