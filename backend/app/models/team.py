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


