import json
import logging
import threading
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.core.git_providers import get_provider_handler
from app.models.git_providers import (
    GitProvider,
    GitProviderConnectionConfig,
    GitProviderConnectionCreateRequest,
    GitProviderConnectionResponse,
    GitProviderConnectionStatus,
    GitProviderConnectionUpdateRequest,
    GitProviderTestResult,
    GitProviderUsageSummary,
    GitRemoteRepo,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _default_base_url(provider: GitProvider) -> str:
    if provider == GitProvider.GITHUB:
        return "https://api.github.com"
    if provider == GitProvider.GITLAB:
        return "https://gitlab.com/api/v4"
    raise ValueError(f"Unsupported provider: {provider.value}")


def _to_response(connection: GitProviderConnectionConfig) -> GitProviderConnectionResponse:
    return GitProviderConnectionResponse(
        id=connection.id,
        provider=connection.provider,
        name=connection.name,
        base_url=connection.base_url,
        auth_mode=connection.auth_mode,
        has_auth_token=bool(connection.auth_token.strip()),
        enabled=connection.enabled,
        notes=connection.notes,
        discovered_repos=list(connection.discovered_repos),
        status=connection.status,
        last_tested_at=connection.last_tested_at,
        last_error=connection.last_error,
        total_repo_actions=connection.total_repo_actions,
        clone_actions=connection.clone_actions,
        push_actions=connection.push_actions,
        pull_request_actions=connection.pull_request_actions,
        last_action_at=connection.last_action_at,
    )


class GitProviderStore:
    def __init__(self):
        settings = get_settings()
        data_dir = Path(settings.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        self._file = data_dir / "git_provider_connections.json"
        self._lock = threading.Lock()
        self._connections: dict[str, GitProviderConnectionConfig] = {}
        self._load()

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            payload = json.loads(self._file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read git provider connections store: %s", exc)
            return
        if not isinstance(payload, dict):
            return
        connections: dict[str, GitProviderConnectionConfig] = {}
        for connection_id, item in payload.items():
            try:
                connections[connection_id] = GitProviderConnectionConfig.model_validate(item)
            except Exception as exc:
                logger.warning("Skipping invalid git provider connection %s: %s", connection_id, exc)
        self._connections = connections

    def _save(self) -> None:
        payload = {connection_id: connection.model_dump(mode="json") for connection_id, connection in self._connections.items()}
        self._file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def list_connections(self) -> list[GitProviderConnectionResponse]:
        with self._lock:
            return [_to_response(connection) for connection in sorted(self._connections.values(), key=lambda item: item.name.lower())]

    def get_connection(self, connection_id: str) -> Optional[GitProviderConnectionConfig]:
        with self._lock:
            connection = self._connections.get(connection_id)
            return connection.model_copy(deep=True) if connection else None

    def create_connection(self, request: GitProviderConnectionCreateRequest) -> GitProviderConnectionResponse:
        with self._lock:
            base_url = request.base_url or _default_base_url(request.provider)
            connection = GitProviderConnectionConfig(
                id=str(uuid.uuid4()),
                provider=request.provider,
                name=request.name.strip(),
                base_url=base_url,
                auth_token=request.auth_token.strip(),
                enabled=request.enabled,
                notes=request.notes.strip(),
            )
            self._connections[connection.id] = connection
            self._save()
            logger.info("Created git provider connection %s (%s)", connection.name, connection.provider.value)
            return _to_response(connection)

    def update_connection(self, connection_id: str, request: GitProviderConnectionUpdateRequest) -> GitProviderConnectionResponse:
        with self._lock:
            connection = self._connections.get(connection_id)
            if not connection:
                raise ValueError("Git provider connection not found")
            updates = request.model_dump(exclude_unset=True)
            if "name" in updates and request.name is not None:
                connection.name = request.name.strip()
            if "base_url" in updates and request.base_url is not None:
                connection.base_url = request.base_url
            if request.clear_auth_token:
                connection.auth_token = ""
            elif "auth_token" in updates and request.auth_token is not None:
                connection.auth_token = request.auth_token.strip()
            if "enabled" in updates and request.enabled is not None:
                connection.enabled = request.enabled
            if "notes" in updates and request.notes is not None:
                connection.notes = request.notes.strip()
            self._save()
            logger.info("Updated git provider connection %s (%s)", connection.name, connection.provider.value)
            return _to_response(connection)

    def delete_connection(self, connection_id: str) -> None:
        with self._lock:
            if connection_id not in self._connections:
                raise ValueError("Git provider connection not found")
            logger.info("Deleted git provider connection %s", self._connections[connection_id].name)
            del self._connections[connection_id]
            self._save()

    def list_repos(self, connection_id: str) -> list[GitRemoteRepo]:
        with self._lock:
            connection = self._connections.get(connection_id)
            if not connection:
                raise ValueError("Git provider connection not found")
            return list(connection.discovered_repos)

    def test_connection(self, connection_id: str) -> GitProviderTestResult:
        connection = self.get_connection(connection_id)
        if connection is None:
            raise ValueError("Git provider connection not found")
        result = get_provider_handler(connection.provider).test_connection(connection)
        with self._lock:
            target = self._connections.get(connection_id)
            if target is None:
                raise ValueError("Git provider connection not found")
            target.status = result.status
            target.last_tested_at = _now_iso()
            target.last_error = result.error
            self._save()
        if result.ok:
            logger.info("Git provider connection test succeeded for %s", connection.name)
        else:
            logger.warning("Git provider connection test failed for %s: %s", connection.name, result.error)
        return result

    def refresh_repos(self, connection_id: str) -> list[GitRemoteRepo]:
        connection = self.get_connection(connection_id)
        if connection is None:
            raise ValueError("Git provider connection not found")
        repos = get_provider_handler(connection.provider).list_repos(connection)
        with self._lock:
            target = self._connections.get(connection_id)
            if target is None:
                raise ValueError("Git provider connection not found")
            target.discovered_repos = repos
            target.status = GitProviderConnectionStatus.HEALTHY
            target.last_tested_at = _now_iso()
            target.last_error = None
            self._save()
        logger.info("Refreshed %s repositories for git provider connection %s", len(repos), connection.name)
        return list(repos)

    def get_repo(self, connection_id: str, repo_full_name: str) -> Optional[GitRemoteRepo]:
        repos = self.list_repos(connection_id)
        for repo in repos:
            if repo.full_name == repo_full_name:
                return repo
        return None

    def record_action(self, connection_id: str, *, action: str, success: bool, error: str | None = None) -> None:
        with self._lock:
            connection = self._connections.get(connection_id)
            if not connection:
                return
            connection.total_repo_actions += 1
            connection.last_action_at = _now_iso()
            if action == "clone":
                connection.clone_actions += 1
            elif action == "push":
                connection.push_actions += 1
            elif action == "pull_request":
                connection.pull_request_actions += 1
            if success:
                connection.status = GitProviderConnectionStatus.HEALTHY
                connection.last_error = None
            else:
                connection.status = GitProviderConnectionStatus.DEGRADED
                connection.last_error = error
            self._save()
        if success:
            logger.info(
                "Recorded git provider action connection=%s action=%s",
                connection_id,
                action,
            )
        else:
            logger.warning(
                "Git provider action failed connection=%s action=%s error=%s",
                connection_id,
                action,
                error,
            )

    def summarize_usage(self) -> GitProviderUsageSummary:
        connections = self.list_connections()
        summary = GitProviderUsageSummary(connections=connections)
        summary.total_connections = len(connections)
        summary.healthy_connections = sum(1 for item in connections if item.status == GitProviderConnectionStatus.HEALTHY)
        summary.degraded_connections = sum(1 for item in connections if item.status == GitProviderConnectionStatus.DEGRADED)
        summary.unavailable_connections = sum(1 for item in connections if item.status == GitProviderConnectionStatus.UNAVAILABLE)
        summary.total_repo_actions = sum(item.total_repo_actions for item in connections)
        summary.clone_actions = sum(item.clone_actions for item in connections)
        summary.push_actions = sum(item.push_actions for item in connections)
        summary.pull_request_actions = sum(item.pull_request_actions for item in connections)
        return summary


@lru_cache(maxsize=1)
def get_git_provider_store() -> GitProviderStore:
    return GitProviderStore()
