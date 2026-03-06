"""
Agent learning phase.
Each agent researches its domain, learns the project context,
writes its skills as Markdown files, and sets up its workspace.
"""
import asyncio
import logging
from anthropic import AsyncAnthropic

from app.config import get_settings
from app.models.agent import AgentConfig, AgentStatus
from app.core.agent_factory import get_agent_factory
from app.memory.skills_store import get_skills_store
from app.memory.project_context import get_project_context_store
from app.core.usage_tracker import get_usage_tracker

logger = logging.getLogger(__name__)

LEARNING_SYSTEM_PROMPT = """You are {agent_name}, a {agent_title} in an AI agent team.

## About the project
{project_context}

## Your workspace
{workspace_path}

## Your task
Write TWO Markdown documents:

### Document 1 — core_skills.md
Your professional expertise, independent of any specific project:
1. Core methodologies and frameworks you rely on
2. Decision-making approach and mental models
3. Best practices you always apply
4. Tools and technologies you master
5. How you collaborate and communicate with teammates
6. Key metrics and KPIs you track
7. How you use your workspace (downloads/, repos/, output/, tmp/, skills/)

### Document 2 — project_context.md
What YOU specifically need to know about this project to do your job well.
Translate the project description into YOUR domain language:
- As a developer: tech stack choices, architecture decisions, code conventions, third-party services
- As a marketer: target audience profile, brand voice, competitors, channels, messaging pillars
- As a PM: delivery methodology, priorities framework, definition of done, team rituals
- As a finance analyst: business model, revenue streams, cost structure, key financial KPIs
- As a designer: design principles, target users, accessibility requirements, toolchain

Only include what is directly relevant to your specialization.
Exclude anything that belongs to another domain.
If information is missing, flag it as "TBD — needs clarification from the user."

Be concise and actionable. These files are your permanent reference — you will read them before every task."""

PROJECT_BRIEFING_PROMPT = """You are Alex, the AI Associate. A new team has been created and you must now write
domain-scoped project context files for each agent in their workspace.

## Project description provided by the user:
{project_context}

## Team members and their domains:
{team_members}

For each agent, write a focused project_context.md file that contains ONLY what that agent
needs to know to do their job on this specific project.

Keep each file under 400 words. Be precise, avoid fluff.
Organize by agent in your response using this format:

---AGENT:{{agent_id}}---
(markdown content here)
---END---

Repeat for each agent. Do not include agents outside the list above."""


def _build_project_summary(ctx: dict) -> str:
    parts = [
        f"Project: {ctx.get('name', 'Unknown')}",
        f"Description: {ctx.get('description', 'No description provided yet.')}",
    ]
    if ctx.get("domain"):
        parts.append(f"Domain: {ctx['domain']}")
    if ctx.get("tech_stack"):
        parts.append(f"Tech stack: {ctx['tech_stack']}")
    if ctx.get("target_audience"):
        parts.append(f"Target audience: {ctx['target_audience']}")
    if ctx.get("business_model"):
        parts.append(f"Business model: {ctx['business_model']}")
    if ctx.get("notes"):
        parts.append(f"Additional context: {ctx['notes']}")
    return "\n".join(parts)


