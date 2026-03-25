"""
Smart Brief Engine — evaluates whether a brief is clear enough for the AI workforce.

Returns an array of highlight objects the frontend can use for inline annotations.
Uses the fastest model tier (haiku) for sub-2-second response times.
"""

import json
import logging

from anthropic import AsyncAnthropic

from app.config import get_settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a brief quality analyst for an autonomous AI workforce. \
Your job is to find vague, ambiguous, or incomplete parts of a user's brief \
so they can fix the brief BEFORE we spend tokens on execution.

You will receive a title and description. Inspect them for:
- Vague scope ("do a competitive analysis" — which competitors? what dimensions?)
- Missing constraints (target audience, market, format, length, deadline)
- Unclear success criteria (how will the user judge the output?)
- Ambiguous references ("the app", "our product" without specifics)

Respond ONLY with a JSON object (no other text) matching this schema:

{
  "sufficient": true | false,
  "highlights": [
    {
      "highlight_quote": "exact substring from the user's input that is vague",
      "issue": "short explanation of why it is vague",
      "suggestion": "concrete suggestion to fix it"
    }
  ]
}

Rules:
- "highlight_quote" MUST be an exact substring of the title or description — the frontend will use string matching to underline it.
- Return at most 5 highlights. Fewer is better — only flag genuine problems.
- If the brief is clear and actionable, set "sufficient" to true and return an empty "highlights" array.
- Do NOT invent issues for already-specific briefs. Err on the side of approval."""


async def analyze_sufficiency(title: str, description: str) -> dict:
    """
    Ask Claude (haiku) to evaluate a brief for clarity and completeness.

    Returns:
        {
            "sufficient": bool,
            "highlights": [
                {
                    "highlight_quote": str,
                    "issue": str,
                    "suggestion": str,
                }
            ]
        }
    """
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    user_text = f"Title: {title}\n\nDescription: {description}"

    try:
        response = await client.messages.create(
            model=settings.claude_model_haiku,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_text}],
        )
        raw = response.content[0].text.strip()
        result = json.loads(raw)
        return {
            "sufficient": bool(result.get("sufficient", True)),
            "highlights": [
                {
                    "highlight_quote": str(h.get("highlight_quote", "")),
                    "issue": str(h.get("issue", "")),
                    "suggestion": str(h.get("suggestion", "")),
                }
                for h in result.get("highlights", [])
            ],
        }
    except Exception as exc:
        logger.warning("Sufficiency analysis failed, defaulting to sufficient: %s", exc)
        return {"sufficient": True, "highlights": []}
