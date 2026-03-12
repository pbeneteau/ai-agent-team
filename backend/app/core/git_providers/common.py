from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote, urlparse, urlunparse

from app.models.git_providers import (
    GitProvider,
    GitProviderConnectionConfig,
    GitProviderTestResult,
    GitRemoteRepo,
)


class GitProviderClientError(RuntimeError):
    pass


@dataclass
class GitProviderPullRequestResult:
    number: int
    web_url: str


class GitProviderHandler(Protocol):
    def test_connection(self, connection: GitProviderConnectionConfig) -> GitProviderTestResult: ...
    def list_repos(self, connection: GitProviderConnectionConfig) -> list[GitRemoteRepo]: ...
    def create_pull_request(
        self,
        connection: GitProviderConnectionConfig,
        *,
        repo: GitRemoteRepo,
        title: str,
        body: str,
        source_branch: str,
        target_branch: str,
    ) -> GitProviderPullRequestResult: ...
    def fetch_pull_request_context(
        self,
        connection: GitProviderConnectionConfig,
        *,
        repo: GitRemoteRepo,
        number: int | None = None,
    ) -> str: ...


def get_provider_display_name(provider: GitProvider) -> str:
    if provider == GitProvider.GITHUB:
        return "GitHub"
    if provider == GitProvider.GITLAB:
        return "GitLab"
    return provider.value


def _inject_basic_credentials(url: str, username: str, password: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    netloc = f"{quote(username, safe='')}:{quote(password, safe='')}@{host}"
    return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def get_authenticated_clone_url(connection: GitProviderConnectionConfig, clone_url: str) -> str:
    token = connection.auth_token.strip()
    if not token:
        raise GitProviderClientError("No auth token configured for this git provider connection.")
    if connection.provider == GitProvider.GITHUB:
        return _inject_basic_credentials(clone_url, "x-access-token", token)
    if connection.provider == GitProvider.GITLAB:
        return _inject_basic_credentials(clone_url, "oauth2", token)
    raise GitProviderClientError(f"Unsupported git provider: {connection.provider.value}")


def get_provider_handler(provider: GitProvider) -> GitProviderHandler:
    if provider == GitProvider.GITHUB:
        from .github import GitHubProviderHandler

        return GitHubProviderHandler()
    if provider == GitProvider.GITLAB:
        from .gitlab import GitLabProviderHandler

        return GitLabProviderHandler()
    raise GitProviderClientError(f"Unsupported git provider: {provider.value}")
