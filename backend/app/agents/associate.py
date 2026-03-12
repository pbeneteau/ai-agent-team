"""
The Associate agent chat engine.
Handles the main user conversation, detects intent and delegates tasks.
"""
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Awaitable, Callable, Optional

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.config.prompts import ASSOCIATE_SYSTEM_PROMPT
from app.config.token_budgets import ASSOCIATE_MAX_HISTORY_MESSAGES, ASSOCIATE_MAX_TOKENS
from app.core.agent_factory import get_agent_factory
from app.core.project_brief import render_project_brief_summary
from app.memory.project_context import get_project_context_store
from app.core.document_store import get_document_store
from app.core.structured_json import extract_json_object
from app.core.usage_tracker import get_usage_tracker
from app.models.chat_actions import (
    AssistantAction,
    action_from_payload,
    action_from_tool_use,
    build_assistant_action_tools,
)

logger = logging.getLogger(__name__)

_LEGACY_JSON_BLOCK_RE = re.compile(r"```json\s*[\s\S]*?```", re.IGNORECASE)


@dataclass
class AssociateResponse:
    human_text: str
    action: AssistantAction | None = None
    action_source: str = "none"


@dataclass
class _AssociateActionResolution:
    action: AssistantAction | None
    action_source: str
    request_name: str
    success: bool
    tool_use_error: str | None = None
    legacy_error: str | None = None
    multiple_tool_calls: bool = False


