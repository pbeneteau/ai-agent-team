"""
Tool registry — maps tool names to CrewAI-compatible tool instances.

File-based tools (file_read, file_write, code_execution, github) are
scoped to the agent's workspace directory when an agent_id is provided.
This prevents cross-agent file system pollution.
"""
import os
import subprocess
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def _build_web_search_tool():
    try:
        from crewai_tools import SerperDevTool
        return SerperDevTool()
    except Exception:
        try:
            from crewai_tools import EXASearchTool
            return EXASearchTool()
        except Exception as e:
            logger.warning(f"Web search tool unavailable: {e}")
            return None


def _build_file_read_tool(workspace_path: Optional[str] = None):
    try:
        from crewai_tools import FileReadTool
        if workspace_path:
            return FileReadTool(file_path=workspace_path)
        return FileReadTool()
    except Exception as e:
        logger.warning(f"FileReadTool unavailable: {e}")
        return None


def _build_file_write_tool(workspace_path: Optional[str] = None):
    try:
        from crewai_tools import FileWriterTool
        return FileWriterTool()
    except Exception as e:
        logger.warning(f"FileWriterTool unavailable: {e}")
        return None


def _build_code_execution_tool():
    try:
        from crewai_tools import CodeInterpreterTool
        return CodeInterpreterTool()
    except Exception as e:
        logger.warning(f"CodeInterpreterTool unavailable: {e}")
        return None


def _build_github_tool():
    from app.config import get_settings
    settings = get_settings()
    if not settings.github_token:
        return None
    try:
        from crewai_tools import GithubSearchTool
        return GithubSearchTool(gh_token=settings.github_token)
    except Exception as e:
        logger.warning(f"GithubSearchTool unavailable: {e}")
        return None


def _build_web_browser_tool():
    try:
        from crewai_tools import ScrapeWebsiteTool
        return ScrapeWebsiteTool()
    except Exception as e:
        logger.warning(f"Web browser tool unavailable: {e}")
        return None


def _build_image_generation_tool():
    try:
        from crewai_tools import DallETool
        return DallETool()
    except Exception as e:
        logger.warning(f"DallETool unavailable: {e}")
        return None


def _build_git_clone_tool(workspace_path: Optional[str] = None):
    """Custom tool that clones a repo into the agent's repos/ workspace folder."""
    from crewai.tools import tool

    ws = workspace_path or "/tmp"

    @tool("git_clone")
    def git_clone(repo_url: str, folder_name: str = "") -> str:
        """Clone a git repository into the agent's workspace repos/ directory.
        SSH is the preferred protocol — use SSH URLs whenever possible.
        Args:
            repo_url: The git URL to clone.
                      Prefer SSH:   git@github.com:user/repo.git
                      HTTPS also works: https://github.com/user/repo.git
            folder_name: Optional name for the target folder (defaults to repo name)
        Returns the path of the cloned directory.
        """
        target_dir = Path(ws) / "repos"
        target_dir.mkdir(parents=True, exist_ok=True)
        name = folder_name or repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
        target = target_dir / name
        if target.exists():
            result = subprocess.run(
                ["git", "-C", str(target), "pull", "--ff-only"],
                capture_output=True, text=True, timeout=120,
            )
        else:
            result = subprocess.run(
                ["git", "clone", "--depth=1", repo_url, str(target)],
                capture_output=True, text=True, timeout=300,
            )
        if result.returncode != 0:
            return f"ERROR: {result.stderr}"
        return f"Repository available at: {target}"

    return git_clone


def _build_workspace_shell_tool(workspace_path: Optional[str] = None):
    """Custom tool that runs shell commands inside the agent's workspace."""
    from crewai.tools import tool

    ws = workspace_path or "/tmp"

    @tool("workspace_shell")
    def workspace_shell(command: str, cwd: str = "") -> str:
        """Run a shell command inside the agent's workspace directory.
        Commands are executed in the workspace root (or a sub-path if cwd is specified).
        Args:
            command: Shell command to run (e.g. 'pip install -r requirements.txt')
            cwd: Optional sub-directory within the workspace to run from (e.g. 'repos/my-project')
        Returns stdout and stderr output.
        """
        work_dir = Path(ws) / cwd if cwd else Path(ws)
        work_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            command, shell=True, cwd=str(work_dir),
            capture_output=True, text=True, timeout=120,
        )
        output = ""
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}"
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        output += f"\nExit code: {result.returncode}"
        return output or "(no output)"

    return workspace_shell


