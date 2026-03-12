"""
Conversational team builder.
Drives the dialogue to understand the project, then proposes and creates the agent team.
"""
import logging
from typing import Optional, AsyncGenerator

from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field

from app.config import get_settings
from app.core.structured_json import StructuredJsonError, parse_structured_json_text
from app.core.usage_tracker import get_usage_tracker
from app.core.universal_plan import TeamPlanExecutor, UniversalPlanSession

logger = logging.getLogger(__name__)

TEAM_BUILDER_SYSTEM_PROMPT = """You are Alex, an AI associate helping the user create their AI agent team.

Your goal is to understand their project and propose the right team structure.

The conversation has two phases:
1. DISCOVERY: Ask focused questions to understand the project (domain, goals, team needs, constraints).
   Keep questions concise and conversational. Max 4-5 questions total.

2. PROPOSAL: Once you have enough info, propose a team structure in JSON format and ask for validation.

When proposing a team, respond with:
1. A single short explanation sentence
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

Keep all prose minimal. Avoid repeating the project context. The JSON block is the source of truth.

Be concise, professional and encouraging. Respond in the same language as the user."""


MAX_HISTORY_MESSAGES = 50


class _TeamBuilderProposalPayload(BaseModel):
    project: dict = Field(default_factory=dict)
    teams: list[dict] = Field(default_factory=list)
    ready_to_create: bool = False


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
            max_tokens=1400,
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
        if "```json" not in text and '"ready_to_create"' not in text:
            return None
        try:
            structured = parse_structured_json_text(
                raw_text=text,
                response_model=_TeamBuilderProposalPayload,
                request_name="team_builder_proposal",
            )
            return structured.value.model_dump(mode="json")
        except StructuredJsonError as exc:
            logger.debug(
                "No valid team builder proposal found: %s (preview=%r)",
                exc,
                exc.telemetry.raw_preview,
            )
        return None

    async def create_team_from_proposal(self) -> dict:
        if not self.proposed_team:
            return {"error": "No proposal available"}

        project = self.proposed_team.get("project", {})
        logger.warning("Using deprecated legacy team builder flow; delegating creation to TeamPlanExecutor.")
        draft = UniversalPlanSession(session_id="legacy-team-builder").set_team_draft(
            {
                "action": "plan_team",
                "kind": "team",
                "title": project.get("name", "Unnamed Project"),
                "summary": project.get("description", "")[:240],
                "project": project,
                "teams": self.proposed_team.get("teams", []),
            }
        )

        async def _noop_broadcast(_message: dict) -> None:
            return

        return await TeamPlanExecutor().execute(draft, _noop_broadcast)

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