class AssociateChat:
    def __init__(self):
        self.settings = get_settings()
        self.client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        self.history: list[dict] = []

    def _build_system_prompt(self, user_message: str = "") -> str:
        factory = get_agent_factory()
        ctx_store = get_project_context_store()
        doc_store = get_document_store()

        teams = factory.list_teams()

        if teams:
            team_lines = []
            for team in teams:
                team_agents = factory.get_team_agents(team.id)
                agent_names = ", ".join(
                    f"{a.name} (agent_id: {a.id}, title: {a.title}, status: {a.status.value})"
                    for a in team_agents
                )
                team_lines.append(f"- {team.name} (team_id: {team.id}): {agent_names}")
            team_context = "\n".join(team_lines)
        else:
            team_context = "No teams created yet. Guide the user to build their team."

        project_brief = ctx_store.get_active_brief()
        project_context = (
            render_project_brief_summary(project_brief.model_dump(mode="json"), include_meta=True)
            if project_brief
            else "No project defined yet."
        )

        # RAG: inject relevant document excerpts based on the current message
        documents_context = ""
        if user_message:
            docs_excerpt = doc_store.format_for_context(user_message, max_chars=1500)
            if docs_excerpt:
                documents_context = docs_excerpt
        elif doc_store.list_documents():
            n = len(doc_store.list_documents())
            documents_context = f"({n} document(s) uploaded — excerpts will appear when relevant to the conversation)"

        return ASSOCIATE_SYSTEM_PROMPT.format(
            team_context=team_context,
            project_context=project_context,
            documents_context=documents_context,
            default_lead_model_tier=self.settings.default_team_lead_model_tier.value,
            default_agent_model_tier=self.settings.default_agent_model_tier.value,
        )

    async def stream_response(
        self,
        user_message: str,
        *,
        tagged_doc_ids: list[str] | None = None,
        on_text_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> AssociateResponse:
        # Build the effective message: prepend explicitly tagged document content
        effective_message = user_message
        if tagged_doc_ids:
            doc_store = get_document_store()
            injected = _build_tagged_docs_context(doc_store, tagged_doc_ids)
            if injected:
                effective_message = f"{injected}\n\n---\n\nUser message: {user_message}"

        self.history.append({"role": "user", "content": effective_message})
        system = self._build_system_prompt(user_message)

        full_response = ""
        model = self.settings.claude_model
        async with self.client.messages.stream(
            model=model,
            max_tokens=ASSOCIATE_MAX_TOKENS,
            system=system,
            messages=self.history,
            tools=build_assistant_action_tools(),
        ) as stream:
            async for text in stream.text_stream:
                full_response += text
                if on_text_chunk:
                    await on_text_chunk(text)
            # Capture token usage while still inside the stream context
            final_msg = await stream.get_final_message()
            get_usage_tracker().log(
                model=model,
                input_tokens=final_msg.usage.input_tokens,
                output_tokens=final_msg.usage.output_tokens,
            )

        visible_response = full_response
        resolution = self._resolve_action(final_msg.content, full_response)
        action = resolution.action
        action_source = resolution.action_source
        if "legacy_json" in action_source:
            visible_response = self._strip_legacy_action_block(full_response)

        get_usage_tracker().log_structured_output(
            request_name=resolution.request_name,
            generation_channel=action_source,
            success=resolution.success,
            failure_kind=None if resolution.success else _associate_failure_kind(resolution),
            stop_reason=str(getattr(final_msg, "stop_reason", None) or "").strip() or None,
            validation_failed=False,
            failure_message=None if resolution.success else (resolution.tool_use_error or resolution.legacy_error),
        )
        if not resolution.success or resolution.tool_use_error or resolution.legacy_error:
            logger.warning(
                "Associate structured action degraded channel=%s success=%s request=%s tool_use_error=%r legacy_error=%r multiple_tool_calls=%s stop_reason=%s",
                resolution.action_source,
                resolution.success,
                resolution.request_name,
                resolution.tool_use_error,
                resolution.legacy_error,
                resolution.multiple_tool_calls,
                getattr(final_msg, "stop_reason", None),
            )

        self.history.append({"role": "assistant", "content": visible_response})
        if len(self.history) > ASSOCIATE_MAX_HISTORY_MESSAGES:
            self.history = self.history[-ASSOCIATE_MAX_HISTORY_MESSAGES:]
        return AssociateResponse(
            human_text=visible_response,
            action=action,
            action_source=action_source,
        )

    def _resolve_action(self, blocks: list[object] | None, text: str) -> _AssociateActionResolution:
        tool_blocks = [
            block for block in (blocks or [])
            if getattr(block, "type", None) == "tool_use"
        ]
        multiple_tool_calls = len(tool_blocks) > 1
        tool_use_error: str | None = None
        request_name = "associate_chat_response"

        if tool_blocks:
            tool_block = tool_blocks[0]
            request_name = _associate_request_name_from_tool_name(getattr(tool_block, "name", ""))
            if multiple_tool_calls:
                logger.warning("Associate returned multiple tool calls; only the first one will be used.")
            try:
                action = action_from_tool_use(
                    getattr(tool_block, "name", ""),
                    getattr(tool_block, "input", None) or {},
                )
                logger.info("Associate action detected: %s", action)
                return _AssociateActionResolution(
                    action=action,
                    action_source="tool_use",
                    request_name=_associate_observability_request_name(action),
                    success=True,
                    multiple_tool_calls=multiple_tool_calls,
                )
            except Exception as exc:
                tool_use_error = str(exc)
                logger.debug(
                    "Invalid associate tool call: %s (tool=%s)",
                    exc,
                    getattr(tool_block, "name", None),
                )

        legacy_attempted = "```json" in text or '"action"' in text
        legacy_error: str | None = None
        if legacy_attempted:
            try:
                payload = extract_json_object(text)
                action = action_from_payload(payload)
                logger.info("Associate legacy action detected: %s", action)
                action_source = "legacy_json" if tool_use_error is None else "tool_use_invalid_legacy_json"
                return _AssociateActionResolution(
                    action=action,
                    action_source=action_source,
                    request_name=_associate_observability_request_name(action),
                    success=True,
                    tool_use_error=tool_use_error,
                    multiple_tool_calls=multiple_tool_calls,
                )
            except Exception as exc:
                legacy_error = str(exc)
                logger.debug("No valid legacy associate action block found: %s", exc)

        if tool_use_error is not None:
            return _AssociateActionResolution(
                action=None,
                action_source="tool_use_invalid_text_only",
                request_name=request_name,
                success=False,
                tool_use_error=tool_use_error,
                legacy_error=legacy_error,
                multiple_tool_calls=multiple_tool_calls,
            )
        if legacy_error is not None:
            return _AssociateActionResolution(
                action=None,
                action_source="legacy_json_invalid_text_only",
                request_name=request_name,
                success=False,
                legacy_error=legacy_error,
                multiple_tool_calls=multiple_tool_calls,
            )
        return _AssociateActionResolution(
            action=None,
            action_source="text_only",
            request_name=request_name,
            success=True,
            multiple_tool_calls=multiple_tool_calls,
        )

    def _extract_action_from_response(self, blocks: list[object] | None) -> AssistantAction | None:
        return self._resolve_action(blocks, "").action

    def _extract_legacy_action(self, text: str) -> AssistantAction | None:
        resolution = self._resolve_action([], text)
        if "legacy_json" in resolution.action_source:
            return resolution.action
        return None

    def _strip_legacy_action_block(self, text: str) -> str:
        stripped = _LEGACY_JSON_BLOCK_RE.sub("", text).strip()
        return stripped

    def extract_action(self, text: str) -> Optional[dict]:
        action = self._extract_legacy_action(text)
        return action.model_dump(mode="json") if action else None

    def reset_history(self):
        self.history = []


def _build_tagged_docs_context(doc_store, doc_ids: list[str]) -> str:
    """Return the full content of explicitly tagged documents to inject into the user message."""
    parts = ["The user has explicitly referenced the following document(s). Read them carefully:\n"]
    for doc_id in doc_ids:
        meta = doc_store.get_document(doc_id)
        if not meta:
            continue
        # Fetch all chunks for this document (by filtering on doc_id metadata)
        try:
            all_results = doc_store.vector_store.query(
                collection_name="user_documents",
                query_texts=["document content"],
                n_results=100,
            )
            chunks = [
                r["document"] for r in all_results
                if r.get("metadata", {}).get("doc_id") == doc_id and r.get("document")
            ]
        except Exception:
            chunks = []
        content = "\n".join(chunks) if chunks else "(contenu non disponible)"
        parts.append(f"### @{meta.filename}\n{content}\n")

    return "\n".join(parts) if len(parts) > 1 else ""


def _associate_observability_request_name(action: AssistantAction | None) -> str:
    if action is None:
        return "associate_chat_response"

    action_name = getattr(action, "action", "")
    if action_name == "gather_info":
        return "associate_gather_info"
    if action_name == "start_team_builder":
        return "associate_start_team_builder"
    if action_name == "trigger_learning":
        return "associate_trigger_learning"
    if action_name in {"plan_task", "plan_mode", "create_task"}:
        kind = str(getattr(action, "kind", "") or "").strip().lower()
        if kind == "team":
            return "associate_propose_team_plan"
        return "associate_propose_task_plan"
    if action_name in {"plan_team", "create_team_direct"}:
        return "associate_propose_team_plan"
    return "associate_chat_action"


def _associate_request_name_from_tool_name(tool_name: str | None) -> str:
    name = str(tool_name or "").strip()
    if name == "gather_info":
        return "associate_gather_info"
    if name == "start_team_builder":
        return "associate_start_team_builder"
    if name == "trigger_learning":
        return "associate_trigger_learning"
    if name == "propose_task_plan":
        return "associate_propose_task_plan"
    if name == "propose_team_plan":
        return "associate_propose_team_plan"
    return "associate_chat_action"


def _associate_failure_kind(resolution: _AssociateActionResolution) -> str:
    if resolution.tool_use_error:
        return "tool_use"
    if resolution.legacy_error:
        return "legacy_json"
    return "unknown"


@lru_cache(maxsize=1)
def get_associate_chat() -> AssociateChat:
    return AssociateChat()
