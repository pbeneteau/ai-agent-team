"""
SkillsStore — thin adapter that delegates to AgentWorkspace.skills/.

All skill files now live inside the agent's workspace at:
  data/workspaces/{agent_id}/skills/{skill_name}.md

This keeps the workspace self-contained and allows both the agent itself
and the Associate to author skills for any agent.
"""
from functools import lru_cache
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def _get_ws(agent_id: str):
    """Lazy import to avoid circular dependencies."""
    from app.core.workspace import get_workspace_manager
    return get_workspace_manager().get(agent_id)


class SkillsStore:
    """
    Facade over workspace skills — kept for backward-compat with learning.py
    and orchestrator.py which call get_skills_store().
    """

    def write_skill(self, agent_id: str, skill_name: str, content: str, author: str = "self"):
        _get_ws(agent_id).write_skill(skill_name, content, author=author)

    def read_skill(self, agent_id: str, skill_name: str) -> Optional[str]:
        return _get_ws(agent_id).read_skill(skill_name)

    def list_skills(self, agent_id: str) -> list[str]:
        return [s["name"] for s in _get_ws(agent_id).list_skills()]

    def list_skills_meta(self, agent_id: str) -> list[dict]:
        return _get_ws(agent_id).list_skills()

    def read_all_skills(self, agent_id: str) -> str:
        return _get_ws(agent_id).read_all_skills()

    def write_profile(self, agent_id: str, profile: dict):
        _get_ws(agent_id).write_profile(profile)

    def read_profile(self, agent_id: str) -> Optional[dict]:
        return _get_ws(agent_id).read_profile()


@lru_cache(maxsize=1)
def get_skills_store() -> SkillsStore:
    return SkillsStore()
