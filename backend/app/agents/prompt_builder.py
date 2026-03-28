"""Prompt assembly — builds the system prompt and user message for every agent call.

Ref: TDD-03 Section 4 (9-position prompt architecture),
     TDD-03 Section 4.4 (output format rules by artifact type and slot role),
     TDD-03 Section 4.5 (iteration prompts),
     TDD-03 Section 7.2 (auto-assume rule — verbatim text).

The 9-position structure leverages LLM recency bias: the current task is
always at position 9 (last in the user message) so it receives the highest
attention weight from the model.

SYSTEM MESSAGE
  1. Role & Identity
  2. Auto-Assume Rule
  3. Output Format Rules

USER MESSAGE
  4. Agent Skills            (oldest — long-term memory)
  5. Agent Work Learnings    (long-term memory)
  6. Upstream Agent Outputs   (DAG execution context)
  7. Project Brief            (current task context)
  8. Artifact Brief           (current task context)
  9. Wave Task Instructions   (recency anchor — always last)
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Position 2: Auto-Assume Rule (TDD-03 Section 7.2 — verbatim)
# ---------------------------------------------------------------------------

AUTO_ASSUME_RULE: str = """\
═══════════════════════════════════════════════════════════════
CRITICAL OPERATING RULE — AUTO-ASSUME

If you encounter missing information, ambiguity, or a situation where you would
normally ask for clarification:
1. Make the safest, most reasonable assumption.
2. Document it CLEARLY inline in your output:
   [ASSUMPTION: <what you assumed and why>]
3. Continue working. Finish the deliverable.

You are fully autonomous. You will NEVER receive a follow-up message.
There is no human in the loop during execution. The user will review your
output after you are done and can override any assumption at that point.

