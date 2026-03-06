"""
The Associate agent chat engine.
Handles the main user conversation, detects intent and delegates tasks.
"""
import json
import logging
from functools import lru_cache
from typing import AsyncGenerator, Optional
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.core.agent_factory import get_agent_factory
from app.memory.project_context import get_project_context_store
from app.memory.skills_store import get_skills_store
from app.core.document_store import get_document_store
from app.core.usage_tracker import get_usage_tracker

logger = logging.getLogger(__name__)

ASSOCIATE_SYSTEM_PROMPT = """You are Alex, the user's AI associate and right-hand. You are the top-level agent in their AI team.

## Your role
- Be the user's trusted strategic partner
- Understand their needs and delegate to the right team members
- Synthesize results and report back clearly
- Help them build and manage their AI agent team
- Coach sub-agents by writing skills to their workspace (use agent_skill_write)
- Be proactive, concise, and action-oriented

## Current team context
{team_context}

## Project context  
{project_context}

## Your tools
- **skill_write / skill_read / skill_list** — manage your own skill documentation
- **agent_skill_write / agent_skill_read** — write or read skills for any team member (use to coach them)
- **web_search, web_browser** — research and browse
- **file_read / file_write** — work with files in your workspace

## Shared documents
The user can upload documents (PDF, DOCX, etc.) to give you context.
Relevant excerpts are injected automatically below when they match the conversation.
{documents_context}

## How to handle requests
- For team building: guide the user through creating their team
- For work tasks: identify which team(s) should handle it and respond with a task delegation plan
- For questions: answer directly or search for information
- For status updates: report on team progress
- To coach a team member: use agent_skill_write to add expertise to their skills/ directory

When you need to delegate a task to a team, include a JSON action block in your response:
```json
{{"action": "create_task", "title": "...", "description": "...", "team_id": "...", "priority": "low|medium|high"}}
```

When you have gathered enough information and are ready to create the team (user has validated the design), create it directly — no need to switch modes:
```json
{{"action": "create_team_direct", "project": {{"name": "...", "description": "...", "domain": "..."}}, "teams": [{{"name": "Team Name", "description": "...", "domain": "...", "agents": [{{"name": "Sophie", "title": "Fundraising Lead", "specialization": "fundraising", "goal": "Raise the seed round...", "backstory": "Expert in...", "is_lead": true, "model_tier": "opus"}}, {{"name": "Marcus", "title": "Business Analyst", "specialization": "business_analysis", "goal": "...", "backstory": "...", "model_tier": "sonnet"}}]}}]}}
```
Rules for create_team_direct:
- Put all agents in the most logical team grouping
- First agent in each team's agents list is the lead (or set "is_lead": true explicitly)
- Leads get model_tier "opus", specialists get "sonnet"
- Always include "goal" and "backstory" tailored to the project context
- Only use built-in templates (dev/marketing/business/product) if they perfectly match; otherwise use custom agents

If you truly need a discovery conversation first (requirements completely unknown):
```json
{{"action": "start_team_builder"}}
```
Prefer create_team_direct in all cases where you already know the team structure.

When you need to collect structured information from the user (e.g., to define a project, gather requirements), use a gather_info form instead of a back-and-forth conversation:
```json
{{"action": "gather_info", "title": "Titre du formulaire", "description": "Explication courte (optionnel)", "fields": [{{"id": "field_id", "label": "Label", "type": "text|textarea|select", "placeholder": "...", "options": ["opt1", "opt2"], "required": true}}]}}
```
The user will see a dynamic form and submit their answers in one go. Use this for initial project setup, team creation requirements, task briefings, etc.

Respond in the same language as the user. Be warm, professional, and proactive."""


MAX_HISTORY_MESSAGES = 50


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
                agent_names = ", ".join(f"{a.name} ({a.title})" for a in team_agents)
                team_lines.append(f"- {team.name}: {agent_names}")
            team_context = "\n".join(team_lines)
        else:
            team_context = "No teams created yet. Guide the user to build their team."

        project_ctx = ctx_store.load_context()
        if project_ctx:
            project_context = f"Project: {project_ctx.get('name', 'Unknown')} — {project_ctx.get('description', '')}"
        else:
            project_context = "No project defined yet."

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
        )

    async def chat(self, user_message: str, tagged_doc_ids: list[str] | None = None) -> AsyncGenerator[str, None]:
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
            max_tokens=2048,
            system=system,
            messages=self.history,
        ) as stream:
            async for text in stream.text_stream:
                full_response += text
                yield text
            # Capture token usage while still inside the stream context
            final_msg = await stream.get_final_message()
            get_usage_tracker().log(
                model=model,
                input_tokens=final_msg.usage.input_tokens,
                output_tokens=final_msg.usage.output_tokens,
            )

        self.history.append({"role": "assistant", "content": full_response})
        if len(self.history) > MAX_HISTORY_MESSAGES:
            self.history = self.history[-MAX_HISTORY_MESSAGES:]

    def _extract_and_queue_action(self, text: str) -> Optional[dict]:
        try:
            start = text.find("```json")
            end = text.find("```", start + 6)
            if start != -1 and end != -1:
                json_str = text[start + 7:end].strip()
                action = json.loads(json_str)
                logger.info("Associate action detected: %s", action)
                return action
        except (json.JSONDecodeError, ValueError):
            logger.debug("No valid JSON action block found in associate response")
        return None

    def extract_action(self, text: str) -> Optional[dict]:
        return self._extract_and_queue_action(text)

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


@lru_cache(maxsize=1)
def get_associate_chat() -> AssociateChat:
    return AssociateChat()