async def run_learning_phase(agent: AgentConfig, broadcast_callback=None) -> bool:
    settings = get_settings()
    factory = get_agent_factory()
    ctx_store = get_project_context_store()

    factory.update_agent_status(agent.id, AgentStatus.LEARNING)
    if broadcast_callback:
        await broadcast_callback({
            "type": "agent_status",
            "data": {"agent_id": agent.id, "status": "learning", "name": agent.name},
        })

    try:
        from app.core.workspace import get_workspace_manager
        wm = get_workspace_manager()
        workspace = wm.get(agent.id, agent.name, agent.title)
        workspace_path = str(workspace.root)

        project_ctx = ctx_store.load_context() or {}
        project_summary = _build_project_summary(project_ctx)

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        system_prompt = LEARNING_SYSTEM_PROMPT.format(
            agent_name=agent.name,
            agent_title=agent.title,
            project_context=project_summary,
            workspace_path=workspace_path,
        )

        response = await client.messages.create(
            model=settings.claude_model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": (
                    f"Write both documents for your role as {agent.title}.\n"
                    f"Specialization: {agent.specialization}\n"
                    f"Goal: {agent.goal}\n\n"
                    f"Backstory: {agent.backstory}\n\n"
                    "Separate the two documents clearly with:\n"
                    "## DOCUMENT: core_skills\n(content)\n\n## DOCUMENT: project_context\n(content)"
                ),
            }],
        )

        get_usage_tracker().log(settings.claude_model, response.usage.input_tokens, response.usage.output_tokens)
        raw = response.content[0].text
        # Split the two documents
        core_skills_content, project_ctx_content = _split_learning_output(raw)

        workspace.write_skill("core_skills", core_skills_content, author="learning_phase")
        workspace.write_skill("project_context", project_ctx_content, author="learning_phase")
        workspace.write_profile({
            "id": agent.id,
            "name": agent.name,
            "title": agent.title,
            "specialization": agent.specialization,
            "goal": agent.goal,
            "team_id": agent.team_id,
            "workspace_path": workspace_path,
        })

        workspace.write(
            "output/profile.md",
            f"# {agent.name} — {agent.title}\n\n"
            f"**Specialization:** {agent.specialization}\n"
            f"**Goal:** {agent.goal}\n"
            f"**Workspace:** `{workspace_path}`\n\n"
            f"## Backstory\n\n{agent.backstory}\n",
        )

        ctx_store.index_text(
            text=f"{agent.name} ({agent.title}): {agent.goal}\n{core_skills_content[:500]}",
            doc_id=f"agent_{agent.id}",
            metadata={"type": "agent", "agent_id": agent.id, "title": agent.title},
        )

        factory.update_agent_status(agent.id, AgentStatus.READY)
        if broadcast_callback:
            await broadcast_callback({
                "type": "agent_status",
                "data": {
                    "agent_id": agent.id,
                    "status": "ready",
                    "name": agent.name,
                    "workspace_path": workspace_path,
                },
            })
        logger.info(f"Agent {agent.name} learning complete — workspace: {workspace_path}")
        return True

    except Exception as e:
        logger.exception(f"Learning phase failed for {agent.name}: {e}")
        factory.update_agent_status(agent.id, AgentStatus.ERROR)
        if broadcast_callback:
            await broadcast_callback({
                "type": "agent_status",
                "data": {"agent_id": agent.id, "status": "error", "name": agent.name, "error": str(e)},
            })
        return False


def _split_learning_output(raw: str) -> tuple[str, str]:
    """Split the LLM response into (core_skills, project_context) documents."""
    marker_core = "## DOCUMENT: core_skills"
    marker_ctx = "## DOCUMENT: project_context"

    core = ""
    project = ""

    if marker_core in raw and marker_ctx in raw:
        idx_core = raw.index(marker_core) + len(marker_core)
        idx_ctx = raw.index(marker_ctx)
        core = raw[idx_core:idx_ctx].strip()
        project = raw[raw.index(marker_ctx) + len(marker_ctx):].strip()
    else:
        # Fallback: put everything in core_skills
        core = raw
        project = "# Project Context\n\nTBD — project briefing not yet completed."

    return core, project


