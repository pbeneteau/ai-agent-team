"""Git push flow — clone, branch, write, commit, push, create PR.

Ref: TDD-04 Section 9.1 (push flow), Section 9.2 (iteration push).

Executed after DAG finalization for code artifacts. Uses subprocess git
commands for clone/branch/commit/push and the provider API client for PR
creation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_string
from app.core.git_providers import get_client
from app.core.git_providers.common import GitProviderError
from app.core.s3_workspace import download_artifact_file
from app.models.artifact import Artifact
from app.models.git_provider_connection import GitProviderConnection

logger = logging.getLogger(__name__)


def _parse_repo_url(git_repo_url: str) -> tuple[str, str]:
    """Extract owner and repo name from a git URL.

    Supports:
      - https://github.com/owner/repo
      - https://github.com/owner/repo.git
      - git@github.com:owner/repo.git
    """
    if git_repo_url.startswith("git@"):
        # git@github.com:owner/repo.git
        path = git_repo_url.split(":", 1)[1]
    else:
        parsed = urlparse(git_repo_url)
        path = parsed.path.lstrip("/")

    # Remove trailing .git
    if path.endswith(".git"):
        path = path[:-4]

    parts = path.split("/")
    if len(parts) < 2:
        raise ValueError(f"Cannot parse owner/repo from URL: {git_repo_url}")

    return parts[0], parts[1]


async def _run_git(args: list[str], cwd: str) -> str:
    """Run a git command and return stdout. Raises on non-zero exit."""
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        error_msg = stderr.decode("utf-8", errors="replace").strip()
        raise GitProviderError(
            f"git {' '.join(args)} failed: {error_msg}",
            status_code=None,
        )

    return stdout.decode("utf-8", errors="replace").strip()


def _find_connection(
    connections: list[GitProviderConnection],
    owner: str,
    repo: str,
) -> GitProviderConnection | None:
    """Find the connection that has access to the target repo."""
    for conn in connections:
        repos = conn.repositories or []
        for r in repos:
            if r.get("owner") == owner and r.get("name") == repo:
                return conn
    # Fallback: return first connection with matching provider
    return connections[0] if connections else None


def _authenticated_clone_url(
    provider: str,
    token: str,
    owner: str,
    repo: str,
) -> str:
    """Build an authenticated HTTPS clone URL."""
    if provider == "github":
        return f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
    elif provider == "gitlab":
        return f"https://oauth2:{token}@gitlab.com/{owner}/{repo}.git"
    else:
        raise ValueError(f"Unknown provider: {provider}")


async def push_artifact_to_git(
    artifact: Artifact,
    version_number: int,
    file_manifest: list[dict[str, Any]],
    connections: list[GitProviderConnection],
    db: AsyncSession,
) -> None:
    """Push a code artifact to git and create a PR.

    TDD-04 Section 9.1:
    1. Load git_provider_connection
    2. Determine target repo
    3. Clone base branch
    4. Create feature branch: artifact/{artifact_id_short}
    5. Write artifact files from S3
    6. Commit
    7. Push
    8. Create PR
    9. Store PR URL/number on artifact
    """
    if not artifact.git_repo_url:
        logger.info("No git_repo_url set on artifact %s, skipping push", artifact.id)
        return

    owner, repo = _parse_repo_url(artifact.git_repo_url)
    connection = _find_connection(connections, owner, repo)

    if connection is None:
        logger.warning(
            "No git connection found for %s/%s, skipping push", owner, repo
        )
        return

    token = decrypt_string(connection.access_token_encrypted)
    clone_url = _authenticated_clone_url(connection.provider, token, owner, repo)
    base_branch = artifact.git_base_branch or "main"
    artifact_id_short = artifact.id[:8]
    feature_branch = f"artifact/{artifact_id_short}"

    tmpdir = tempfile.mkdtemp(prefix="agent_team_git_")
    try:
        # 1. Clone the base branch (shallow for speed)
        await _run_git(
            ["clone", "--depth", "1", "--branch", base_branch, clone_url, "repo"],
            cwd=tmpdir,
        )
        repo_dir = os.path.join(tmpdir, "repo")

        # 2. Configure git user
        await _run_git(["config", "user.email", "ai-agent-team@noreply.com"], cwd=repo_dir)
        await _run_git(["config", "user.name", "AI Agent Team"], cwd=repo_dir)

        # 3. Create feature branch
        await _run_git(["checkout", "-b", feature_branch], cwd=repo_dir)

        # 4. Write artifact files from S3
        for file_entry in file_manifest:
            file_path = file_entry["path"]
            content = download_artifact_file(
                artifact_id=artifact.id,
                version_number=version_number,
                file_path=file_path,
            )
            full_path = os.path.join(repo_dir, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "wb") as f:
                f.write(content)

        # 5. Stage and commit
        await _run_git(["add", "-A"], cwd=repo_dir)
        commit_msg = f"[AI Agent Team] {artifact.title}"
        await _run_git(["commit", "-m", commit_msg, "--allow-empty"], cwd=repo_dir)

        # 6. Push feature branch
        await _run_git(["push", "-u", "origin", feature_branch], cwd=repo_dir)

        # 7. Create PR via provider API
        client = get_client(connection.provider, token)
        try:
            assumptions_text = ""
            sources_text = ""

            pr_body = (
                f"## AI Agent Team Deliverable\n\n"
                f"**Goal:** {artifact.goal or 'N/A'}\n\n"
                f"{assumptions_text}"
                f"{sources_text}"
                f"---\n"
                f"Generated by [AI Agent Team](http://localhost:3000)"
            )

            pr_info = await client.create_pull_request(
                owner=owner,
                repo=repo,
                title=artifact.title,
                body=pr_body,
                head=feature_branch,
                base=base_branch,
            )

            # 8. Store PR info on artifact
            await db.execute(
                update(Artifact)
                .where(Artifact.id == artifact.id)
                .values(
                    git_pr_url=pr_info.html_url,
                    git_pr_number=pr_info.number,
                    git_feature_branch=feature_branch,
                )
            )
            await db.commit()

            logger.info(
                "Created PR #%d for artifact %s: %s",
                pr_info.number, artifact.id, pr_info.html_url,
            )
        finally:
            await client.close()

    except Exception:
        logger.exception("Git push failed for artifact %s", artifact.id)
        raise
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


async def push_iteration_to_git(
    artifact: Artifact,
    version_number: int,
    file_manifest: list[dict[str, Any]],
    connections: list[GitProviderConnection],
    comment_instruction: str | None = None,
) -> None:
    """Push an iteration to the existing feature branch.

    TDD-04 Section 9.2:
    1. Checkout existing feature branch
    2. Overwrite changed files
    3. Commit with iteration message
    4. Push — PR updates automatically
    """
    if not artifact.git_repo_url or not artifact.git_feature_branch:
        logger.info("No git branch set on artifact %s, skipping iteration push", artifact.id)
        return

    owner, repo = _parse_repo_url(artifact.git_repo_url)
    connection = _find_connection(connections, owner, repo)

    if connection is None:
        logger.warning(
            "No git connection found for %s/%s, skipping iteration push", owner, repo
        )
        return

    token = decrypt_string(connection.access_token_encrypted)
    clone_url = _authenticated_clone_url(connection.provider, token, owner, repo)
    feature_branch = artifact.git_feature_branch

    tmpdir = tempfile.mkdtemp(prefix="agent_team_git_")
    try:
        # Clone and checkout existing feature branch
        await _run_git(
            ["clone", "--depth", "1", "--branch", feature_branch, clone_url, "repo"],
            cwd=tmpdir,
        )
        repo_dir = os.path.join(tmpdir, "repo")

        await _run_git(["config", "user.email", "ai-agent-team@noreply.com"], cwd=repo_dir)
        await _run_git(["config", "user.name", "AI Agent Team"], cwd=repo_dir)

        # Write updated files
        for file_entry in file_manifest:
            file_path = file_entry["path"]
            content = download_artifact_file(
                artifact_id=artifact.id,
                version_number=version_number,
                file_path=file_path,
            )
            full_path = os.path.join(repo_dir, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "wb") as f:
                f.write(content)

        # Commit
        await _run_git(["add", "-A"], cwd=repo_dir)

        instruction_snippet = ""
        if comment_instruction:
            instruction_snippet = f" — {comment_instruction[:80]}"
        commit_msg = f"[AI Agent Team] Iteration v{version_number}{instruction_snippet}"

        await _run_git(["commit", "-m", commit_msg, "--allow-empty"], cwd=repo_dir)

        # Push
        await _run_git(["push", "origin", feature_branch], cwd=repo_dir)

        logger.info(
            "Pushed iteration v%d to branch %s for artifact %s",
            version_number, feature_branch, artifact.id,
        )

    except Exception:
        logger.exception("Iteration push failed for artifact %s", artifact.id)
        raise
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
