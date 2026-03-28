"""git_clone and git_push tools — interact with connected git repositories.

Ref: TDD-03 Section 6.2 (git tools available in execution phase only),
     AD-14: GitHub/GitLab auth via PAT only (no OAuth for MVP).

Uses the GitHub/GitLab REST APIs directly via httpx.
"""

from __future__ import annotations

import base64
import logging
import urllib.parse
from typing import Any

import httpx

from app.tools.registry import ExecutionContext, ToolDef

logger = logging.getLogger(__name__)

_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Connection lookup
# ---------------------------------------------------------------------------


def _find_connection(repo_url: str, connections: list[Any]) -> Any | None:
    """Find a git connection whose repositories match the given repo URL."""
    parsed = urllib.parse.urlparse(repo_url)
    path = parsed.path.strip("/").removesuffix(".git")

    for conn in connections:
        for repo in conn.repositories or []:
            repo_full = repo.get("full_name", "") if isinstance(repo, dict) else str(repo)
            if repo_full and repo_full.lower() == path.lower():
                return conn
        # Fallback: match on provider domain when no repos are configured
        if not conn.repositories:
            if conn.provider == "github" and "github.com" in (parsed.netloc or ""):
                return conn
            if conn.provider == "gitlab" and "gitlab" in (parsed.netloc or ""):
                return conn

    return None


def _parse_owner_repo(repo_url: str) -> tuple[str, str]:
    """Extract owner and repo name from a GitHub/GitLab URL."""
    path = urllib.parse.urlparse(repo_url).path.strip("/").removesuffix(".git")
    parts = path.split("/")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "", path


# ---------------------------------------------------------------------------
# git_clone executor
# ---------------------------------------------------------------------------


async def execute_clone(tool_input: dict[str, Any], context: ExecutionContext) -> str:
    """Clone / read files from a git repository via the provider API."""
    repo_url: str = tool_input.get("repo_url", "")
    if not repo_url:
        return "Error: 'repo_url' is required."

    branch: str = tool_input.get("branch", "main")
    path: str = tool_input.get("path", "")

    conn = _find_connection(repo_url, context.git_connections)
    if conn is None:
        return (
            f"Error: no git connection found for '{repo_url}'. "
            "Configure a git provider connection for this repository."
        )

    owner, repo = _parse_owner_repo(repo_url)
    if not owner or not repo:
        return f"Error: could not parse owner/repo from '{repo_url}'."

    token: str = conn.access_token_encrypted  # PAT stored directly for MVP

    if conn.provider == "github":
        return await _github_get_contents(owner, repo, branch, path, token)
    if conn.provider == "gitlab":
        return await _gitlab_get_contents(owner, repo, branch, path, token)
    return f"Error: unsupported git provider '{conn.provider}'."


