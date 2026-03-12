import subprocess
from pathlib import Path

from app.config.tool_runtime import (
    GIT_CLONE_TIMEOUT_SECONDS,
    GIT_PULL_TIMEOUT_SECONDS,
    GIT_PUSH_TIMEOUT_SECONDS,
)
from app.core.git_providers import (
    GitProviderClientError,
    get_authenticated_clone_url,
    get_provider_handler,
)
from app.core.workspace import resolve_workspace_path
from app.models.git_providers import GitProviderConnectionConfig, GitRemoteRepo


def _sanitize_output(text: str, secrets: list[str]) -> str:
    sanitized = text or ""
    for secret in secrets:
        if secret:
            sanitized = sanitized.replace(secret, "***")
    return sanitized


def _run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int,
    secrets: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout)
    if secrets:
        result.stdout = _sanitize_output(result.stdout, secrets)
        result.stderr = _sanitize_output(result.stderr, secrets)
    return result


def repo_slug(repo: GitRemoteRepo) -> str:
    return repo.full_name.replace("/", "__")


def ensure_repo_cloned(
    workspace_root: Path,
    connection: GitProviderConnectionConfig,
    repo: GitRemoteRepo,
    *,
    folder_name: str = "",
) -> Path:
    repos_root = resolve_workspace_path(workspace_root, "repos")
    repos_root.mkdir(parents=True, exist_ok=True)
    target_name = folder_name.strip() or repo_slug(repo)
    target = resolve_workspace_path(workspace_root, str(Path("repos") / target_name))
    token = connection.auth_token.strip()
    clean_url = repo.clone_url
    auth_url = get_authenticated_clone_url(connection, repo.clone_url)
    secrets = [token, auth_url]
    if not target.exists():
        result = _run_git(
            ["git", "clone", "--depth=1", auth_url, str(target)],
            timeout=GIT_CLONE_TIMEOUT_SECONDS,
            secrets=secrets,
        )
        if result.returncode != 0:
            raise GitProviderClientError(result.stderr or "Unable to clone repository.")
        _run_git(["git", "-C", str(target), "remote", "set-url", "origin", clean_url], timeout=GIT_PULL_TIMEOUT_SECONDS)
        return target
    fetch_result = _run_git(["git", "-C", str(target), "fetch", "origin", "--prune"], timeout=GIT_PULL_TIMEOUT_SECONDS, secrets=secrets)
    if fetch_result.returncode != 0:
        raise GitProviderClientError(fetch_result.stderr or "Unable to refresh repository.")
    return target


def create_or_switch_branch(repo_path: Path, branch_name: str, *, base_branch: str) -> str:
    normalized = branch_name.strip()
    if not normalized:
        raise GitProviderClientError("branch_name is required.")
    if normalized in {"main", "master"}:
        raise GitProviderClientError("Direct work on protected branches is blocked.")
    fetch_result = _run_git(["git", "-C", str(repo_path), "fetch", "origin", base_branch], timeout=GIT_PULL_TIMEOUT_SECONDS)
    if fetch_result.returncode != 0:
        raise GitProviderClientError(fetch_result.stderr or "Unable to fetch base branch.")
    checkout_result = _run_git(
        ["git", "-C", str(repo_path), "checkout", "-B", normalized, f"origin/{base_branch}"],
        timeout=GIT_PULL_TIMEOUT_SECONDS,
    )
    if checkout_result.returncode != 0:
        raise GitProviderClientError(checkout_result.stderr or "Unable to create or switch branch.")
    return normalized


def commit_and_push_changes(
    repo_path: Path,
    *,
    connection: GitProviderConnectionConfig,
    repo: GitRemoteRepo,
    commit_message: str,
    branch_name: str,
) -> str:
    normalized_message = commit_message.strip()
    if not normalized_message:
        raise GitProviderClientError("commit_message is required.")
    normalized_branch = branch_name.strip()
    if not normalized_branch or normalized_branch in {"main", "master"}:
        raise GitProviderClientError("Push to protected branches is blocked.")
    checkout_result = _run_git(["git", "-C", str(repo_path), "checkout", normalized_branch], timeout=GIT_PULL_TIMEOUT_SECONDS)
    if checkout_result.returncode != 0:
        raise GitProviderClientError(checkout_result.stderr or "Unable to checkout the target branch.")
    add_result = _run_git(["git", "-C", str(repo_path), "add", "-A"], timeout=GIT_PULL_TIMEOUT_SECONDS)
    if add_result.returncode != 0:
        raise GitProviderClientError(add_result.stderr or "Unable to stage repository changes.")
    status_result = _run_git(["git", "-C", str(repo_path), "status", "--short"], timeout=GIT_PULL_TIMEOUT_SECONDS)
    if status_result.returncode != 0:
        raise GitProviderClientError(status_result.stderr or "Unable to inspect repository changes.")
    if not status_result.stdout.strip():
        return "No local changes to commit."
    commit_result = _run_git(
        [
            "git",
            "-C",
            str(repo_path),
            "-c",
            "user.name=AI Agent Team",
            "-c",
            "user.email=agent-team@local",
            "commit",
            "-m",
            normalized_message,
        ],
        timeout=GIT_PULL_TIMEOUT_SECONDS,
    )
    if commit_result.returncode != 0:
        raise GitProviderClientError(commit_result.stderr or "Unable to create git commit.")
    token = connection.auth_token.strip()
    auth_url = get_authenticated_clone_url(connection, repo.clone_url)
    secrets = [token, auth_url]
    original_url_result = _run_git(["git", "-C", str(repo_path), "remote", "get-url", "origin"], timeout=GIT_PULL_TIMEOUT_SECONDS)
    if original_url_result.returncode != 0:
        raise GitProviderClientError(original_url_result.stderr or "Unable to read remote origin URL.")
    original_url = original_url_result.stdout.strip() or repo.clone_url
    try:
        set_result = _run_git(["git", "-C", str(repo_path), "remote", "set-url", "origin", auth_url], timeout=GIT_PULL_TIMEOUT_SECONDS, secrets=secrets)
        if set_result.returncode != 0:
            raise GitProviderClientError(set_result.stderr or "Unable to configure authenticated remote URL.")
        push_result = _run_git(
            ["git", "-C", str(repo_path), "push", "-u", "origin", normalized_branch],
            timeout=GIT_PUSH_TIMEOUT_SECONDS,
            secrets=secrets,
        )
        if push_result.returncode != 0:
            raise GitProviderClientError(push_result.stderr or "Unable to push branch to remote.")
        return push_result.stdout.strip() or f"Pushed branch {normalized_branch}."
    finally:
        _run_git(["git", "-C", str(repo_path), "remote", "set-url", "origin", original_url], timeout=GIT_PULL_TIMEOUT_SECONDS)


def create_pull_request(
    connection: GitProviderConnectionConfig,
    *,
    repo: GitRemoteRepo,
    title: str,
    body: str,
    source_branch: str,
    target_branch: str,
) -> str:
    handler = get_provider_handler(connection.provider)
    result = handler.create_pull_request(
        connection,
        repo=repo,
        title=title.strip(),
        body=body.strip(),
        source_branch=source_branch.strip(),
        target_branch=target_branch.strip() or repo.default_branch,
    )
    return f"Created review request #{result.number}: {result.web_url}"


def fetch_pull_request_context(
    connection: GitProviderConnectionConfig,
    *,
    repo: GitRemoteRepo,
    number: int | None = None,
) -> str:
    handler = get_provider_handler(connection.provider)
    return handler.fetch_pull_request_context(connection, repo=repo, number=number)
