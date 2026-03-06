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

from app.config import get_settings
from app.models.agent import AgentConfig, AgentRole, AgentStatus, ModelTier
from app.models.team import TeamConfig
from app.agents.specialists.templates import AGENT_TEMPLATES, TEAM_TEMPLATES, BASE_TOOLS, ASSOCIATE_EXTRA_TOOLS

logger = logging.getLogger(__name__)


class AgentFactory:
    def __init__(self):
        settings = get_settings()
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
            if agent.workspace_path is None:
                agent.workspace_path = self._provision_workspace(agent)
                needs_save = True
        if needs_save:
            self._save()

    def _provision_workspace(self, agent: AgentConfig) -> str:
        """Create the agent's workspace directory and return its path string."""
        from app.core.workspace import get_workspace_manager
        wm = get_workspace_manager()
        ws = wm.get(agent.id, agent.name, agent.title)
        return str(ws.root)

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
            # Alex uses Opus — he is the strategic brain, his reasoning quality is critical
            model_tier=ModelTier.OPUS,
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
            tier_str = agent_template.get("model_tier", "sonnet")
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
                model_tier=ModelTier.OPUS if tier_str == "opus" else ModelTier.SONNET,
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
            spec_tools = spec.get("tools", ["web_search", "file_read", "file_write"])
            tools = list(dict.fromkeys(spec_tools + BASE_TOOLS))
            tier_str = spec.get("model_tier", "opus" if is_lead else "sonnet")
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
                model_tier=ModelTier.OPUS if tier_str == "opus" else ModelTier.SONNET,
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

    def delete_agent(self, agent_id: str) -> bool:
        if agent_id not in self._agents:
            return False
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

    # --- Queries ---

    def get_agent(self, agent_id: str) -> Optional[AgentConfig]:
        return self._agents.get(agent_id)

    def get_team(self, team_id: str) -> Optional[TeamConfig]:
        return self._teams.get(team_id)

    def list_agents(self) -> list[AgentConfig]:
        return list(self._agents.values())

    def list_teams(self) -> list[TeamConfig]:
        return list(self._teams.values())

    def get_team_agents(self, team_id: str) -> list[AgentConfig]:
        return [a for a in self._agents.values() if a.team_id == team_id]

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
        from app.core.workspace import get_workspace_manager
        wm = get_workspace_manager()
        for agent_id in list(self._agents.keys()):
            wm.delete_workspace(agent_id)
        self._agents = {}
        self._teams = {}
        self._save()
        get_agent_factory.cache_clear()


@lru_cache(maxsize=1)
def get_agent_factory() -> AgentFactory:
    return AgentFactory()
