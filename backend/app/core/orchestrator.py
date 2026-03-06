"""
Main CrewAI orchestrator.
Receives task requests, builds the right Crew and kicks off execution.
"""
import json
import logging
import asyncio
import threading
from datetime import datetime, UTC
from functools import lru_cache
from pathlib import Path
from typing import Optional, Callable, Awaitable
import uuid

from crewai import Crew, Task

from app.config import get_settings
from app.models.task import TaskResponse, TaskStatus, TaskPriority
from app.models.agent import AgentConfig, AgentRole
from app.core.agent_factory import get_agent_factory
from app.agents.base_agent import build_crewai_agent
from app.tools.registry import get_tools_for_agent
from app.memory.skills_store import get_skills_store
from app.memory.project_context import get_project_context_store

logger = logging.getLogger(__name__)

BroadcastCallback = Callable[[dict], Awaitable[None]]

_SKILLS_TOKEN_BUDGET = 1500   # max chars for core_skills injected into backstory
_CTX_TOKEN_BUDGET    = 800    # max chars for project_context injected into backstory


_ALL_SKILLS_TOKEN_BUDGET = 6000   # max chars for all skills (includes research_*.md)


def _enrich_backstory(cfg: AgentConfig, skills_store) -> str:
    """
    Build the agent's enriched backstory for task execution.

    Reads ALL skills from the agent's workspace (core_skills, project_context,
    and any research_*.md files produced by autonomous research) via read_all_skills(),
    so research findings are automatically injected into every task.
    """
    parts = [cfg.backstory]

    if cfg.workspace_path:
        try:
            from app.core.workspace import get_workspace_manager
            wm = get_workspace_manager()
            workspace = wm.get(cfg.id, cfg.name, cfg.title)
            all_skills = workspace.read_all_skills()
            if all_skills:
                parts.append(f"\n\n## Your knowledge base\n{all_skills[:_ALL_SKILLS_TOKEN_BUDGET]}")
        except Exception:
            # Fallback to individual skill reads if workspace unavailable
            project_ctx = skills_store.read_skill(cfg.id, "project_context")
            if project_ctx:
                parts.append(f"\n\n## Your project context\n{project_ctx[:_CTX_TOKEN_BUDGET]}")
            core_skills = skills_store.read_skill(cfg.id, "core_skills")
            if core_skills:
                parts.append(f"\n\n## Your expertise\n{core_skills[:_SKILLS_TOKEN_BUDGET]}")

        parts.append(
            f"\n\n## Your workspace\n"
            f"Directory: `{cfg.workspace_path}`\n"
            f"Use `workspace_list` to browse, `workspace_shell` to run commands, `git_clone` to clone repos."
        )

    return "".join(parts)


