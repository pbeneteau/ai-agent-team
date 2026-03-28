"""Pydantic schemas for Git provider connection endpoints.

Ref: TDD-04 Section 8.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class RepoItem(BaseModel):
    owner: str
    name: str
    full_name: str
    default_branch: str = "main"
    private: bool = False
    webhook_configured: bool = False


class GitConnectionItem(BaseModel):
    id: str
    provider: str
    display_name: str
    status: str
    repositories: list[dict] = Field(default_factory=list)
    last_verified_at: datetime | None = None
    created_at: datetime


class CreateGitConnectionRequest(BaseModel):
    provider: str = Field(..., pattern="^(github|gitlab)$")
    display_name: str = Field(..., min_length=1, max_length=255)
    access_token: str = Field(..., min_length=1)


class TestConnectionResponse(BaseModel):
    ok: bool
    user: str
    scopes: list[str] = Field(default_factory=list)
    rate_limit_remaining: int | None = None


class RepoListResponse(BaseModel):
    items: list[RepoItem]


class WebhookConfiguredResponse(BaseModel):
    webhook_id: int
    webhook_url: str
    events: list[str]
    status: str = "active"