_SKILL_NOTE_MAX_CHARS = 6000      # max skill file size before consolidation
_SKILL_NOTE_CONSOLIDATE_AT = 5000  # trigger consolidation above this
_SKILL_NOTE_ENTRY_MAX = 400        # max chars per note entry


def _build_skill_note_tool(workspace_path: Optional[str] = None):
    """Append a concise insight to a skill file without overwriting it.
    Triggers automatic consolidation when the file gets too large."""
    from crewai.tools import tool

    ws = workspace_path or "/tmp"

    @tool("skill_note")
    def skill_note(skill_name: str, insight: str) -> str:
        """Append a new, concise insight to one of your skill files.

        Use this ONLY when you have discovered genuinely NEW information during a task
        that you did not already know (e.g., found via web search, inferred from data).
        Do NOT use this to repeat information already in your skills.
        Keep the insight under 300 characters — one focused fact or decision.

        Args:
            skill_name: Which skill file to update (e.g. 'core_skills', 'project_context',
                        or a topic slug like 'yc_requirements')
            insight:    The new fact/insight to add. Be concise and specific.
        Returns a confirmation or an explanation of why nothing was saved.
        """
        if not insight or len(insight.strip()) < 10:
            return "Insight too short — nothing saved."

        insight = insight.strip()[:_SKILL_NOTE_ENTRY_MAX]

        skills_dir = Path(ws) / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        safe = skill_name.replace(" ", "_").replace("/", "_").lower()
        path = skills_dir / f"{safe}.md"

        existing = path.read_text(encoding="utf-8") if path.exists() else ""

        # Reject if the insight is already present (simple substring check)
        if insight[:60].lower() in existing.lower():
            return f"Insight already present in '{safe}' — nothing added."

        # Append note with timestamp
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d")
        note_block = f"\n\n<!-- note:{timestamp} -->\n- {insight}"
        new_content = existing + note_block

        # If file is getting too large, consolidate before writing
        if len(new_content) > _SKILL_NOTE_CONSOLIDATE_AT:
            consolidated = _consolidate_skill(safe, new_content, ws)
            if consolidated:
                new_content = consolidated

        # Hard cap — never exceed maximum
        if len(new_content) > _SKILL_NOTE_MAX_CHARS:
            return (
                f"Skill '{safe}' is full ({len(new_content)} chars). "
                "Consolidation was attempted but file remains large. "
                "Consider creating a new, focused skill file instead."
            )

        path.write_text(new_content, encoding="utf-8")
        return f"Insight appended to '{safe}' ({len(new_content)} chars total)."

    return skill_note


def _consolidate_skill(skill_name: str, content: str, ws: str) -> Optional[str]:
    """Use Claude to deduplicate and compress a skill file that has grown too large."""
    try:
        from app.config import get_settings
        import anthropic

        settings = get_settings()
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model=settings.claude_model,
            max_tokens=1500,
            messages=[{
                "role": "user",
                "content": (
                    f"The following is a skill document for an AI agent named '{skill_name}'.\n"
                    "It has grown large from accumulated notes. Please consolidate it:\n"
                    "- Remove duplicate or redundant entries\n"
                    "- Merge related facts into single bullet points\n"
                    "- Preserve ALL unique facts and insights\n"
                    "- Keep the result under 4000 characters\n"
                    "- Return only the consolidated Markdown content, no preamble.\n\n"
                    f"---\n{content[:8000]}\n---"
                ),
            }],
        )
        from app.core.usage_tracker import get_usage_tracker
        get_usage_tracker().log(settings.claude_model, resp.usage.input_tokens, resp.usage.output_tokens)
        consolidated = resp.content[0].text.strip()
        logger.info(f"[skill_note] Consolidated '{skill_name}': {len(content)} → {len(consolidated)} chars")
        return consolidated
    except Exception as e:
        logger.warning(f"[skill_note] Consolidation failed for '{skill_name}': {e}")
        return None


