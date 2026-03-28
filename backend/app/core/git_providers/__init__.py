from app.core.git_providers.common import GitProviderClient, RepoInfo, UserInfo, WebhookInfo
from app.core.git_providers.github import GitHubClient
from app.core.git_providers.gitlab import GitLabClient

__all__ = [
    "GitProviderClient",
    "RepoInfo",
    "UserInfo",
    "WebhookInfo",
    "GitHubClient",
    "GitLabClient",
    "get_client",
]


def get_client(provider: str, access_token: str) -> GitProviderClient:
    """Factory: return the correct provider client for the given provider string."""
    if provider == "github":
        return GitHubClient(access_token)
    elif provider == "gitlab":
        return GitLabClient(access_token)
    else:
        raise ValueError(f"Unknown git provider: {provider!r}")
