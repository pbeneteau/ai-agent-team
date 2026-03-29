"""GitHub API client using httpx + PAT auth.

Implements the GitProviderClient protocol for GitHub.
"""

from __future__ import annotations

import logging

import httpx

from app.core.git_providers.common import (
    GitProviderError,
    PullRequestInfo,
    RepoInfo,
    UserInfo,
    WebhookInfo,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.github.com"


class GitHubClient:
    """GitHub API client using a Personal Access Token."""

    def __init__(self, access_token: str) -> None:
        self._token = access_token
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={
                "Authorization": f"token {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    async def validate_token(self) -> UserInfo:
        """Validate PAT by calling GET /user and reading scopes from headers."""
        resp = await self._client.get("/user")
        if resp.status_code == 401:
            raise GitProviderError("Invalid GitHub token", status_code=401)
        if resp.status_code != 200:
            raise GitProviderError(
                f"GitHub API error: {resp.status_code} {resp.text}",
                status_code=resp.status_code,
            )

        data = resp.json()
        scopes_header = resp.headers.get("x-oauth-scopes", "")
        scopes = [s.strip() for s in scopes_header.split(",") if s.strip()]
        rate_remaining = resp.headers.get("x-ratelimit-remaining")

        return UserInfo(
            username=data.get("login", ""),
            scopes=scopes,
            rate_limit_remaining=int(rate_remaining) if rate_remaining else None,
        )

    async def list_repos(self) -> list[RepoInfo]:
        """List repositories accessible via this PAT (up to 100)."""
        repos: list[RepoInfo] = []
        page = 1

        while True:
            resp = await self._client.get(
                "/user/repos",
                params={"per_page": 100, "page": page, "sort": "updated"},
            )
            if resp.status_code != 200:
                raise GitProviderError(
                    f"Failed to list repos: {resp.status_code}",
                    status_code=resp.status_code,
                )

            data = resp.json()
            if not data:
                break

            for r in data:
                repos.append(
                    RepoInfo(
                        owner=r["owner"]["login"],
                        name=r["name"],
                        full_name=r["full_name"],
                        default_branch=r.get("default_branch", "main"),
                        private=r.get("private", False),
                    )
                )

            # GitHub paginates with Link header; stop at page 3 (300 repos max for MVP)
            if len(data) < 100 or page >= 3:
                break
            page += 1

        return repos

    async def get_readme(self, owner: str, repo: str) -> str | None:
        """Fetch the README content from the repository. Returns None if not found."""
        resp = await self._client.get(
            f"/repos/{owner}/{repo}/readme",
            headers={"Accept": "application/vnd.github.raw+json"},
        )
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            logger.warning("Failed to fetch README for %s/%s: %s", owner, repo, resp.status_code)
            return None
        return resp.text

    async def create_webhook(
        self,
        owner: str,
        repo: str,
        webhook_url: str,
        webhook_secret: str,
    ) -> WebhookInfo:
        """Create a webhook on the repository (AD-17)."""
        events = ["pull_request", "pull_request_review_comment", "pull_request_review"]

        resp = await self._client.post(
            f"/repos/{owner}/{repo}/hooks",
            json={
                "name": "web",
                "active": True,
                "config": {
                    "url": webhook_url,
                    "content_type": "json",
                    "secret": webhook_secret,
                    "insecure_ssl": "0",
                },
                "events": events,
            },
        )

        if resp.status_code == 422:
            # May already exist — try to find and update
            existing = await self._find_existing_webhook(owner, repo, webhook_url)
            if existing:
                return await self._update_webhook(
                    owner, repo, existing, webhook_url, webhook_secret, events
                )
            raise GitProviderError(
                f"Failed to create webhook: {resp.text}", status_code=422
            )

        if resp.status_code == 404:
            raise GitProviderError(
                "Repository not found or PAT lacks admin:repo_hook scope",
                status_code=404,
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
            events=events,
            status="active",
        )

    async def _find_existing_webhook(
        self, owner: str, repo: str, webhook_url: str
    ) -> int | None:
        """Find an existing webhook by URL. Returns webhook_id or None."""
        resp = await self._client.get(f"/repos/{owner}/{repo}/hooks")
        if resp.status_code != 200:
            return None
        for hook in resp.json():
            config = hook.get("config", {})
            if config.get("url") == webhook_url:
                return hook["id"]
        return None

    async def _update_webhook(
        self,
        owner: str,
        repo: str,
        webhook_id: int,
        webhook_url: str,
        webhook_secret: str,
        events: list[str],
    ) -> WebhookInfo:
        """Update an existing webhook."""
        resp = await self._client.patch(
            f"/repos/{owner}/{repo}/hooks/{webhook_id}",
            json={
                "active": True,
                "config": {
                    "url": webhook_url,
                    "content_type": "json",
                    "secret": webhook_secret,
                    "insecure_ssl": "0",
                },
                "events": events,
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
            events=events,
            status="active",
        )

    async def delete_webhook(
        self,
        owner: str,
        repo: str,
        webhook_id: int,
    ) -> None:
        """Delete a webhook. Best-effort — does not raise on 404."""
        resp = await self._client.delete(
            f"/repos/{owner}/{repo}/hooks/{webhook_id}"
        )
        if resp.status_code not in (200, 204, 404):
            logger.warning(
                "Failed to delete GitHub webhook %d on %s/%s: %s",
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
        """Create a pull request."""
        resp = await self._client.post(
            f"/repos/{owner}/{repo}/pulls",
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            },
        )
        if resp.status_code not in (200, 201):
            raise GitProviderError(
                f"Failed to create PR: {resp.status_code} {resp.text}",
                status_code=resp.status_code,
            )

        data = resp.json()
        return PullRequestInfo(
            number=data["number"],
            url=data["url"],
            html_url=data["html_url"],
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