async def run_project_briefing(team_id: str, broadcast_callback=None):
    """
    After the user provides rich project context, Alex writes a domain-scoped
    project_context.md to each agent's workspace. This can be run multiple times
    as the project evolves.
    """
    settings = get_settings()
    factory = get_agent_factory()
    ctx_store = get_project_context_store()

    project_ctx = ctx_store.load_context() or {}
    if not project_ctx:
        logger.warning("No project context found — skipping briefing")
        return

    agents = factory.get_team_agents(team_id)
    if not agents:
        return

    project_summary = _build_project_summary(project_ctx)
    team_members = "\n".join(
        f"- {a.name} (id: {a.id}) — {a.title}, specialization: {a.specialization}"
        for a in agents
    )

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.claude_model_opus,
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": PROJECT_BRIEFING_PROMPT.format(
                project_context=project_summary,
                team_members=team_members,
            ),
        }],
    )

    get_usage_tracker().log(settings.claude_model_opus, response.usage.input_tokens, response.usage.output_tokens)
    raw = response.content[0].text
    _distribute_briefing(raw, agents, factory)

    if broadcast_callback:
        await broadcast_callback({
            "type": "briefing_complete",
            "data": {"team_id": team_id, "agent_count": len(agents)},
        })
    logger.info(f"Project briefing distributed to {len(agents)} agents in team {team_id}")


def _distribute_briefing(raw: str, agents, factory):
    """Parse Alex's response and write project_context.md to each agent's workspace."""
    from app.core.workspace import get_workspace_manager
    wm = get_workspace_manager()

    for agent in agents:
        start_marker = f"---AGENT:{agent.id}---"
        end_marker = "---END---"
        if start_marker in raw:
            start = raw.index(start_marker) + len(start_marker)
            end = raw.index(end_marker, start) if end_marker in raw[start:] else len(raw)
            content = raw[start:end].strip()
            if content:
                workspace = wm.get(agent.id, agent.name, agent.title)
                workspace.write_skill("project_context", content, author="alex_briefing")
                logger.info(f"Project context written for {agent.name}")


TARGETED_REBRIEFING_PROMPT = """You are {agent_name}, a {agent_title} in an AI agent team.

## Current project context
{project_summary}

## Your current project_context.md
{current_project_context}

## New knowledge source: "{source_name}"
{document_text}

## Your task
Rewrite your project_context.md, incorporating the relevant information from this new source.
- Keep only what is relevant to YOUR role as {agent_title}
- Integrate new facts, data, and insights that will help you do your job better
- Preserve existing important context; update or extend it where the new source adds value
- If information conflicts, prefer the new source (it's more recent)
- Do NOT include information that belongs to other domains
- Keep it under 700 words, actionable and precise
- Write the full updated file, not just the additions

Write only the Markdown content for project_context.md. No preamble."""


DOCUMENT_REBRIEFING_PROMPT = """You are updating the project_context.md files for an AI agent team.

## Project context
{project_summary}

## New document shared by the user: "{doc_filename}"
{doc_text}

## Team members
{team_members}

For each agent, rewrite their project_context.md to incorporate relevant information from this document.
Focus only on what is relevant to each agent's specialization. Ignore sections that don't apply.
Keep each file under 600 words. Be precise and actionable.

Format your response as:
---AGENT:{{agent_id}}---
(updated markdown content)
---END---

Repeat for every agent listed above."""