class Orchestrator:
    def __init__(self):
        settings = get_settings()
        self.data_dir = Path(settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_file = self.data_dir / "tasks.json"
        self._tasks: dict[str, TaskResponse] = {}
        self._save_lock = threading.Lock()
        self._load_tasks()

    def _load_tasks(self):
        if self.tasks_file.exists():
            raw = json.loads(self.tasks_file.read_text(encoding="utf-8"))
            self._tasks = {k: TaskResponse.model_validate(v) for k, v in raw.items()}

    def _save_tasks(self):
        with self._save_lock:
            self.tasks_file.write_text(
                json.dumps({k: v.model_dump() for k, v in self._tasks.items()}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def create_task(self, title: str, description: str, priority: TaskPriority = TaskPriority.MEDIUM, team_id: Optional[str] = None) -> TaskResponse:
        now = datetime.now(UTC).isoformat()
        task = TaskResponse(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            status=TaskStatus.PENDING,
            priority=priority,
            assigned_team_id=team_id,
            created_at=now,
            updated_at=now,
        )
        self._tasks[task.id] = task
        self._save_tasks()
        return task

    def get_task(self, task_id: str) -> Optional[TaskResponse]:
        return self._tasks.get(task_id)

    def delete_task(self, task_id: str) -> bool:
        if task_id not in self._tasks:
            return False
        del self._tasks[task_id]
        self._save_tasks()
        return True

    def list_tasks(self) -> list[TaskResponse]:
        return list(self._tasks.values())

    def _update_task(self, task_id: str, **kwargs):
        if task_id in self._tasks:
            task = self._tasks[task_id]
            for k, v in kwargs.items():
                setattr(task, k, v)
            task.updated_at = datetime.now(UTC).isoformat()
            self._save_tasks()

    def _add_progress(self, task_id: str, message: str, agent: Optional[str] = None):
        if task_id in self._tasks:
            entry = {"timestamp": datetime.now(UTC).isoformat(), "message": message}
            if agent:
                entry["agent"] = agent
            self._tasks[task_id].progress_log.append(entry)
            self._tasks[task_id].updated_at = datetime.now(UTC).isoformat()
            self._save_tasks()

    async def execute_task(self, task_id: str, broadcast: Optional[BroadcastCallback] = None):
        task = self._tasks.get(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return

        factory = get_agent_factory()
        skills_store = get_skills_store()
        ctx_store = get_project_context_store()

        self._update_task(task_id, status=TaskStatus.RUNNING)
        self._add_progress(task_id, "Task started")
        if broadcast:
            await broadcast({"type": "task_update", "data": self._tasks[task_id].model_dump()})

        try:
            # Determine which agents to use
            if task.assigned_team_id:
                agents_cfg = factory.get_team_agents(task.assigned_team_id)
            else:
                # Use associate + all ready agents
                agents_cfg = [a for a in factory.list_agents() if a.status.value == "ready"]

            if not agents_cfg:
                raise ValueError("No ready agents available for this task")

            # Enrich task description with project context
            ctx = ctx_store.load_context() or {}
            enriched_description = (
                f"Project: {ctx.get('name', 'Unknown')}\n"
                f"Context: {ctx.get('description', '')}\n\n"
                f"Task: {task.description}"
            )

            # Build CrewAI agents with their skills
            crewai_agents = []
            for cfg in agents_cfg:
                tools = get_tools_for_agent(cfg.tools, workspace_path=cfg.workspace_path)
                enriched_backstory = _enrich_backstory(cfg, skills_store)
                agent = build_crewai_agent(cfg, tools=tools, backstory_override=enriched_backstory)
                crewai_agents.append((cfg, agent))
                self._update_task(task_id, assigned_agent_ids=[c.id for c, _ in crewai_agents])

            self._add_progress(task_id, f"Assembled team: {', '.join(c.name for c, _ in crewai_agents)}")
            if broadcast:
                await broadcast({"type": "task_update", "data": self._tasks[task_id].model_dump()})

            # Self-augmentation guidance injected into every task
            SELF_AUGMENT_SUFFIX = (
                "\n\n---\n"
                "## Self-augmentation rule\n"
                "During this task, you may use `skill_note` to save a new insight — but ONLY if ALL of:\n"
                "1. You searched the web or processed external data and found something genuinely new\n"
                "2. The information is not already in your skills (check with `skill_read` first if unsure)\n"
                "3. The insight will be useful for future tasks, not just this one\n"
                "Keep the note under 300 characters. Do NOT save things you already know. "
                "Do NOT flood your skills with every search result — be selective and concise."
            )

            # Build CrewAI tasks — one per agent or chained tasks for multi-agent
            crew_tasks = []
            if len(crewai_agents) == 1:
                cfg, agent = crewai_agents[0]
                crew_tasks.append(Task(
                    description=enriched_description + SELF_AUGMENT_SUFFIX,
                    agent=agent,
                    expected_output="A complete, well-structured response addressing all aspects of the task.",
                ))
            else:
                # Each specialist gets a dedicated sub-task; the lead synthesises them all.
                lead_cfg, lead_agent = crewai_agents[0]
                specialist_tasks = []
                for spec_cfg, spec_agent in crewai_agents[1:]:
                    spec_task = Task(
                        description=(
                            f"You are {spec_cfg.name} ({spec_cfg.title}), specialised in: {spec_cfg.specialization}.\n\n"
                            f"Contribute your expertise to the following team task:\n\n{enriched_description}\n\n"
                            f"Focus strictly on what falls within your specialization. "
                            f"Produce a clear, structured contribution that the team lead can integrate."
                            + SELF_AUGMENT_SUFFIX
                        ),
                        agent=spec_agent,
                        expected_output=f"A focused contribution from {spec_cfg.name} relevant to their specialization.",
                    )
                    specialist_tasks.append(spec_task)
                    crew_tasks.append(spec_task)

                lead_task = Task(
                    description=(
                        f"You are {lead_cfg.name} ({lead_cfg.title}), the team lead.\n\n"
                        f"Original task:\n{enriched_description}\n\n"
                        f"Your specialists have produced their contributions (available as context). "
                        f"Synthesise their work into a single, coherent, complete deliverable."
                        + SELF_AUGMENT_SUFFIX
                    ),
                    agent=lead_agent,
                    context=specialist_tasks,
                    expected_output="A complete, well-structured deliverable that integrates all specialist contributions.",
                )
                crew_tasks.append(lead_task)

            crew = Crew(
                agents=[a for _, a in crewai_agents],
                tasks=crew_tasks,
                verbose=True,
            )

            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, crew.kickoff)
            result_text = str(result)

            self._update_task(task_id, status=TaskStatus.COMPLETED, result=result_text)
            self._add_progress(task_id, "Task completed successfully")
            if broadcast:
                await broadcast({"type": "task_update", "data": self._tasks[task_id].model_dump()})

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            self._update_task(task_id, status=TaskStatus.FAILED, error=str(e))
            self._add_progress(task_id, f"Task failed: {e}")
            if broadcast:
                await broadcast({"type": "task_update", "data": self._tasks[task_id].model_dump()})


@lru_cache(maxsize=1)
def get_orchestrator() -> Orchestrator:
    return Orchestrator()