def _build_skill_write_tool(workspace_path: Optional[str] = None):
    """Tool for an agent to write/update one of its own skills."""
    from crewai.tools import tool

    ws = workspace_path or "/tmp"

    @tool("skill_write")
    def skill_write(skill_name: str, content: str) -> str:
        """Write or update a skill document in your own skills/ directory.
        Use this to document something you have learned, a methodology, or expertise area.
        Args:
            skill_name: Short slug name for the skill (e.g. 'react_patterns', 'api_design')
            content:    Full Markdown content of the skill document
        Returns a confirmation message.
        """
        skills_dir = Path(ws) / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        safe = skill_name.replace(" ", "_").replace("/", "_").lower()
        path = skills_dir / f"{safe}.md"
        header = (
            f"<!--\n"
            f"  skill: {safe}\n"
            f"  author: self\n"
            f"  updated: {datetime.now(UTC).isoformat()}Z\n"
            f"-->\n\n"
        )
        path.write_text(header + content, encoding="utf-8")
        return f"Skill '{safe}' saved to {path}"

    return skill_write


def _build_skill_read_tool(workspace_path: Optional[str] = None):
    """Tool for an agent to read one of its own skills."""
    from crewai.tools import tool

    ws = workspace_path or "/tmp"

    @tool("skill_read")
    def skill_read(skill_name: str) -> str:
        """Read a skill document from your skills/ directory.
        Args:
            skill_name: Name of the skill to read (e.g. 'core_skills', 'react_patterns')
        Returns the full Markdown content of the skill.
        """
        skills_dir = Path(ws) / "skills"
        safe = skill_name.replace(" ", "_").replace("/", "_").lower()
        path = skills_dir / f"{safe}.md"
        if not path.exists():
            available = [f.stem for f in skills_dir.glob("*.md")]
            return f"Skill '{safe}' not found. Available skills: {available}"
        return path.read_text(encoding="utf-8")

    return skill_read


def _build_skill_list_tool(workspace_path: Optional[str] = None):
    """Tool to list all skills in the agent's skills/ directory."""
    from crewai.tools import tool

    ws = workspace_path or "/tmp"

    @tool("skill_list")
    def skill_list() -> str:
        """List all skill documents in your skills/ directory.
        Returns a formatted list of available skills with metadata.
        """
        skills_dir = Path(ws) / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(skills_dir.glob("*.md"))
        if not files:
            return "No skills documented yet. Use skill_write to create your first skill."
        lines = [f"Your skills ({len(files)} total):\n"]
        for f in files:
            stat = f.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
            lines.append(f"  • {f.stem}  ({stat.st_size} B, updated {mtime})")
        return "\n".join(lines)

    return skill_list


def _build_agent_skill_write_tool(workspace_path: Optional[str] = None):
    """
    Tool for the Associate (Alex) to write skills into ANY sub-agent's skills/ directory.
    This is a privileged tool — only given to the Associate agent.
    """
    from crewai.tools import tool

    @tool("agent_skill_write")
    def agent_skill_write(agent_id: str, skill_name: str, content: str) -> str:
        """Write a skill document into a specific team member's skills/ directory.
        Use this as the Associate to coach or document expertise for a sub-agent.
        Args:
            agent_id:   The ID of the target agent (get it from the team roster)
            skill_name: Short slug name for the skill
            content:    Full Markdown content of the skill document
        Returns a confirmation message.
        """
        from app.core.workspace import get_workspace_manager
        from app.core.agent_factory import get_agent_factory
        factory = get_agent_factory()
        agent = factory.get_agent(agent_id)
        if not agent:
            return f"ERROR: Agent '{agent_id}' not found."
        wm = get_workspace_manager()
        ws = wm.get(agent_id, agent.name, agent.title)
        path = ws.write_skill(skill_name, content, author="associate_alex")
        return f"Skill '{skill_name}' written for agent {agent.name} ({agent_id}) at {path}"

    return agent_skill_write


