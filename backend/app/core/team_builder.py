"""
Conversational team builder.
Drives the dialogue to understand the project, then proposes and creates the agent team.
"""
import json
import logging
from typing import Optional, AsyncGenerator
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.core.agent_factory import get_agent_factory
from app.agents.specialists.templates import TEAM_TEMPLATES, AGENT_TEMPLATES
from app.memory.project_context import get_project_context_store
from app.core.usage_tracker import get_usage_tracker

logger = logging.getLogger(__name__)

TEAM_BUILDER_SYSTEM_PROMPT = """You are Alex, an AI associate helping the user create their AI agent team.

Your goal is to understand their project and propose the right team structure.

The conversation has two phases:
1. DISCOVERY: Ask focused questions to understand the project (domain, goals, team needs, constraints).
   Keep questions concise and conversational. Max 4-5 questions total.

2. PROPOSAL: Once you have enough info, propose a team structure in JSON format and ask for validation.

When proposing a team, respond with:
1. A brief explanation paragraph
2. A JSON block with this exact structure:
```json
{
  "project": {
    "name": "...",
    "description": "...",
    "domain": "..."
  },
  "teams": [
    {
      "template": "dev|marketing|business|product",
      "customizations": {}
    }
  ],
  "ready_to_create": false
}
```

When the user confirms/validates the team, respond with the same JSON but with "ready_to_create": true.

Available team templates: dev (PM + Frontend + Backend), marketing (Lead + Content + Social), business (Finance), product (Designer).

Be concise, professional and encouraging. Respond in the same language as the user."""


MAX_HISTORY_MESSAGES = 50


class TeamBuilderSession:
    def __init__(self):
        self.settings = get_settings()
        self.client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        self.history: list[dict] = []
        self.project_data: Optional[dict] = None
        self.proposed_team: Optional[dict] = None
        self.phase = "discovery"

    async def chat(self, user_message: str) -> AsyncGenerator[str, None]:
        self.history.append({"role": "user", "content": user_message})

        full_response = ""
        async with self.client.messages.stream(
            model=self.settings.claude_model,
            max_tokens=2048,
            system=TEAM_BUILDER_SYSTEM_PROMPT,
            messages=self.history,
        ) as stream:
            async for text in stream.text_stream:
                full_response += text
                yield text
            final_msg = await stream.get_final_message()
            get_usage_tracker().log(
                self.settings.claude_model,
                final_msg.usage.input_tokens,
                final_msg.usage.output_tokens,
            )

        self.history.append({"role": "assistant", "content": full_response})
        if len(self.history) > MAX_HISTORY_MESSAGES:
            self.history = self.history[-MAX_HISTORY_MESSAGES:]

        # Try to extract JSON proposal from the response
        extracted = self._extract_json(full_response)
        if extracted:
            self.proposed_team = extracted
            if extracted.get("ready_to_create"):
                self.phase = "confirmed"
            else:
                self.phase = "proposal"

    def _extract_json(self, text: str) -> Optional[dict]:
        try:
            start = text.find("```json")
            end = text.find("```", start + 6)
            if start != -1 and end != -1:
                json_str = text[start + 7:end].strip()
                return json.loads(json_str)
        except Exception:
            pass
        return None

    async def create_team_from_proposal(self) -> dict:
        if not self.proposed_team:
            return {"error": "No proposal available"}

        factory = get_agent_factory()
        ctx_store = get_project_context_store()

        project = self.proposed_team.get("project", {})
        ctx_store.save_context({
            "name": project.get("name", "Unnamed Project"),
            "description": project.get("description", ""),
            "domain": project.get("domain", ""),
            "conversation": self.history,
        })
        ctx_store.index_text(
            text=f"{project.get('name', '')} — {project.get('description', '')}",
            doc_id="project_overview",
            metadata={"type": "project", "domain": project.get("domain", "")},
        )

        created_teams = []
        created_agents = []

        for team_spec in self.proposed_team.get("teams", []):
            template_key = team_spec.get("template")
            if template_key and template_key in TEAM_TEMPLATES:
                team, agents = factory.create_team_from_template(template_key)
                created_teams.append(team.model_dump())
                created_agents.extend([a.model_dump() for a in agents])

        return {
            "project": project,
            "teams": created_teams,
            "agents": created_agents,
        }

    def is_confirmed(self) -> bool:
        return self.phase == "confirmed"


_session: Optional[TeamBuilderSession] = None


def get_team_builder_session() -> TeamBuilderSession:
    global _session
    if _session is None:
        _session = TeamBuilderSession()
    return _session


def reset_team_builder_session():
    global _session
    _session = None
