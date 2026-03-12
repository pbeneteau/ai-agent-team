"""
Dynamically creates and persists AgentConfig instances.
Each agent gets its own workspace directory provisioned on creation.
"""
import json
import threading
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Optional
import logging

from app.agents.specialists.templates import (
    AGENT_TEMPLATES,
    ASSOCIATE_EXTRA_TOOLS,
    BASE_TOOLS,
    TEAM_TEMPLATES,
)
from app.config import get_default_model_tier, get_settings
from app.core.git_provider_store import get_git_provider_store
from app.core.mcp_connection_store import get_mcp_connection_store
from app.core.workspace import get_workspace_manager
from app.models.agent import (
    AgentConfig,
    AgentOccupancyReason,
    AgentOccupancyStatus,
    AgentRole,
    AgentStatus,
    ModelTier,
)
from app.models.git_providers import AgentGitBinding
from app.models.mcp import AgentMcpToolBinding
from app.models.team import TeamConfig

logger = logging.getLogger(__name__)


class AgentFactory:
    def __init__(self):
        settings = get_settings()
        self.settings = settings
        self.data_dir = Path(settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.agents_file = self.data_dir / "agents.json"
        self.teams_file = Path(settings.teams_file)
        self._agents: dict[str, AgentConfig] = {}
        self._teams: dict[str, TeamConfig] = {}
        self._save_lock = threading.Lock()
        self._load()

    def _load(self):
        if self.agents_file.exists():
            raw = json.loads(self.agents_file.read_text(encoding="utf-8"))
            self._agents = {k: AgentConfig.model_validate(v) for k, v in raw.items()}
        if self.teams_file.exists():
            raw = json.loads(self.teams_file.read_text(encoding="utf-8"))
            self._teams = {k: TeamConfig.model_validate(v) for k, v in raw.items()}
        # Ensure all loaded agents have a workspace provisioned
        needs_save = False
        for agent in self._agents.values():
            provisioned_workspace = self._provision_workspace(agent)
            if agent.workspace_path != provisioned_workspace:
                agent.workspace_path = provisioned_workspace
                needs_save = True
            resolved_tier = self._resolve_model_tier(agent.model_tier.value, is_lead=agent.role == AgentRole.TEAM_LEAD)
            if agent.model_tier != resolved_tier:
                agent.model_tier = resolved_tier
                needs_save = True
            cleaned_bindings = self._cleanup_mcp_bindings(agent.mcp_tool_bindings)
            if cleaned_bindings != agent.mcp_tool_bindings:
                agent.mcp_tool_bindings = cleaned_bindings
                needs_save = True
            cleaned_git_bindings = self._cleanup_git_bindings(agent.git_bindings)
            if cleaned_git_bindings != agent.git_bindings:
                agent.git_bindings = cleaned_git_bindings
                needs_save = True
        if needs_save:
            self._save()

    def _resolve_model_tier(self, requested_tier: Optional[str], *, is_lead: bool) -> ModelTier:
        normalized = (requested_tier or "").strip().lower()
        if normalized in {"sonnet", "opus"}:
            return ModelTier(normalized)

        return get_default_model_tier(self.settings, is_lead=is_lead)

    def _provision_workspace(self, agent: AgentConfig) -> str:
        """Create the agent's workspace directory and return its path string."""
        wm = get_workspace_manager()
        ws = wm.get(agent.id, agent.name, agent.title)
        return str(ws.root.resolve())

    def _cleanup_mcp_bindings(
        self,
        bindings: list[AgentMcpToolBinding],
    ) -> list[AgentMcpToolBinding]:
        store = get_mcp_connection_store()
        cleaned: list[AgentMcpToolBinding] = []
        seen: set[tuple[str, str]] = set()
        for binding in bindings:
            connection = store.get_connection(binding.connection_id)
            if connection is None:
                continue
            tools = {tool.name: tool for tool in store.list_tools(binding.connection_id)}
            tool = tools.get(binding.tool_name)
            if tool is None or not tool.read_only:
                continue
            key = (binding.connection_id, binding.tool_name)
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(binding)
        return cleaned

    def _cleanup_git_bindings(
        self,
        bindings: list[AgentGitBinding],
    ) -> list[AgentGitBinding]:
        store = get_git_provider_store()
        cleaned: list[AgentGitBinding] = []
        seen: set[tuple[str, str]] = set()
        for binding in bindings:
            connection = store.get_connection(binding.connection_id)
            if connection is None:
                continue
            repo = store.get_repo(binding.connection_id, binding.repo_full_name)
            if repo is None:
                continue
            key = (binding.connection_id, binding.repo_full_name)
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(binding)
        return cleaned

    def _save(self):
        with self._save_lock:
            self.agents_file.write_text(
                json.dumps({k: v.model_dump() for k, v in self._agents.items()}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self.teams_file.write_text(
                json.dumps({k: v.model_dump() for k, v in self._teams.items()}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # --- Associate (singleton) ---

    def get_or_create_associate(self) -> AgentConfig:
        for agent in self._agents.values():
            if agent.role == AgentRole.ASSOCIATE:
                return agent

        associate = AgentConfig(
            name="Alex",
            role=AgentRole.ASSOCIATE,
            title="Associate",
            specialization="general_management",
            goal=(
                "Be the user's trusted associate. Understand their vision, help them build and manage their AI agent team, "
                "delegate work to the right teams, and synthesize results clearly."
            ),
            backstory=(
                "You are Alex, a highly capable and empathetic AI associate. You think like a co-founder: "
                "you understand business, technology and people. You help the user structure their ideas, "
                "build the right team and get work done. You are proactive, concise and always focused on outcomes."
            ),
            status=AgentStatus.READY,
            tools=["web_search", "file_read", "file_write", "web_browser"] + BASE_TOOLS + ASSOCIATE_EXTRA_TOOLS,
            model_tier=self._resolve_model_tier(None, is_lead=False),
            max_iter=20,
        )
        associate.workspace_path = self._provision_workspace(associate)
        self._agents[associate.id] = associate
        self._save()
        return associate

    # --- Teams ---

    def create_team_from_template(self, template_key: str, customizations: Optional[dict] = None) -> tuple[TeamConfig, list[AgentConfig]]:
        template = TEAM_TEMPLATES[template_key]
        team = TeamConfig(
            name=template["name"],
            description=template["description"],
            domain=template["domain"],
        )

        agents = []
        lead = None

        for i, role_key in enumerate(template["agent_roles"]):
            agent_template = AGENT_TEMPLATES[role_key]
            is_lead = i == 0
            tools = list(dict.fromkeys(agent_template["tools"] + BASE_TOOLS))
            tier_str = agent_template.get("model_tier")
            agent = AgentConfig(
                name=self._generate_name(role_key),
                role=AgentRole.TEAM_LEAD if is_lead else AgentRole.SPECIALIST,
                title=agent_template["title"],
                specialization=agent_template["specialization"],
                goal=agent_template["goal"],
                backstory=agent_template["backstory"],
                team_id=team.id,
                tools=tools,
                status=AgentStatus.PENDING,
                model_tier=self._resolve_model_tier(tier_str, is_lead=is_lead),
                max_iter=agent_template.get("max_iter", 15),
            )
            if is_lead:
                lead = agent
                team.lead_agent_id = agent.id
            team.agent_ids.append(agent.id)
            agents.append(agent)

        # Set parent for non-leads
        if lead:
            for agent in agents:
                if agent.id != lead.id:
                    agent.parent_id = lead.id

        for agent in agents:
            agent.workspace_path = self._provision_workspace(agent)
            self._agents[agent.id] = agent
        self._teams[team.id] = team
        self._save()
        return team, agents

    def create_custom_team(self, name: str, description: str, domain: str, agent_specs: list[dict]) -> tuple[TeamConfig, list[AgentConfig]]:
        team = TeamConfig(name=name, description=description, domain=domain)
        agents = []
        lead = None

        for i, spec in enumerate(agent_specs):
            is_lead = spec.get("is_lead", i == 0)
            # Default custom agents can browse and read their workspace, but should not
            # receive generic workspace writes unless the user explicitly asks for them.
            spec_tools = spec.get("tools", ["web_search", "web_browser", "file_read", "workspace_list"])
            # Ensure web_browser is always present if web_search is
            if "web_search" in spec_tools and "web_browser" not in spec_tools:
                spec_tools = spec_tools + ["web_browser"]
            tools = list(dict.fromkeys(spec_tools + BASE_TOOLS))
            tier_str = spec.get("model_tier")
            agent = AgentConfig(
                name=spec.get("name", self._generate_name(spec.get("specialization", "specialist"))),
                role=AgentRole.TEAM_LEAD if is_lead else AgentRole.SPECIALIST,
                title=spec["title"],
                specialization=spec.get("specialization", "general"),
                goal=spec["goal"],
                backstory=spec["backstory"],
                team_id=team.id,
                tools=tools,
                status=AgentStatus.PENDING,
                model_tier=self._resolve_model_tier(tier_str, is_lead=is_lead),
                max_iter=spec.get("max_iter", 20 if is_lead else 15),
            )
            if is_lead and lead is None:
                lead = agent
                team.lead_agent_id = agent.id
            team.agent_ids.append(agent.id)
            agents.append(agent)

        if lead:
            for agent in agents:
                if agent.id != lead.id:
                    agent.parent_id = lead.id

        for agent in agents:
            agent.workspace_path = self._provision_workspace(agent)
            self._agents[agent.id] = agent
        self._teams[team.id] = team
        self._save()
        return team, agents

    def update_team_scope(self, team_id: str, description: Optional[str] = None, scope_note: Optional[str] = None) -> Optional[TeamConfig]:
        team = self._teams.get(team_id)
        if not team:
            return None
        if description is not None:
            team.description = description
        if scope_note is not None:
            team.scope_note = scope_note
        self._save()
        return team

    def add_agent_to_team(self, team_id: str, spec: dict) -> Optional[AgentConfig]:
        team = self._teams.get(team_id)
        if not team:
            return None

        lead = self._agents.get(team.lead_agent_id) if team.lead_agent_id else None
        requested_lead = bool(spec.get("is_lead", False))
        is_lead = requested_lead and lead is None
        spec_tools = spec.get("tools", ["web_search", "web_browser", "file_read", "workspace_list"])
        if "web_search" in spec_tools and "web_browser" not in spec_tools:
            spec_tools = spec_tools + ["web_browser"]
        tools = list(dict.fromkeys(spec_tools + BASE_TOOLS))
        tier_str = spec.get("model_tier")

        agent = AgentConfig(
            name=spec.get("name", self._generate_name(spec.get("specialization", "specialist"))),
            role=AgentRole.TEAM_LEAD if is_lead else AgentRole.SPECIALIST,
            title=spec["title"],
            specialization=spec.get("specialization", "general"),
            goal=spec["goal"],
            backstory=spec["backstory"],
            team_id=team.id,
            parent_id=lead.id if lead else None,
            tools=tools,
            status=AgentStatus.PENDING,
            model_tier=self._resolve_model_tier(tier_str, is_lead=is_lead),
            max_iter=spec.get("max_iter", 20 if is_lead else 15),
        )

        if is_lead:
            team.lead_agent_id = agent.id

        team.agent_ids.append(agent.id)
        agent.workspace_path = self._provision_workspace(agent)
        self._agents[agent.id] = agent
        self._save()
        return agent

    def delete_agent(self, agent_id: str) -> bool:
        agent = self._agents.get(agent_id)
        if not agent:
            return False

        if agent.team_id and agent.team_id in self._teams:
            team = self._teams[agent.team_id]
            remaining_ids = [existing_id for existing_id in team.agent_ids if existing_id != agent_id]
            team.agent_ids = remaining_ids

            if team.lead_agent_id == agent_id:
                team.lead_agent_id = remaining_ids[0] if remaining_ids else None
                if team.lead_agent_id and team.lead_agent_id in self._agents:
                    new_lead = self._agents[team.lead_agent_id]
                    new_lead.role = AgentRole.TEAM_LEAD
                    new_lead.parent_id = None
                    for child_id in remaining_ids:
                        if child_id == new_lead.id or child_id not in self._agents:
                            continue
                        child = self._agents[child_id]
                        child.role = AgentRole.SPECIALIST
                        child.parent_id = new_lead.id
            elif team.lead_agent_id and team.lead_agent_id in self._agents:
                for child_id in remaining_ids:
                    if child_id not in self._agents:
                        continue
                    child = self._agents[child_id]
                    if child.role == AgentRole.SPECIALIST and child.parent_id == agent_id:
                        child.parent_id = team.lead_agent_id

        self._agents.pop(agent_id)
        for team in self._teams.values():
            if agent_id in team.agent_ids:
                team.agent_ids.remove(agent_id)
        self._save()
        return True

    def delete_team(self, team_id: str) -> bool:
        team = self._teams.pop(team_id, None)
        if not team:
            return False
        for agent_id in team.agent_ids:
            self._agents.pop(agent_id, None)
        self._save()
        return True

    def update_agent_status(self, agent_id: str, status: AgentStatus):
        if agent_id in self._agents:
            self._agents[agent_id].status = status
            self._save()

    def update_agent_mcp_tool_bindings(
        self,
        agent_id: str,
        bindings: list[AgentMcpToolBinding],
    ) -> Optional[AgentConfig]:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        agent.mcp_tool_bindings = self._cleanup_mcp_bindings(bindings)
        self._save()
        return agent

    def update_agent_git_bindings(
        self,
        agent_id: str,
        bindings: list[AgentGitBinding],
    ) -> Optional[AgentConfig]:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        agent.git_bindings = self._cleanup_git_bindings(bindings)
        self._save()
        return agent

    def remove_mcp_connection_references(self, connection_id: str) -> int:
        updated_agents = 0
        for agent in self._agents.values():
            filtered = [
                binding
                for binding in agent.mcp_tool_bindings
                if binding.connection_id != connection_id
            ]
            if filtered != agent.mcp_tool_bindings:
                agent.mcp_tool_bindings = filtered
                updated_agents += 1
        if updated_agents:
            self._save()
        return updated_agents

    def remove_git_provider_connection_references(self, connection_id: str) -> int:
        updated_agents = 0
        for agent in self._agents.values():
            filtered = [
                binding
                for binding in agent.git_bindings
                if binding.connection_id != connection_id
            ]
            if filtered != agent.git_bindings:
                agent.git_bindings = filtered
                updated_agents += 1
        if updated_agents:
            self._save()
        return updated_agents

    def update_agent_occupancy(
        self,
        agent_id: str,
        *,
        occupancy_status: AgentOccupancyStatus,
        occupancy_reason: Optional[AgentOccupancyReason] = None,
        current_task_id: Optional[str] = None,
        current_task_title: Optional[str] = None,
        current_node_id: Optional[str] = None,
        current_node_title: Optional[str] = None,
        busy_since: Optional[str] = None,
    ) -> Optional[AgentConfig]:
        agent = self._agents.get(agent_id)
        if not agent:
            return None

        agent.occupancy_status = occupancy_status
        agent.occupancy_reason = occupancy_reason
        agent.current_task_id = current_task_id
        agent.current_task_title = current_task_title
        agent.current_node_id = current_node_id
        agent.current_node_title = current_node_title
        agent.busy_since = busy_since
        self._save()
        return agent

    def clear_agent_occupancy(self, agent_id: str) -> Optional[AgentConfig]:
        return self.update_agent_occupancy(
            agent_id,
            occupancy_status=AgentOccupancyStatus.IDLE,
            occupancy_reason=None,
            current_task_id=None,
            current_task_title=None,
            current_node_id=None,
            current_node_title=None,
            busy_since=None,
        )

    def reconcile_runtime_state_after_restart(self) -> dict[str, int]:
        """
        Recover from an unclean local shutdown.

        Nothing is actively running after process restart, so any transient
        occupancy must be cleared. Agents interrupted during learning are moved
        back to pending so they can be re-initialized cleanly.
        """
        updated_agents = 0
        reset_learning_agents = 0

        for agent in self._agents.values():
            changed = False

            if (
                agent.occupancy_status != AgentOccupancyStatus.IDLE
                or agent.occupancy_reason is not None
                or agent.current_task_id is not None
                or agent.current_task_title is not None
                or agent.current_node_id is not None
                or agent.current_node_title is not None
                or agent.busy_since is not None
            ):
                agent.occupancy_status = AgentOccupancyStatus.IDLE
                agent.occupancy_reason = None
                agent.current_task_id = None
                agent.current_task_title = None
                agent.current_node_id = None
                agent.current_node_title = None
                agent.busy_since = None
                changed = True

            if agent.status == AgentStatus.LEARNING:
                agent.status = AgentStatus.PENDING
                reset_learning_agents += 1
                changed = True
            elif agent.status == AgentStatus.WORKING:
                agent.status = AgentStatus.READY
                changed = True

            if changed:
                updated_agents += 1

        if updated_agents:
            self._save()

        return {
            "updated_agents": updated_agents,
            "reset_learning_agents": reset_learning_agents,
        }

    # --- Queries ---

    def get_agent(self, agent_id: str) -> Optional[AgentConfig]:
        return self._agents.get(agent_id)

    def get_team(self, team_id: str) -> Optional[TeamConfig]:
        return self._teams.get(team_id)

    def list_agents(self) -> list[AgentConfig]:
        return list(self._agents.values())

    def list_teams(self) -> list[TeamConfig]:
        return list(self._teams.values())

    def get_ordered_team_agents(self, team_id: str) -> list[AgentConfig]:
        team = self._teams.get(team_id)
        if not team:
            return []

        ordered: list[AgentConfig] = []
        seen: set[str] = set()

        if team.lead_agent_id and team.lead_agent_id in self._agents:
            ordered.append(self._agents[team.lead_agent_id])
            seen.add(team.lead_agent_id)

        for agent_id in team.agent_ids:
            if agent_id in seen or agent_id not in self._agents:
                continue
            ordered.append(self._agents[agent_id])
            seen.add(agent_id)

        for agent in self._agents.values():
            if agent.team_id == team_id and agent.id not in seen:
                ordered.append(agent)
                seen.add(agent.id)

        return ordered

    def get_team_agents(self, team_id: str) -> list[AgentConfig]:
        return self.get_ordered_team_agents(team_id)

    def get_associate(self) -> Optional[AgentConfig]:
        for a in self._agents.values():
            if a.role == AgentRole.ASSOCIATE:
                return a
        return None

    def _generate_name(self, role_key: str) -> str:
        names = {
            "project_manager": "Jordan",
            "frontend_developer": "Sam",
            "backend_developer": "Morgan",
            "devops_engineer": "Casey",
            "marketing_lead": "Riley",
            "content_writer": "Blake",
            "social_media_manager": "Avery",
            "finance_analyst": "Quinn",
            "product_designer": "Taylor",
        }
        return names.get(role_key, f"Agent-{str(uuid.uuid4())[:6]}")

    def reset(self):
        wm = get_workspace_manager()
        for agent_id in list(self._agents.keys()):
            wm.delete_workspace(agent_id)
        self._agents = {}
        self._teams = {}
        self.get_or_create_associate()
        self._save()


@lru_cache(maxsize=1)
def get_agent_factory() -> AgentFactory:
    return AgentFactory()
