from typing import Any
from urllib.parse import quote

import httpx

from app.config.tool_runtime import GIT_PROVIDER_API_TIMEOUT_SECONDS
from app.core.git_providers.common import GitProviderClientError, GitProviderPullRequestResult
from app.models.git_providers import GitProviderConnectionConfig, GitProviderTestResult, GitRemoteRepo


class GitLabProviderHandler:
    def _headers(self, connection: GitProviderConnectionConfig) -> dict[str, str]:
        token = connection.auth_token.strip()
        if not token:
            raise GitProviderClientError("GitLab connection requires a personal access token.")
        return {"PRIVATE-TOKEN": token}

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
            raise GitProviderClientError(f"GitLab API error {response.status_code}: {response.text}")
        return response.json()

    def test_connection(self, connection: GitProviderConnectionConfig) -> GitProviderTestResult:
        try:
            user = self._request(connection, "GET", "/user")
            repos = self._request(connection, "GET", "/projects", params={"membership": True, "per_page": 100, "simple": True})
            return GitProviderTestResult(
                ok=True,
                status="healthy",
                account_name=user.get("name"),
                account_username=user.get("username"),
                repo_count=len(repos) if isinstance(repos, list) else 0,
            )
        except Exception as exc:
            return GitProviderTestResult(ok=False, status="unavailable", error=str(exc))

    def list_repos(self, connection: GitProviderConnectionConfig) -> list[GitRemoteRepo]:
        projects = self._request(connection, "GET", "/projects", params={"membership": True, "per_page": 100, "simple": True})
        if not isinstance(projects, list):
            return []
        normalized: list[GitRemoteRepo] = []
        for project in projects:
            path_with_namespace = project.get("path_with_namespace")
            name = project.get("path") or project.get("name")
            http_url = project.get("http_url_to_repo")
            web_url = project.get("web_url")
            default_branch = project.get("default_branch") or "main"
            if not path_with_namespace or not name or not http_url or not web_url:
                continue
            owner = path_with_namespace.rsplit("/", 1)[0]
            normalized.append(
                GitRemoteRepo(
                    full_name=path_with_namespace,
                    owner=owner,
                    name=name,
                    web_url=web_url,
                    clone_url=http_url,
                    default_branch=default_branch,
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
        project_id = quote(repo.full_name, safe="")
        result = self._request(
            connection,
            "POST",
            f"/projects/{project_id}/merge_requests",
            json_body={
                "title": title,
                "description": body,
                "source_branch": source_branch,
                "target_branch": target_branch,
            },
        )
        return GitProviderPullRequestResult(
            number=int(result.get("iid", 0)),
            web_url=str(result.get("web_url", "")),
        )

    def fetch_pull_request_context(
        self,
        connection: GitProviderConnectionConfig,
        *,
        repo: GitRemoteRepo,
        number: int | None = None,
    ) -> str:
        project_id = quote(repo.full_name, safe="")
        if number is not None and number > 0:
            result = self._request(connection, "GET", f"/projects/{project_id}/merge_requests/{number}")
            return (
                f"MR !{result.get('iid')}: {result.get('title')}\n"
                f"State: {result.get('state')}\n"
                f"URL: {result.get('web_url')}\n"
                f"Body:\n{result.get('description') or ''}"
            )
        merge_requests = self._request(
            connection,
            "GET",
            f"/projects/{project_id}/merge_requests",
            params={"state": "opened", "per_page": 20},
        )
        if not isinstance(merge_requests, list) or not merge_requests:
            return "No open merge requests."
        lines = []
        for item in merge_requests[:10]:
            lines.append(
                f"MR !{item.get('iid')}: {item.get('title')} [{item.get('state')}] {item.get('web_url')}"
            )
        return "\n".join(lines)
