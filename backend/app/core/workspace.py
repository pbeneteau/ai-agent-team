"""
Workspace manager — each agent gets an isolated work directory.

Structure:
  data/workspaces/{agent_id}/
    ├── README.md          (created at init, describes the agent)
    ├── skills/            (Markdown skill files — self-authored or written by Alex)
    │   └── core_skills.md (generated during learning phase)
    ├── downloads/         (downloaded files, documents)
    ├── repos/             (cloned git repositories)
    ├── output/            (task deliverables — reports, code, assets)
    └── tmp/               (scratch space, cleaned between tasks)

Agents MUST work exclusively inside their workspace.
Cross-agent file sharing is done via the shared/ workspace (associate only).
Skills can be authored by:
  - The agent itself (skill_write tool)
  - The Associate / top-level agent (agent_skill_write tool, which targets another agent's skills/)
"""
import json
import os
import shutil
import subprocess
from datetime import datetime, UTC
from functools import lru_cache
from pathlib import Path
from typing import Optional
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)

SHARED_WORKSPACE_ID = "shared"


class AgentWorkspace:
    """Represents and manages a single agent's workspace directory."""

    SUBDIRS = ["skills", "downloads", "repos", "output", "tmp"]

    def __init__(self, agent_id: str, agent_name: str = "", agent_title: str = ""):
        settings = get_settings()
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.agent_title = agent_title
        self.root = Path(settings.workspaces_dir) / agent_id
        self._init()

    def _init(self):
        """Create the workspace directory structure if it doesn't exist."""
        self.root.mkdir(parents=True, exist_ok=True)
        for sub in self.SUBDIRS:
            (self.root / sub).mkdir(exist_ok=True)

        readme = self.root / "README.md"
        if not readme.exists():
            readme.write_text(
                f"# Workspace — {self.agent_name or self.agent_id}\n\n"
                f"**Role:** {self.agent_title}\n"
                f"**Agent ID:** `{self.agent_id}`\n"
                f"**Created:** {datetime.now(UTC).isoformat()}Z\n\n"
                "## Structure\n\n"
                "- `skills/` — skill documentation (Markdown) — self-authored or written by Alex\n"
                "- `downloads/` — downloaded files and documents\n"
                "- `repos/` — cloned git repositories\n"
                "- `output/` — task deliverables (reports, code, assets)\n"
                "- `tmp/` — temporary scratch space\n",
                encoding="utf-8",
            )

    # --- Path helpers ---

    @property
    def skills(self) -> Path:
        return self.root / "skills"

    @property
    def downloads(self) -> Path:
        return self.root / "downloads"

    @property
    def repos(self) -> Path:
        return self.root / "repos"

    @property
    def output(self) -> Path:
        return self.root / "output"

    @property
    def tmp(self) -> Path:
        return self.root / "tmp"

    # --- Skills helpers ---

    def write_skill(self, skill_name: str, content: str, author: str = "self") -> Path:
        """Write or overwrite a skill Markdown file.
        Args:
            skill_name: Slug-style name (e.g. 'python_backend', 'seo_strategy')
            content:    Markdown content
            author:     Who wrote this skill ('self' or the author agent name)
        """
        safe_name = skill_name.replace(" ", "_").replace("/", "_").lower()
        path = self.skills / f"{safe_name}.md"
        header = (
            f"<!--\n"
            f"  skill: {safe_name}\n"
            f"  author: {author}\n"
            f"  updated: {datetime.now(UTC).isoformat()}Z\n"
            f"-->\n\n"
        )
        path.write_text(header + content, encoding="utf-8")
        logger.info(f"[{self.agent_id}] Skill '{safe_name}' written by {author}")
        return path

    def read_skill(self, skill_name: str) -> Optional[str]:
        safe_name = skill_name.replace(" ", "_").replace("/", "_").lower()
        path = self.skills / f"{safe_name}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def list_skills(self) -> list[dict]:
        """Return metadata for all skills in this agent's skills/ dir."""
        result = []
        for f in sorted(self.skills.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            author = "unknown"
            for line in text.splitlines():
                if line.strip().startswith("author:"):
                    author = line.split("author:", 1)[1].strip()
                    break
            result.append({
                "name": f.stem,
                "path": f"skills/{f.name}",
                "size_bytes": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                "author": author,
            })
        return result

    def read_all_skills(self) -> str:
        """Concatenate all skills into a single context string."""
        parts = []
        for f in sorted(self.skills.glob("*.md")):
            content = f.read_text(encoding="utf-8")
            parts.append(f"# Skill: {f.stem}\n\n{content}")
        return "\n\n---\n\n".join(parts)

    def write_profile(self, profile: dict):
        path = self.skills / "profile.json"
        path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")

    def read_profile(self) -> Optional[dict]:
        path = self.skills / "profile.json"
        if path.exists():
            import json
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def path(self, relative: str) -> Path:
        """Resolve a relative path safely within the workspace (no traversal)."""
        resolved = (self.root / relative).resolve()
        if not str(resolved).startswith(str(self.root.resolve())):
            raise PermissionError(f"Path traversal attempt blocked: {relative}")
        return resolved

    # --- File operations ---

    def write(self, relative_path: str, content: str, encoding: str = "utf-8") -> Path:
        p = self.path(relative_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding=encoding)
        logger.debug(f"[{self.agent_id}] Wrote: {relative_path}")
        return p

    def write_bytes(self, relative_path: str, content: bytes) -> Path:
        p = self.path(relative_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    def read(self, relative_path: str, encoding: str = "utf-8") -> str:
        p = self.path(relative_path)
        return p.read_text(encoding=encoding)

    def exists(self, relative_path: str) -> bool:
        return self.path(relative_path).exists()

    def list_dir(self, relative_path: str = ".") -> list[dict]:
        p = self.path(relative_path)
        if not p.is_dir():
            return []
        root_resolved = self.root.resolve()
        entries = []
        for item in sorted(p.iterdir()):
            item_resolved = item.resolve()
            try:
                rel = str(item_resolved.relative_to(root_resolved))
            except ValueError:
                rel = item.name
            entries.append({
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
                "modified": datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
                "path": rel,
            })
        return entries

    def delete(self, relative_path: str):
        p = self.path(relative_path)
        if p.is_dir():
            shutil.rmtree(p)
        elif p.is_file():
            p.unlink()

    def clear_tmp(self):
        """Wipe the tmp/ folder between tasks."""
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp.mkdir(exist_ok=True)
        logger.debug(f"[{self.agent_id}] Cleared tmp/")

    # --- Git operations ---

    def git_clone(self, repo_url: str, folder_name: Optional[str] = None, depth: int = 1) -> Path:
        """Clone a git repository into repos/. Returns the cloned directory path."""
        if not folder_name:
            folder_name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
        target = self.repos / folder_name
        if target.exists():
            logger.info(f"[{self.agent_id}] Repo already exists: {folder_name}, pulling instead")
            result = subprocess.run(
                ["git", "-C", str(target), "pull", "--ff-only"],
                capture_output=True, text=True, timeout=120,
            )
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            cmd = ["git", "clone", f"--depth={depth}", repo_url, str(target)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            raise RuntimeError(f"git failed: {result.stderr}")
        logger.info(f"[{self.agent_id}] Cloned/updated {repo_url} -> {target}")
        return target

    def run_command(self, command: list[str], cwd: Optional[str] = None, timeout: int = 60) -> dict:
        """
        Run a shell command inside the workspace (cwd defaults to workspace root).
        Returns {"stdout", "stderr", "returncode"}.
        """
        work_dir = self.path(cwd) if cwd else self.root
        if not str(work_dir.resolve()).startswith(str(self.root.resolve())):
            raise PermissionError("Command cwd must be inside workspace")
        result = subprocess.run(
            command,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }

    # --- Metadata ---

    def info(self) -> dict:
        total_size = sum(f.stat().st_size for f in self.root.rglob("*") if f.is_file())
        return {
            "agent_id": self.agent_id,
            "root": str(self.root),
            "total_size_bytes": total_size,
            "contents": self.list_dir("."),
        }


class WorkspaceManager:
    """Central registry for all agent workspaces."""

    def __init__(self):
        settings = get_settings()
        self._base = Path(settings.workspaces_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        # Create shared workspace (for cross-agent deliverables)
        self._shared = AgentWorkspace(SHARED_WORKSPACE_ID, "Shared", "Cross-agent shared space")

    def get(self, agent_id: str, agent_name: str = "", agent_title: str = "") -> AgentWorkspace:
        """Get (and lazily create) a workspace for an agent."""
        return AgentWorkspace(agent_id, agent_name, agent_title)

    @property
    def shared(self) -> AgentWorkspace:
        return self._shared

    def list_workspaces(self) -> list[dict]:
        result = []
        for d in sorted(self._base.iterdir()):
            if d.is_dir():
                ws = AgentWorkspace(d.name)
                result.append(ws.info())
        return result

    def delete_workspace(self, agent_id: str):
        ws_path = self._base / agent_id
        if ws_path.exists():
            shutil.rmtree(ws_path)
            logger.info(f"Deleted workspace for agent {agent_id}")


@lru_cache(maxsize=1)
def get_workspace_manager() -> WorkspaceManager:
    return WorkspaceManager()
