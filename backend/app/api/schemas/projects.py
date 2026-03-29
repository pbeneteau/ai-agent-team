"""Pydantic schemas for project and document endpoints (TDD-04 Sections 4, 7)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class ProjectListItem(BaseModel):
    id: str
    name: str
    description: str | None = None
    primary_language: str | None = None
    framework: str | None = None
    git_repo_url: str | None = None
    artifact_count: int = 0
    brief_status: str = "none"  # "none", "draft", "published"
    created_at: datetime


class ProjectDetail(BaseModel):
    id: str
    name: str
    description: str | None = None
    primary_language: str | None = None
    framework: str | None = None
    package_manager: str | None = None
    git_repo_url: str | None = None
    has_readme: bool = False
    artifact_count: int = 0
    brief_status: str = "none"  # "none" | "draft" | "published"
    brief_draft: str | None = None
    brief_published: str | None = None
    brief_fingerprint: str | None = None
    brief_published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CreateProjectRequest(BaseModel):
    name: str
    description: str | None = None
    primary_language: str | None = None
    framework: str | None = None
    package_manager: str | None = None
    git_repo_url: str | None = None
    git_connection_id: str | None = None


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    primary_language: str | None = None
    framework: str | None = None
    package_manager: str | None = None
    git_repo_url: str | None = None


# ---------------------------------------------------------------------------
# Brief management
# ---------------------------------------------------------------------------


class BriefContext(BaseModel):
    draft: str | None = None
    published: str | None = None
    published_at: datetime | None = None
    fingerprint: str | None = None


class SaveDraftRequest(BaseModel):
    content: str


class PublishResponse(BaseModel):
    published: str
    published_at: datetime
    fingerprint: str
    agents_rebriefed: int


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


class DocumentItem(BaseModel):
    id: str
    filename: str
    mime_type: str
    size_bytes: int
    chunk_count: int
    processing_status: str
    created_at: datetime


class DocumentCreated(BaseModel):
    id: str
    filename: str
    mime_type: str
    size_bytes: int
    processing_status: str