async def run_targeted_rebriefing(agent_id: str, document_text: str, source_name: str, broadcast_callback=None) -> bool:
    """
    Update a single agent's project_context.md with content from a new document or URL.
    """
    from app.core.workspace import get_workspace_manager

    settings = get_settings()
    factory = get_agent_factory()
    ctx_store = get_project_context_store()

    agent = factory.get_agent(agent_id)
    if not agent:
        logger.error(f"Agent {agent_id} not found for targeted rebriefing")
        return False

    project_ctx = ctx_store.load_context() or {}
    project_summary = _build_project_summary(project_ctx)

    wm = get_workspace_manager()
    workspace = wm.get(agent.id, agent.name, agent.title)
    current_ctx = workspace.read_skill("project_context") or "No existing project context."

    if broadcast_callback:
        await broadcast_callback({
            "type": "agent_status",
            "data": {"agent_id": agent.id, "status": "learning", "name": agent.name},
        })

    try:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        prompt = TARGETED_REBRIEFING_PROMPT.format(
            agent_name=agent.name,
            agent_title=agent.title,
            project_summary=project_summary,
            current_project_context=current_ctx[:2000],
            source_name=source_name,
            document_text=document_text[:12000],
        )
        response = await client.messages.create(
            model=settings.claude_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        get_usage_tracker().log(settings.claude_model, response.usage.input_tokens, response.usage.output_tokens)
        new_ctx = response.content[0].text.strip()
        workspace.write_skill("project_context", new_ctx, author=f"knowledge:{source_name}")
        logger.info(f"project_context updated for {agent.name} from '{source_name}'")

        if broadcast_callback:
            await broadcast_callback({
                "type": "agent_status",
                "data": {"agent_id": agent.id, "status": "ready", "name": agent.name},
            })
        return True

    except Exception as e:
        logger.exception(f"Targeted rebriefing failed for {agent.name}: {e}")
        if broadcast_callback:
            await broadcast_callback({
                "type": "agent_status",
                "data": {"agent_id": agent.id, "status": "ready", "name": agent.name, "error": str(e)},
            })
        return False


async def run_document_rebriefing(doc_id: str, broadcast_callback=None):
    """
    Re-generate project_context.md for every agent across all teams,
    incorporating the content of a newly shared document.
    """
    from app.core.document_store import get_document_store
    from app.core.workspace import get_workspace_manager

    settings = get_settings()
    factory = get_agent_factory()
    ctx_store = get_project_context_store()

    doc_store = get_document_store()
    meta = doc_store.get_document(doc_id)
    if not meta:
        logger.error(f"Document {doc_id} not found for rebriefing")
        return

    doc_text = doc_store.get_full_text(doc_id, max_chars=15000)
    if not doc_text:
        logger.warning(f"Document {doc_id} has no extractable text")
        return

    project_ctx = ctx_store.load_context() or {}
    project_summary = _build_project_summary(project_ctx)

    all_agents = [a for a in factory.list_agents() if a.team_id is not None]
    if not all_agents:
        logger.warning("No team agents found for rebriefing")
        return

    team_members = "\n".join(
        f"- {a.name} (id: {a.id}) — {a.title}, specialization: {a.specialization}"
        for a in all_agents
    )

    if broadcast_callback:
        await broadcast_callback({
            "type": "briefing_start",
            "data": {"doc_id": doc_id, "filename": meta.filename, "agent_count": len(all_agents)},
        })

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    prompt = DOCUMENT_REBRIEFING_PROMPT.format(
        project_summary=project_summary,
        doc_filename=meta.filename,
        doc_text=doc_text,
        team_members=team_members,
    )

    try:
        response = await client.messages.create(
            model=settings.claude_model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        get_usage_tracker().log(settings.claude_model, response.usage.input_tokens, response.usage.output_tokens)
        raw = response.content[0].text
    except Exception as e:
        logger.exception(f"Document rebriefing LLM call failed: {e}")
        return

    wm = get_workspace_manager()
    agents_by_id = {a.id: a for a in all_agents}

    import re
    blocks = re.findall(r"---AGENT:([a-f0-9\-]+)---\n([\s\S]*?)---END---", raw)
    updated = 0
    for agent_id, content in blocks:
        agent = agents_by_id.get(agent_id.strip())
        if not agent:
            continue
        workspace = wm.get(agent.id, agent.name, agent.title)
        workspace.write_skill("project_context", content.strip(), author=f"doc_rebriefing:{meta.filename}")
        logger.info(f"project_context updated for {agent.name} from document '{meta.filename}'")
        updated += 1

    if broadcast_callback:
        await broadcast_callback({
            "type": "briefing_complete",
            "data": {"doc_id": doc_id, "filename": meta.filename, "agents_updated": updated},
        })
    logger.info(f"Document rebriefing complete: {updated}/{len(all_agents)} agents updated")


async def run_agent_research(agent_id: str, topic: str, broadcast_callback=None) -> bool:
    """
    Run an autonomous web research session for an agent using CrewAI + web_search.
    The agent searches, synthesises, and saves findings to skills/research_{slug}.md.
    Requires SERPER_API_KEY to be set in settings.
    """
    import re
    import os
    from concurrent.futures import ThreadPoolExecutor

    settings = get_settings()
    factory = get_agent_factory()
    ctx_store = get_project_context_store()

    agent_cfg = factory.get_agent(agent_id)
    if not agent_cfg:
        logger.error(f"Agent {agent_id} not found for research")
        return False

    # Make SERPER_API_KEY available to SerperDevTool (reads from env)
    if settings.serper_api_key:
        os.environ["SERPER_API_KEY"] = settings.serper_api_key

    slug = re.sub(r"[^\w]", "_", topic.lower())[:40]
    skill_name = f"research_{slug}"

    project_ctx = ctx_store.load_context() or {}
    project_summary = _build_project_summary(project_ctx)

    from app.core.workspace import get_workspace_manager
    wm = get_workspace_manager()
    workspace = wm.get(agent_cfg.id, agent_cfg.name, agent_cfg.title)
    current_project_ctx = workspace.read_skill("project_context") or ""

    if broadcast_callback:
        await broadcast_callback({
            "type": "agent_status",
            "data": {"agent_id": agent_id, "status": "learning", "name": agent_cfg.name, "task": f"Recherche : {topic}"},
        })

    try:
        from crewai import Agent as CrAgent, Crew, Task as CrTask
        from app.agents.base_agent import build_llm
        from app.tools.registry import get_tools_for_agent
        from app.models.agent import ModelTier

        tools = get_tools_for_agent(agent_cfg.tools, agent_cfg.workspace_path)

        llm = build_llm(agent_cfg.model_tier, agent_cfg.max_tokens)
        backstory = (
            f"{agent_cfg.backstory}\n\n"
            f"## Project context\n{current_project_ctx[:1500]}\n\n"
            f"## Project overview\n{project_summary}"
        )

        crewai_agent = CrAgent(
            role=agent_cfg.title,
            goal=agent_cfg.goal,
            backstory=backstory,
            llm=llm,
            tools=[t for t in tools if t is not None],
            verbose=True,
            max_iter=10,
        )

        task = CrTask(
            description=(
                f"Research the following topic thoroughly: **{topic}**\n\n"
                f"As {agent_cfg.name} ({agent_cfg.title}), focus on what is most relevant to your role "
                f"and to the project context above.\n\n"
                f"Instructions:\n"
                f"1. Perform 3–5 targeted web searches on different angles of the topic\n"
                f"2. Browse 2–3 of the most promising result pages for deeper content\n"
                f"3. Synthesise your findings into a structured Markdown document\n"
                f"4. Save it using skill_write with skill_name='{skill_name}'\n\n"
                f"The document should include: key facts, useful frameworks, relevant data points, "
                f"sources cited, and actionable insights for your role."
            ),
            expected_output=f"A saved skill file '{skill_name}.md' with synthesised research findings.",
            agent=crewai_agent,
        )

        crew = Crew(agents=[crewai_agent], tasks=[task], verbose=True)

        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            await loop.run_in_executor(executor, crew.kickoff)

        logger.info(f"Research complete for {agent_cfg.name}: topic='{topic}', skill='{skill_name}'")
        if broadcast_callback:
            await broadcast_callback({
                "type": "agent_status",
                "data": {"agent_id": agent_id, "status": "ready", "name": agent_cfg.name},
            })
            await broadcast_callback({
                "type": "research_complete",
                "data": {"agent_id": agent_id, "topic": topic, "skill_name": skill_name},
            })
        return True

    except Exception as e:
        logger.exception(f"Research failed for {agent_cfg.name}: {e}")
        if broadcast_callback:
            await broadcast_callback({
                "type": "agent_status",
                "data": {"agent_id": agent_id, "status": "ready", "name": agent_cfg.name},
            })
        return False


async def run_learning_phase_for_team(team_id: str, broadcast_callback=None):
    factory = get_agent_factory()
    agents = factory.get_team_agents(team_id)
    tasks = [run_learning_phase(agent, broadcast_callback) for agent in agents]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    logger.info(f"Learning phase complete for team {team_id}: {results}")
