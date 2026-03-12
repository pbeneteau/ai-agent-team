from typing import Any

import httpx

from app.config.tool_runtime import GIT_PROVIDER_API_TIMEOUT_SECONDS
from app.core.git_providers.common import GitProviderClientError, GitProviderPullRequestResult
from app.models.git_providers import GitProviderConnectionConfig, GitProviderTestResult, GitRemoteRepo


class GitHubProviderHandler:
    def _headers(self, connection: GitProviderConnectionConfig) -> dict[str, str]:
        token = connection.auth_token.strip()
        if not token:
            raise GitProviderClientError("GitHub connection requires a personal access token.")
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(
        self,
        connection: GitProviderConnectionConfig,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{str(connection.base_url).rstrip('/')}{path}"
        with httpx.Client(timeout=GIT_PROVIDER_API_TIMEOUT_SECONDS) as client:
            response = client.request(method, url, headers=self._headers(connection), params=params, json=json_body)
        if response.status_code >= 400:
            raise GitProviderClientError(f"GitHub API error {response.status_code}: {response.text}")
        return response.json()

    def test_connection(self, connection: GitProviderConnectionConfig) -> GitProviderTestResult:
        try:
            user = self._request(connection, "GET", "/user")
            repos = self._request(
                connection,
                "GET",
                "/user/repos",
                params={"per_page": 100, "sort": "updated", "affiliation": "owner,collaborator,organization_member"},
            )
            return GitProviderTestResult(
                ok=True,
                status="healthy",
                account_name=user.get("name"),
                account_username=user.get("login"),
                repo_count=len(repos) if isinstance(repos, list) else 0,
            )
        except Exception as exc:
            return GitProviderTestResult(ok=False, status="unavailable", error=str(exc))

    def list_repos(self, connection: GitProviderConnectionConfig) -> list[GitRemoteRepo]:
        repos = self._request(
            connection,
            "GET",
            "/user/repos",
            params={"per_page": 100, "sort": "updated", "affiliation": "owner,collaborator,organization_member"},
        )
        if not isinstance(repos, list):
            return []
        normalized: list[GitRemoteRepo] = []
        for repo in repos:
            owner = (repo.get("owner") or {}).get("login")
            name = repo.get("name")
            full_name = repo.get("full_name")
            clone_url = repo.get("clone_url")
            html_url = repo.get("html_url")
            if not owner or not name or not full_name or not clone_url or not html_url:
                continue
            normalized.append(
                GitRemoteRepo(
                    full_name=full_name,
                    owner=owner,
                    name=name,
                    web_url=html_url,
                    clone_url=clone_url,
                    default_branch=repo.get("default_branch") or "main",
                )
            )
        return normalized

    def create_pull_request(
        self,
        connection: GitProviderConnectionConfig,
        *,
        repo: GitRemoteRepo,
        title: str,
        body: str,
        source_branch: str,
        target_branch: str,
    ) -> GitProviderPullRequestResult:
        result = self._request(
            connection,
            "POST",
            f"/repos/{repo.owner}/{repo.name}/pulls",
            json_body={
                "title": title,
                "body": body,
                "head": source_branch,
                "base": target_branch,
            },
        )
        return GitProviderPullRequestResult(number=int(result.get("number", 0)), web_url=str(result.get("html_url", "")))

    def fetch_pull_request_context(
        self,
        connection: GitProviderConnectionConfig,
        *,
        repo: GitRemoteRepo,
        number: int | None = None,
    ) -> str:
        if number is not None and number > 0:
            result = self._request(connection, "GET", f"/repos/{repo.owner}/{repo.name}/pulls/{number}")
            return (
                f"PR #{result.get('number')}: {result.get('title')}\n"
                f"State: {result.get('state')}\n"
                f"URL: {result.get('html_url')}\n"
                f"Body:\n{result.get('body') or ''}"
            )
        pulls = self._request(connection, "GET", f"/repos/{repo.owner}/{repo.name}/pulls", params={"state": "open", "per_page": 20})
        if not isinstance(pulls, list) or not pulls:
            return "No open pull requests."
        lines = []
        for item in pulls[:10]:
            lines.append(
                f"PR #{item.get('number')}: {item.get('title')} [{item.get('state')}] {item.get('html_url')}"
            )
        return "\n".join(lines)
