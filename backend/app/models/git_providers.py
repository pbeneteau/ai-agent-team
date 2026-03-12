from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class GitProvider(str, Enum):
    GITHUB = "github"
    GITLAB = "gitlab"


class GitProviderConnectionStatus(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class GitProviderAuthMode(str, Enum):
    PERSONAL_ACCESS_TOKEN = "personal_access_token"


class GitRepoPermission(str, Enum):
    READ = "read"
    PUSH = "push"
    OPEN_PR = "open_pr"


class GitRemoteRepo(BaseModel):
    full_name: str
    owner: str
    name: str
    web_url: str
    clone_url: str
    default_branch: str = "main"


class GitProviderConnectionConfig(BaseModel):
    id: str
    provider: GitProvider
    name: str
    base_url: HttpUrl
    auth_mode: GitProviderAuthMode = GitProviderAuthMode.PERSONAL_ACCESS_TOKEN
    auth_token: str = ""
    enabled: bool = True
    notes: str = ""
    discovered_repos: list[GitRemoteRepo] = Field(default_factory=list)
    status: GitProviderConnectionStatus = GitProviderConnectionStatus.UNKNOWN
    last_tested_at: Optional[str] = None
    last_error: Optional[str] = None
    total_repo_actions: int = 0
    clone_actions: int = 0
    push_actions: int = 0
    pull_request_actions: int = 0
    last_action_at: Optional[str] = None


class GitProviderConnectionResponse(BaseModel):
    id: str
    provider: GitProvider
    name: str
    base_url: HttpUrl
    auth_mode: GitProviderAuthMode
    has_auth_token: bool
    enabled: bool
    notes: str
    discovered_repos: list[GitRemoteRepo]
    status: GitProviderConnectionStatus
    last_tested_at: Optional[str] = None
    last_error: Optional[str] = None
    total_repo_actions: int = 0
    clone_actions: int = 0
    push_actions: int = 0
    pull_request_actions: int = 0
    last_action_at: Optional[str] = None


class GitProviderConnectionCreateRequest(BaseModel):
    provider: GitProvider
    name: str
    base_url: Optional[HttpUrl] = None
    auth_token: str = ""
    enabled: bool = True
    notes: str = ""


class GitProviderConnectionUpdateRequest(BaseModel):
    name: Optional[str] = None
    base_url: Optional[HttpUrl] = None
    auth_token: Optional[str] = None
    clear_auth_token: bool = False
    enabled: Optional[bool] = None
    notes: Optional[str] = None


class GitProviderTestResult(BaseModel):
    ok: bool
    status: GitProviderConnectionStatus
    account_name: Optional[str] = None
    account_username: Optional[str] = None
    repo_count: int = 0
    error: Optional[str] = None


class AgentGitBinding(BaseModel):
    connection_id: str
    repo_full_name: str
    enabled: bool = True
    can_push: bool = False
    can_open_pr: bool = False
    branch_prefix: str = "agent"


class AgentGitBindingResolved(BaseModel):
    connection_id: str
    connection_name: str
    provider: GitProvider
    repo_full_name: str
    repo_web_url: str
    default_branch: str
    enabled: bool = True
    can_push: bool = False
    can_open_pr: bool = False
    branch_prefix: str = "agent"
    connection_status: GitProviderConnectionStatus = GitProviderConnectionStatus.UNKNOWN


class AgentGitBindingUpdateRequest(BaseModel):
    bindings: list[AgentGitBinding] = Field(default_factory=list)


class GitProviderUsageSummary(BaseModel):
    total_connections: int = 0
    healthy_connections: int = 0
    degraded_connections: int = 0
    unavailable_connections: int = 0
    total_repo_actions: int = 0
    clone_actions: int = 0
    push_actions: int = 0
    pull_request_actions: int = 0
    connections: list[GitProviderConnectionResponse] = Field(default_factory=list)