def _build_agent_skill_read_tool(workspace_path: Optional[str] = None):
    """Tool for the Associate to read a sub-agent's skill."""
    from crewai.tools import tool

    @tool("agent_skill_read")
    def agent_skill_read(agent_id: str, skill_name: str) -> str:
        """Read a skill document from a specific team member's skills/ directory.
        Args:
            agent_id:   The ID of the target agent
            skill_name: Name of the skill to read
        Returns the skill content.
        """
        from app.core.workspace import get_workspace_manager
        from app.core.agent_factory import get_agent_factory
        factory = get_agent_factory()
        agent = factory.get_agent(agent_id)
        if not agent:
            return f"ERROR: Agent '{agent_id}' not found."
        wm = get_workspace_manager()
        ws = wm.get(agent_id, agent.name, agent.title)
        content = ws.read_skill(skill_name)
        if content is None:
            available = [s["name"] for s in ws.list_skills()]
            return f"Skill not found for agent {agent.name}. Available: {available}"
        return content

    return agent_skill_read


def _build_workspace_list_tool(workspace_path: Optional[str] = None):
    """Custom tool to list the contents of the agent's workspace."""
    from crewai.tools import tool

    ws = workspace_path or "/tmp"

    @tool("workspace_list")
    def workspace_list(sub_path: str = ".") -> str:
        """List the contents of the agent's workspace directory.
        Args:
            sub_path: Sub-directory to list (default: workspace root)
        Returns a text listing of files and folders.
        """
        target = (Path(ws) / sub_path).resolve()
        ws_resolved = Path(ws).resolve()
        if target != ws_resolved and not str(target).startswith(str(ws_resolved) + os.sep):
            return "ERROR: Path outside workspace"
        if not target.exists():
            return f"Path does not exist: {sub_path}"
        lines = [f"Contents of {sub_path}:\n"]
        for item in sorted(target.iterdir()):
            kind = "DIR " if item.is_dir() else "FILE"
            size = f"{item.stat().st_size:>10} B" if item.is_file() else " " * 12
            mtime = datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            lines.append(f"  {kind}  {size}  {mtime}  {item.name}")
        return "\n".join(lines)

    return workspace_list


# Tool builders that do NOT depend on workspace (shared/cached globally)
GLOBAL_TOOL_BUILDERS = {
    "web_search": _build_web_search_tool,
    "web_browser": _build_web_browser_tool,
    "image_generation": _build_image_generation_tool,
    "github": _build_github_tool,
    "code_execution": _build_code_execution_tool,
}

# Tool builders that ARE workspace-scoped (built per-agent, not cached globally)
WORKSPACE_TOOL_BUILDERS = {
    "file_read": _build_file_read_tool,
    "file_write": _build_file_write_tool,
    "git_clone": _build_git_clone_tool,
    "workspace_shell": _build_workspace_shell_tool,
    "workspace_list": _build_workspace_list_tool,
    # Skill tools — self
    "skill_note": _build_skill_note_tool,   # append-only, safe for self-augmentation
    "skill_write": _build_skill_write_tool,
    "skill_read": _build_skill_read_tool,
    "skill_list": _build_skill_list_tool,
    # Skill tools — cross-agent (Associate only)
    "agent_skill_write": _build_agent_skill_write_tool,
    "agent_skill_read": _build_agent_skill_read_tool,
}

_global_tool_cache: dict = {}


def get_tools_for_agent(tool_names: list[str], workspace_path: Optional[str] = None) -> list:
    """
    Build tool list for a specific agent.
    Global tools are cached; workspace-scoped tools are built fresh per agent.
    """
    tools = []

    for name in tool_names:
        tool_obj = None

        if name in WORKSPACE_TOOL_BUILDERS:
            # Always build fresh with the agent's workspace path
            try:
                tool_obj = WORKSPACE_TOOL_BUILDERS[name](workspace_path)
            except Exception as e:
                logger.error(f"Failed to build workspace tool '{name}': {e}")

        elif name in GLOBAL_TOOL_BUILDERS:
            if name not in _global_tool_cache:
                try:
                    _global_tool_cache[name] = GLOBAL_TOOL_BUILDERS[name]()
                except Exception as e:
                    logger.error(f"Failed to build global tool '{name}': {e}")
                    _global_tool_cache[name] = None
            tool_obj = _global_tool_cache.get(name)

        else:
            logger.warning(f"Unknown tool: '{name}'")

        if tool_obj is not None:
            tools.append(tool_obj)

    return tools
