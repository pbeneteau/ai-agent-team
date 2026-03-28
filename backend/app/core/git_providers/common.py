"""Shared interface for GitHub and GitLab provider clients.

Both GitHubClient and GitLabClient implement the GitProviderClient protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class UserInfo:
    """Authenticated user information."""
    username: str
    scopes: list[str] = field(default_factory=list)
    rate_limit_remaining: int | None = None


@dataclass(frozen=True, slots=True)
class RepoInfo:
    """Repository metadata."""
    owner: str
    name: str
    full_name: str
    default_branch: str
    private: bool
    webhook_configured: bool = False


@dataclass(frozen=True, slots=True)
class WebhookInfo:
    """Created/updated webhook details."""
    webhook_id: int
    webhook_url: str
    events: list[str]
    status: str = "active"


@dataclass(frozen=True, slots=True)
class PullRequestInfo:
    """Created pull request details."""
    number: int
    url: str
    html_url: str


@runtime_checkable
class GitProviderClient(Protocol):
    """Protocol defining the interface all git provider clients must implement."""

    async def validate_token(self) -> UserInfo:
        """Validate the PAT and return user info with scopes.

        Raises:
            GitProviderError: If the token is invalid or has insufficient permissions.
        """
        ...

    async def list_repos(self) -> list[RepoInfo]:
        """List repositories accessible via this PAT."""
        ...

    async def create_webhook(
        self,
        owner: str,
        repo: str,
        webhook_url: str,
        webhook_secret: str,
    ) -> WebhookInfo:
        """Create a webhook on the specified repository.

        Raises:
            GitProviderError: If the PAT lacks required scopes.
        """
        ...

    async def delete_webhook(
        self,
        owner: str,
        repo: str,
        webhook_id: int,
    ) -> None:
        """Delete a webhook from the specified repository. Best-effort."""
        ...

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> PullRequestInfo:
        """Create a pull request on the specified repository."""
        ...

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        ...


class GitProviderError(Exception):
    """Base error for git provider operations."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
