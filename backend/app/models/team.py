from pydantic import BaseModel, Field
from typing import Optional
import uuid
from .agent import AgentResponse


class TeamConfig(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str
    domain: str
    lead_agent_id: Optional[str] = None
    scope_note: str = ""
    agent_ids: list[str] = Field(default_factory=list)


class TeamResponse(BaseModel):
    id: str
    name: str
    description: str
    domain: str
    lead_agent_id: Optional[str] = None
    scope_note: str = ""
    agents: list[AgentResponse] = []


class OrganigrammeNode(BaseModel):
    id: str
    name: str
    title: str
    role: str
    status: str
    occupancy_status: str = "idle"
    occupancy_reason: Optional[str] = None
    current_task_id: Optional[str] = None
    current_task_title: Optional[str] = None
    current_node_id: Optional[str] = None
    current_node_title: Optional[str] = None
    busy_since: Optional[str] = None
    parent_id: Optional[str] = None
    children: list["OrganigrammeNode"] = []


OrganigrammeNode.model_rebuild()