async def _github_get_contents(
    owner: str, repo: str, branch: str, path: str, token: str,
) -> str:
    """Fetch file or directory contents from the GitHub Contents API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                url,
                params={"ref": branch},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github.v3+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        return f"Error: GitHub API request timed out for '{owner}/{repo}'."
    except httpx.HTTPStatusError as exc:
        return f"Error: GitHub API returned HTTP {exc.response.status_code}."
    except httpx.HTTPError as exc:
        return f"Error: GitHub API request failed: {exc}"

    # Directory listing
    if isinstance(data, list):
        entries: list[str] = []
        for item in data:
            kind = item.get("type", "file")
            name = item.get("name", "")
            size = item.get("size", 0)
            prefix = "[dir] " if kind == "dir" else ""
            entries.append(f"  {prefix}{name} ({size} bytes)")
        return f"Contents of '{path or '/'}' on branch '{branch}':\n" + "\n".join(entries)

    # Single file
    if isinstance(data, dict) and data.get("type") == "file":
        content_b64 = data.get("content", "")
        try:
            return base64.b64decode(content_b64).decode("utf-8")
        except Exception:
            return f"Error: could not decode file content for '{path}'."

    return f"Error: unexpected response type from GitHub for '{path}'."


async def _gitlab_get_contents(
    owner: str, repo: str, branch: str, path: str, token: str,
) -> str:
    """Fetch file or tree contents from the GitLab Repository API."""
    project_path = urllib.parse.quote(f"{owner}/{repo}", safe="")

    if path:
        file_path = urllib.parse.quote(path, safe="")
        url = f"https://gitlab.com/api/v4/projects/{project_path}/repository/files/{file_path}"
        params: dict[str, str] = {"ref": branch}
    else:
        url = f"https://gitlab.com/api/v4/projects/{project_path}/repository/tree"
        params = {"ref": branch, "per_page": "100"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                url,
                params=params,
                headers={"PRIVATE-TOKEN": token},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        return f"Error: GitLab API request timed out for '{owner}/{repo}'."
    except httpx.HTTPStatusError as exc:
        return f"Error: GitLab API returned HTTP {exc.response.status_code}."
    except httpx.HTTPError as exc:
        return f"Error: GitLab API request failed: {exc}"

    # Tree listing
    if isinstance(data, list):
        entries = []
        for item in data:
            kind = item.get("type", "blob")
            name = item.get("name", "")
            prefix = "[dir] " if kind == "tree" else ""
            entries.append(f"  {prefix}{name}")
        return f"Contents of '{path or '/'}' on branch '{branch}':\n" + "\n".join(entries)

    # Single file
    if isinstance(data, dict):
        content_b64 = data.get("content", "")
        try:
            return base64.b64decode(content_b64).decode("utf-8")
        except Exception:
            return f"Error: could not decode file content for '{path}'."

    return f"Error: unexpected response from GitLab for '{path}'."


# ---------------------------------------------------------------------------
# git_push executor
# ---------------------------------------------------------------------------


async def execute_push(tool_input: dict[str, Any], context: ExecutionContext) -> str:
    """Push files to a git repository by creating a commit via the provider API."""
    repo_url: str = tool_input.get("repo_url", "")
    branch: str = tool_input.get("branch", "")
    commit_message: str = tool_input.get("commit_message", "")
    files: dict[str, str] = tool_input.get("files", {})

    if not repo_url:
        return "Error: 'repo_url' is required."
    if not branch:
        return "Error: 'branch' is required."
    if not commit_message:
        return "Error: 'commit_message' is required."
    if not files:
        return "Error: 'files' must contain at least one file."

    conn = _find_connection(repo_url, context.git_connections)
    if conn is None:
        return (
            f"Error: no git connection found for '{repo_url}'. "
            "Configure a git provider connection for this repository."
        )

    owner, repo = _parse_owner_repo(repo_url)
    if not owner or not repo:
        return f"Error: could not parse owner/repo from '{repo_url}'."

    token: str = conn.access_token_encrypted

    if conn.provider == "github":
        return await _github_push_files(owner, repo, branch, commit_message, files, token)
    if conn.provider == "gitlab":
        return await _gitlab_push_files(owner, repo, branch, commit_message, files, token)
    return f"Error: unsupported git provider '{conn.provider}'."


async def _github_push_files(
    owner: str,
    repo: str,
    branch: str,
    commit_message: str,
    files: dict[str, str],
    token: str,
) -> str:
    """Create a multi-file commit using the GitHub Git Data API."""
    base_url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            # 1. Get current branch ref
            ref_resp = await client.get(
                f"{base_url}/git/ref/heads/{branch}", headers=headers,
            )
            ref_resp.raise_for_status()
            current_sha: str = ref_resp.json()["object"]["sha"]

            # 2. Get the current commit to find the base tree SHA
            commit_resp = await client.get(
                f"{base_url}/git/commits/{current_sha}", headers=headers,
            )
            commit_resp.raise_for_status()
            base_tree_sha: str = commit_resp.json()["tree"]["sha"]

            # 3. Create blobs for each file
            tree_entries: list[dict[str, str]] = []
            for file_path, content in files.items():
                blob_resp = await client.post(
                    f"{base_url}/git/blobs",
                    headers=headers,
                    json={"content": content, "encoding": "utf-8"},
                )
                blob_resp.raise_for_status()
                tree_entries.append({
                    "path": file_path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_resp.json()["sha"],
                })

            # 4. Create new tree
            tree_resp = await client.post(
                f"{base_url}/git/trees",
                headers=headers,
                json={"base_tree": base_tree_sha, "tree": tree_entries},
            )
            tree_resp.raise_for_status()
            new_tree_sha: str = tree_resp.json()["sha"]

            # 5. Create commit
            new_commit_resp = await client.post(
                f"{base_url}/git/commits",
                headers=headers,
                json={
                    "message": commit_message,
                    "tree": new_tree_sha,
                    "parents": [current_sha],
                },
            )
            new_commit_resp.raise_for_status()
            new_commit_sha: str = new_commit_resp.json()["sha"]

            # 6. Update branch ref
            update_resp = await client.patch(
                f"{base_url}/git/refs/heads/{branch}",
                headers=headers,
                json={"sha": new_commit_sha},
            )
            update_resp.raise_for_status()

    except httpx.TimeoutException:
        return f"Error: GitHub API timed out during push to '{owner}/{repo}'."
    except httpx.HTTPStatusError as exc:
        return f"Error: GitHub API returned HTTP {exc.response.status_code} during push."
    except httpx.HTTPError as exc:
        return f"Error: GitHub API request failed during push: {exc}"

    return (
        f"Successfully pushed {len(files)} file(s) to "
        f"'{owner}/{repo}' branch '{branch}'. Commit: {new_commit_sha[:8]}"
    )


async def _gitlab_push_files(
    owner: str,
    repo: str,
    branch: str,
    commit_message: str,
    files: dict[str, str],
    token: str,
) -> str:
    """Create a multi-file commit using the GitLab Commits API."""
    project_path = urllib.parse.quote(f"{owner}/{repo}", safe="")
    url = f"https://gitlab.com/api/v4/projects/{project_path}/repository/commits"

    actions = [
        {
            "action": "create",
            "file_path": file_path,
            "content": content,
        }
        for file_path, content in files.items()
    ]

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                url,
                headers={
                    "PRIVATE-TOKEN": token,
                    "Content-Type": "application/json",
                },
                json={
                    "branch": branch,
                    "commit_message": commit_message,
                    "actions": actions,
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        return f"Error: GitLab API timed out during push to '{owner}/{repo}'."
    except httpx.HTTPStatusError as exc:
        return f"Error: GitLab API returned HTTP {exc.response.status_code} during push."
    except httpx.HTTPError as exc:
        return f"Error: GitLab API request failed during push: {exc}"

    commit_id = str(data.get("id", "unknown"))[:8]
    return (
        f"Successfully pushed {len(files)} file(s) to "
        f"'{owner}/{repo}' branch '{branch}'. Commit: {commit_id}"
    )


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


GIT_CLONE_TOOL = ToolDef(
    name="git_clone",
    description=(
        "Clone a git repository and read its contents. "
        "Use this to read source code from a connected repository."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "repo_url": {
                "type": "string",
                "description": "Repository URL (e.g., 'https://github.com/owner/repo')",
            },
            "branch": {
                "type": "string",
                "description": "Branch name (default: main)",
            },
            "path": {
                "type": "string",
                "description": "Path to a specific file or directory to read",
            },
        },
        "required": ["repo_url"],
    },
    executor=execute_clone,
)


GIT_PUSH_TOOL = ToolDef(
    name="git_push",
    description=(
        "Push files to a git repository. "
        "Creates a commit with the specified files on the given branch."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "repo_url": {
                "type": "string",
                "description": "Repository URL (e.g., 'https://github.com/owner/repo')",
            },
            "branch": {
                "type": "string",
                "description": "Target branch name",
            },
            "commit_message": {
                "type": "string",
                "description": "Commit message",
            },
            "files": {
                "type": "object",
                "description": "Map of file paths to file content",
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["repo_url", "branch", "commit_message", "files"],
    },
    executor=execute_push,
)