DO NOT:
- Output questions to the user
- Say "I would need to know..." or "Please clarify..."
- Leave sections blank or with placeholders like "TBD" (unless you genuinely
  cannot even assume — in which case, mark as [TBD: <what's needed>])
- Stop mid-work because of uncertainty

ALWAYS prefer completing the work with assumptions over leaving gaps.
═══════════════════════════════════════════════════════════════"""


# ---------------------------------------------------------------------------
# Position 3: Output Format Rules (TDD-03 Section 4.4)
# ---------------------------------------------------------------------------

_PROSE_FORMAT_RULES: str = """\
OUTPUT RULES:
- Output the deliverable directly. No preamble ("Here is the..."), no
  meta-commentary ("I'll now write..."), no sign-offs.
- Use Markdown formatting.
- If you make an assumption, mark it inline: [ASSUMPTION: <what and why>]
- If you used a source, cite it inline: [Source: <URL or reference>]"""

_CODE_FORMAT_RULES: str = """\
OUTPUT RULES:
- Output complete, working code files.
- Use the following format for each file:

--- FILE: {relative/path/to/file.ext} ---
{file content}
--- END FILE ---

- Do not output partial files or pseudocode.
- If you make an assumption, add a code comment: // [ASSUMPTION: <what and why>]
- Follow the project's tech stack and conventions from the brief context."""

_ANALYSIS_FORMAT_RULES: str = """\
OUTPUT RULES:
- Output structured Markdown.
- Use headers, bullet points, and tables for clarity.
- Your output will be consumed by downstream agents — be precise and specific.
  Avoid vague language. Provide exact values (hex codes, pixel values, API
  endpoints) rather than descriptions.
- If you make an assumption, mark it: [ASSUMPTION: <what and why>]
- If you used a source, cite it: [Source: <URL or reference>]"""

_QA_FORMAT_RULES: str = """\
OUTPUT RULES:
- If your role is review/QA, output a structured review report AND the
  corrected deliverable.
- Use this format:

## Review Report
| Criterion | Status | Notes |
|---|---|---|
| ... | PASS/FAIL | ... |

## Issues Found
1. [Issue description + location + suggested fix]

## Corrected Output
{the fixed/improved deliverable}"""


# Mapping: slot_role → format rules (primary routing)
_ROLE_FORMAT_MAP: dict[str, str] = {
    # Prose roles
    "writer": _PROSE_FORMAT_RULES,
    "editor": _PROSE_FORMAT_RULES,
    "compiler": _PROSE_FORMAT_RULES,
    # Code roles
    "implementation": _CODE_FORMAT_RULES,
    "developer": _CODE_FORMAT_RULES,
    "fixer": _CODE_FORMAT_RULES,
    # Analysis / spec roles
    "product_spec": _ANALYSIS_FORMAT_RULES,
    "design_spec": _ANALYSIS_FORMAT_RULES,
    "analyst": _ANALYSIS_FORMAT_RULES,
    "researcher": _ANALYSIS_FORMAT_RULES,
    # QA / review roles
    "qa_review": _QA_FORMAT_RULES,
    "validator": _QA_FORMAT_RULES,
}

# Fallback: artifact_type → format rules
_TYPE_FORMAT_MAP: dict[str, str] = {
    "prose": _PROSE_FORMAT_RULES,
    "code": _CODE_FORMAT_RULES,
}


def get_output_format_rules(artifact_type: str, slot_role: str) -> str:
    """Return output format instructions for the given artifact type and slot role.

    Ref: TDD-03 Section 4.4.

    Routes primarily on ``slot_role`` (most specific), falls back to
    ``artifact_type``, and defaults to analysis format rules.
    """
    rules = _ROLE_FORMAT_MAP.get(slot_role)
    if rules:
        return rules

    rules = _TYPE_FORMAT_MAP.get(artifact_type)
    if rules:
        return rules

    return _ANALYSIS_FORMAT_RULES


# ---------------------------------------------------------------------------
# Position 9 replacement for iterations (TDD-03 Section 4.5)
# ---------------------------------------------------------------------------

_ITERATION_TASK: str = """\
## Your Task
Address the user's feedback on the previous version. Modify ONLY the section
the user highlighted. Preserve everything else unchanged. Output the complete
updated deliverable (not just the changed section).

If the feedback contradicts a previous assumption you made, remove the assumption
tag and apply the user's correction."""


# ---------------------------------------------------------------------------
# System prompt builder (positions 1-3)
# ---------------------------------------------------------------------------


def build_system_prompt(
    agent: Any,
    output_format_rules: str,
) -> str:
    """Assemble the system prompt from positions 1-3.

    Position 1: Role & identity — ``agent.name``, ``agent.specialization``,
                and ``agent.system_prompt`` (if present).
    Position 2: Auto-assume rule (TDD-03 Section 7.2).
    Position 3: Output format rules (TDD-03 Section 4.4).

    Args:
        agent: Agent model instance (needs ``.name``, ``.specialization``,
               ``.system_prompt`` attributes).
        output_format_rules: Format rules string from ``get_output_format_rules()``.

    Returns:
        Complete system prompt string.
    """
    sections: list[str] = []

    # Position 1: Role & Identity
    role = f"You are {agent.name}, a {agent.specialization}."
    system_prompt = getattr(agent, "system_prompt", None)
    if system_prompt:
        role += f"\n\n{system_prompt}"
    sections.append(role)

    # Position 2: Auto-Assume Rule
    sections.append(AUTO_ASSUME_RULE)

    # Position 3: Output Format Rules
    sections.append(output_format_rules)

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# User message builder (positions 4-9)
# ---------------------------------------------------------------------------


def build_user_message(
    agent_memory: str | None,
    upstream_context: str | None,
    project_brief: str | None,
    artifact_brief: dict[str, str | None] | None,
    wave_task: str | None,
) -> str:
    """Assemble the user message from positions 4-9 in recency bias order.

    Position 4-5: Agent skills + work learnings (``agent_memory``, pre-formatted).
    Position 6:   Upstream agent outputs (``upstream_context``, pre-formatted).
    Position 7:   Project brief (``project.brief_published``).
    Position 8:   Artifact brief (title, goal, audience, context, description).
    Position 9:   Wave-specific task instructions (recency anchor — always last).

    Empty or ``None`` sections are silently omitted. No empty headers appear.

    Args:
        agent_memory: Pre-formatted markdown string of agent skills and
                      work learnings. Built by ``memory.load_agent_memory()``.
        upstream_context: Pre-formatted markdown string of outputs from
                         upstream agents in the DAG.
        project_brief: The published project brief text (``project.brief_published``).
        artifact_brief: Dict with keys ``title``, ``goal``, ``target_audience``,
                       ``context``, ``description``. Missing/None fields omitted.
        wave_task: The slot-specific role prompt from the DAG template.

    Returns:
        Complete user message string.
    """
    sections: list[str] = []

    # Position 4-5: Agent memory (skills + work learnings)
    if agent_memory:
        sections.append(f"## Your Knowledge & Experience\n\n{agent_memory}")

    # Position 6: Upstream context
    if upstream_context:
        sections.append(upstream_context)

    # Position 7: Project brief
    if project_brief:
        sections.append(f"## Project Context\n\n{project_brief}")

    # Position 8: Artifact brief
    if artifact_brief:
        brief_text = _format_artifact_brief(artifact_brief)
        if brief_text:
            sections.append(brief_text)

    # Position 9: Wave task (recency anchor — always last)
    if wave_task:
        sections.append(f"## Your Task in This Wave\n\n{wave_task}")

    return "\n\n".join(sections)


def _format_artifact_brief(brief: dict[str, str | None]) -> str:
    """Format artifact brief fields into a markdown section.

    Follows TDD-03 Section 4.2 format exactly:
        ## Your Assignment
        Title: {title}
        Goal: {goal}
        Target Audience: {audience}
        Context: {context}
        Description: {description}

    Fields that are ``None`` or empty are omitted.
    Returns empty string if no fields have values.
    """
    lines: list[str] = []

    field_map: list[tuple[str, str | None]] = [
        ("Title", brief.get("title")),
        ("Goal", brief.get("goal")),
        ("Target Audience", brief.get("target_audience")),
        ("Context", brief.get("context")),
        ("Description", brief.get("description")),
    ]

    for label, value in field_map:
        if value:
            lines.append(f"{label}: {value}")

    if not lines:
        return ""

    return "## Your Assignment\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Iteration prompt builder (TDD-03 Section 4.5)
# ---------------------------------------------------------------------------


def build_iteration_prompt(
    previous_version_content: str,
    comment: Any,
    artifact_brief: dict[str, str | None] | None,
    *,
    agent_memory: str | None = None,
    project_brief: str | None = None,
    version_number: int | None = None,
) -> str:
    """Assemble the user message for a contextual iteration.

    Ref: TDD-03 Section 4.5.

    The structure mirrors ``build_user_message`` but replaces:
    - Position 6 (upstream context) → previous version content + user feedback
    - Position 9 (wave task) → fixed iteration task instruction

    Positions 4-5, 7, and 8 remain the same.

    Args:
        previous_version_content: Full text of the previous artifact version.
        comment: Object with ``.file_path``, ``.highlighted_text``, and
                 ``.instruction`` attributes (e.g. ``ContextualComment`` model
                 or any duck-typed equivalent).
        artifact_brief: Same as ``build_user_message``.
        agent_memory: Optional pre-formatted agent memory string.
        project_brief: Optional published project brief text.
        version_number: Optional version number for labeling.

    Returns:
        Complete user message string for the iteration.
    """
    sections: list[str] = []

    # Position 4-5: Agent memory (optional for iterations)
    if agent_memory:
        sections.append(f"## Your Knowledge & Experience\n\n{agent_memory}")

    # Position 6 (replaced): Previous version + user feedback
    version_label = f" (v{version_number})" if version_number else ""
    sections.append(
        f"## Previous Version{version_label}\n\n{previous_version_content}"
    )

    file_ref = getattr(comment, "file_path", None) or "entire document"
    highlighted = getattr(comment, "highlighted_text", None) or ""
    instruction = getattr(comment, "instruction", "")

    feedback_lines: list[str] = [
        "## User Feedback",
        f"File: {file_ref}",
    ]
    if highlighted:
        feedback_lines.append(f'Highlighted text: "{highlighted}"')
    feedback_lines.append(f"Instruction: {instruction}")
    sections.append("\n".join(feedback_lines))

    # Position 7: Project brief
    if project_brief:
        sections.append(f"## Project Context\n\n{project_brief}")

    # Position 8: Artifact brief
    if artifact_brief:
        brief_text = _format_artifact_brief(artifact_brief)
        if brief_text:
            sections.append(brief_text)

    # Position 9 (replaced): Iteration task instruction
    sections.append(_ITERATION_TASK)

    return "\n\n".join(sections)
