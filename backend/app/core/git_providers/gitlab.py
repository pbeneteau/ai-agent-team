"""GitLab API client using httpx + PAT auth.

Implements the GitProviderClient protocol for GitLab.
"""

from __future__ import annotations

import logging
from urllib.parse import quote

import httpx

from app.core.git_providers.common import (
    GitProviderError,
    PullRequestInfo,
    RepoInfo,
    UserInfo,
    WebhookInfo,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://gitlab.com/api/v4"


class GitLabClient:
    """GitLab API client using a Personal Access Token."""

    def __init__(self, access_token: str) -> None:
        self._token = access_token
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={
                "PRIVATE-TOKEN": access_token,
            },
            timeout=30.0,
        )

    def _project_path(self, owner: str, repo: str) -> str:
        """URL-encode the project path for GitLab API."""
        return quote(f"{owner}/{repo}", safe="")

    async def validate_token(self) -> UserInfo:
        """Validate PAT by calling GET /user and reading token scopes."""
        resp = await self._client.get("/user")
        if resp.status_code == 401:
            raise GitProviderError("Invalid GitLab token", status_code=401)
        if resp.status_code != 200:
            raise GitProviderError(
                f"GitLab API error: {resp.status_code} {resp.text}",
                status_code=resp.status_code,
            )

        data = resp.json()

        # GitLab PAT scopes are available via GET /personal_access_tokens/self
        scopes: list[str] = []
        try:
            scopes_resp = await self._client.get("/personal_access_tokens/self")
            if scopes_resp.status_code == 200:
                scopes = scopes_resp.json().get("scopes", [])
        except Exception:
            pass

        return UserInfo(
            username=data.get("username", ""),
            scopes=scopes,
            rate_limit_remaining=None,
        )

    async def list_repos(self) -> list[RepoInfo]:
        """List projects accessible via this PAT (up to 100)."""
        repos: list[RepoInfo] = []
        page = 1

        while True:
            resp = await self._client.get(
                "/projects",
                params={
                    "membership": True,
                    "per_page": 100,
                    "page": page,
                    "order_by": "updated_at",
                    "sort": "desc",
                },
            )
            if resp.status_code != 200:
                raise GitProviderError(
                    f"Failed to list projects: {resp.status_code}",
                    status_code=resp.status_code,
                )

            data = resp.json()
            if not data:
                break

            for p in data:
                namespace = p.get("namespace", {})
                repos.append(
                    RepoInfo(
                        owner=namespace.get("path", ""),
                        name=p.get("path", ""),
                        full_name=p.get("path_with_namespace", ""),
                        default_branch=p.get("default_branch", "main"),
                        private=p.get("visibility", "private") == "private",
                    )
                )

            if len(data) < 100 or page >= 3:
                break
            page += 1

        return repos

    async def create_webhook(
        self,
        owner: str,
        repo: str,
        webhook_url: str,
        webhook_secret: str,
    ) -> WebhookInfo:
        """Create a webhook on the GitLab project."""
        project_path = self._project_path(owner, repo)

        resp = await self._client.post(
            f"/projects/{project_path}/hooks",
            json={
                "url": webhook_url,
                "token": webhook_secret,
                "merge_requests_events": True,
                "note_events": True,
                "push_events": False,
                "enable_ssl_verification": True,
            },
        )

        if resp.status_code == 422:
            # May already exist — try to find and update
            existing = await self._find_existing_webhook(
                project_path, webhook_url
            )
            if existing:
                return await self._update_webhook(
                    project_path, existing, webhook_url, webhook_secret
                )
            raise GitProviderError(
                f"Failed to create webhook: {resp.text}", status_code=422
            )

        if resp.status_code not in (200, 201):
            raise GitProviderError(
                f"Failed to create webhook: {resp.status_code} {resp.text}",
                status_code=resp.status_code,
            )

        data = resp.json()
        return WebhookInfo(
            webhook_id=data["id"],
            webhook_url=webhook_url,
            events=["merge_request", "note"],
            status="active",
        )

    async def _find_existing_webhook(
        self, project_path: str, webhook_url: str
    ) -> int | None:
        """Find existing webhook by URL."""
        resp = await self._client.get(f"/projects/{project_path}/hooks")
        if resp.status_code != 200:
            return None
        for hook in resp.json():
            if hook.get("url") == webhook_url:
                return hook["id"]
        return None

    async def _update_webhook(
        self,
        project_path: str,
        webhook_id: int,
        webhook_url: str,
        webhook_secret: str,
    ) -> WebhookInfo:
        """Update an existing webhook."""
        resp = await self._client.put(
            f"/projects/{project_path}/hooks/{webhook_id}",
            json={
                "url": webhook_url,
                "token": webhook_secret,
                "merge_requests_events": True,
                "note_events": True,
                "push_events": False,
                "enable_ssl_verification": True,
            },
        )
        if resp.status_code != 200:
            raise GitProviderError(
                f"Failed to update webhook: {resp.status_code}",
                status_code=resp.status_code,
            )
        return WebhookInfo(
            webhook_id=webhook_id,
            webhook_url=webhook_url,
            events=["merge_request", "note"],
            status="active",
        )

    async def delete_webhook(
        self,
        owner: str,
        repo: str,
        webhook_id: int,
    ) -> None:
        """Delete a webhook. Best-effort."""
        project_path = self._project_path(owner, repo)
        resp = await self._client.delete(
            f"/projects/{project_path}/hooks/{webhook_id}"
        )
        if resp.status_code not in (200, 204, 404):
            logger.warning(
                "Failed to delete GitLab webhook %d on %s/%s: %s",
                webhook_id, owner, repo, resp.status_code,
            )

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> PullRequestInfo:
        """Create a merge request on the GitLab project."""
        project_path = self._project_path(owner, repo)

        resp = await self._client.post(
            f"/projects/{project_path}/merge_requests",
            json={
                "title": title,
                "description": body,
                "source_branch": head,
                "target_branch": base,
            },
        )
        if resp.status_code not in (200, 201):
            raise GitProviderError(
                f"Failed to create MR: {resp.status_code} {resp.text}",
                status_code=resp.status_code,
            )

        data = resp.json()
        return PullRequestInfo(
            number=data["iid"],
            url=data.get("web_url", ""),
            html_url=data.get("web_url", ""),
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
