"""Sufficiency check engine — Sonnet-powered brief quality validator.

Ref: TDD-03 Section 1 (sufficiency check engine).
     TDD-03 Section 1.3 (system prompt).
     TDD-03 Section 1.4 (user message template).
     TDD-03 Section 1.5 (response schema).
     TDD-03 Section 1.6 (fail-open policy).

Runs when the user clicks "Validate" or "Delegate" — never on keystroke.
Uses Claude Sonnet for quality over speed (target latency < 4s).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from app.config.settings import settings
from app.models.artifact import Artifact
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt (TDD-03 Section 1.3 — verbatim)
# ---------------------------------------------------------------------------

SUFFICIENCY_SYSTEM_PROMPT: str = """\
You are a Brief Quality Analyst. Your job is to evaluate whether a project brief \
is clear and complete enough for a team of AI agents to execute WITHOUT asking \
any follow-up questions.

You must identify:
1. MISSING CONSTRAINTS — critical information the brief does not provide \
(audience, market, timeline, tech stack, success criteria, scope boundaries)
2. AMBIGUOUS LANGUAGE — words like "some", "various", "good", "comprehensive", \
"appropriate", "etc." that leave execution open to interpretation
3. SCOPE CREEP INDICATORS — briefs that try to do too many things at once \
or mix unrelated deliverables
4. MISSING SUCCESS CRITERIA — no way to evaluate whether the output is correct

Rules:
- Be strict but fair. A brief does not need to be a novel — it needs to be \
unambiguous.
- Only flag issues that would genuinely cause an AI agent to produce the wrong \
output or guess incorrectly.
- Do NOT flag stylistic preferences or minor omissions that agents can safely \
assume.
- For each issue, quote the EXACT substring from the user's text that is \
problematic (this is used for inline highlighting in the UI).
- Provide an actionable suggestion for each issue — tell the user exactly what \
to add or change.
- Maximum 5 issues. Prioritize the most critical ones.
- Classify each issue as "critical" (blocks execution) or "warning" (advisory).

Respond with valid JSON only. No markdown fences, no explanation outside the JSON."""

# ---------------------------------------------------------------------------
# Pydantic models (TDD-03 Section 1.5)
# ---------------------------------------------------------------------------


class SufficiencyIssue(BaseModel):
    """A single issue found in the brief."""

    severity: str  # "critical" or "warning"
    field: str  # Which brief field: title, goal, target_audience, context, description
    matched_text: str  # Exact substring from user's input for inline highlighting
    issue: str  # What's wrong
    suggestion: str  # Actionable fix


class SufficiencyResult(BaseModel):
    """Result of a sufficiency check."""

    eligible: bool  # True if no critical issues. Warning issues do not block.
    score: int  # 0-100 quality score (informational — not used for blocking)
    issues: list[SufficiencyIssue]


# ---------------------------------------------------------------------------
# User message builder (TDD-03 Section 1.4)
# ---------------------------------------------------------------------------


def build_sufficiency_user_msg(artifact: Artifact, workspace: Workspace) -> str:
    """Build the user message for the sufficiency check.

    Always includes the core brief fields. Appends tech stack context
    for code artifacts (TDD-03 Section 1.4).
    """
    msg = (
        f"Evaluate this brief:\n\n"
        f"Title: {artifact.title}\n"
        f"Goal: {artifact.goal or '(not specified)'}\n"
        f"Target Audience: {artifact.target_audience or '(not specified)'}\n"
        f"Context: {artifact.context or '(not specified)'}\n"
        f"Description: {artifact.description or '(not specified)'}\n\n"
        f"Artifact Type: {artifact.artifact_type}  (prose or code)"
    )

    if artifact.artifact_type == "code":
        msg += (
            f"\nTech Stack Context: {workspace.tech_stack or '(not specified)'}\n"
            f"Target Repository: {artifact.git_repo_url or 'Not specified'}"
        )

    return msg


# ---------------------------------------------------------------------------
# Core entry point (TDD-03 Section 1.6)
# ---------------------------------------------------------------------------


async def run_sufficiency_check(
    artifact: Artifact,
    workspace: Workspace,
) -> SufficiencyResult:
    """Run the Sonnet-powered sufficiency check on a brief.

    Returns a SufficiencyResult with eligibility, score, and issues.

    Fail-open policy: If the LLM returns malformed JSON or the call fails
    entirely, we return eligible=True with a warning. The sufficiency check
    is a quality gate, not a security gate.
    """
    from app.agents.anthropic_runner import get_anthropic_client

    client = get_anthropic_client()
    user_msg = build_sufficiency_user_msg(artifact, workspace)

    try:
        response = await client.messages.create(
            model=settings.MODEL_SONNET,
            max_tokens=1024,
            system=SUFFICIENCY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )

        raw_text = response.content[0].text
        result_data: dict[str, Any] = json.loads(raw_text)
        return SufficiencyResult(**result_data)

    except (json.JSONDecodeError, ValidationError) as exc:
        # Fail-open: malformed JSON → return eligible with warning
        logger.warning(
            "Sufficiency check returned malformed response, failing open: %s",
            exc,
        )
        return _fail_open_result()

    except Exception as exc:
        # Fail-open: any other error (timeout, network, etc.)
        logger.error(
            "Sufficiency check failed, failing open: %s",
            exc,
        )
        return _fail_open_result()


def _fail_open_result() -> SufficiencyResult:
    """Return a fail-open result when the sufficiency check cannot complete."""
    return SufficiencyResult(
        eligible=True,
        score=50,
        issues=[
            SufficiencyIssue(
                severity="warning",
                field="description",
                matched_text="",
                issue="Brief validation returned an unexpected result. Proceeding with caution.",
                suggestion="Consider reviewing your brief for clarity before delegating.",
            )
        ],
    )
