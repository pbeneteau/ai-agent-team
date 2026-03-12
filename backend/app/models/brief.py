from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ProjectBriefStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class ProjectContextDraftRequest(BaseModel):
    name: str = ""
    description: str = ""
    domain: str = ""
    short_term_goal: str = ""
    tech_stack: str = ""
    target_audience: str = ""
    business_model: str = ""
    notes: str = ""


class ProjectContextPublishRequest(ProjectContextDraftRequest):
    name: str
    description: str


class ProjectBriefSnapshot(BaseModel):
    revision: int
    status: ProjectBriefStatus
    updated_at: str
    published_at: Optional[str] = None
    brief_fingerprint: str
    completeness_score: int = 0
    name: str = ""
    description: str = ""
    domain: str = ""
    short_term_goal: str = ""
    tech_stack: str = ""
    target_audience: str = ""
    business_model: str = ""
    notes: str = ""


class ProjectBriefStateResponse(BaseModel):
    draft: Optional[ProjectBriefSnapshot] = None
    published: Optional[ProjectBriefSnapshot] = None
    active: Optional[ProjectBriefSnapshot] = None
    has_unpublished_changes: bool = False


class ProjectBriefMutationResponse(BaseModel):
    ok: bool = True
    message: str
    state: ProjectBriefStateResponse
