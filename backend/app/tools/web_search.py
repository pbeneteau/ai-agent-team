"""web_search tool — search the web via Serper API.

Ref: TDD-03 Section 6.3 (web_search tool definition).
Gracefully degrades if SERPER_API_KEY is not configured.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config.settings import settings
from app.tools.registry import ExecutionContext, ToolDef

logger = logging.getLogger(__name__)

_SERPER_URL = "https://google.serper.dev/search"
_TIMEOUT = 10.0


async def execute(tool_input: dict[str, Any], context: ExecutionContext) -> str:
    """Execute a web search via Serper API."""
    query: str = tool_input.get("query", "")
    if not query:
        return "Error: 'query' is required."

    num_results: int = min(tool_input.get("num_results", 5), 10)

    if not settings.SERPER_API_KEY:
        return "Error: web search is unavailable — SERPER_API_KEY is not configured."

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                _SERPER_URL,
                headers={
                    "X-API-KEY": settings.SERPER_API_KEY,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": num_results},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        return f"Error: web search timed out for query '{query}'."
    except httpx.HTTPStatusError as exc:
        return f"Error: web search failed with HTTP {exc.response.status_code}."
    except httpx.HTTPError as exc:
        return f"Error: web search request failed: {exc}"

    return _format_results(data)


def _format_results(data: dict[str, Any]) -> str:
    """Format Serper API response into clean text for the agent."""
    parts: list[str] = []

    # Answer box (if present)
    answer_box = data.get("answerBox")
    if answer_box:
        answer = answer_box.get("answer") or answer_box.get("snippet", "")
        if answer:
            parts.append(f"Answer: {answer}\n")

    # Organic results
    for i, result in enumerate(data.get("organic", []), 1):
        title = result.get("title", "")
        url = result.get("link", "")
        snippet = result.get("snippet", "")
        parts.append(f"{i}. {title}\n   URL: {url}\n   {snippet}")

    if not parts:
        return "No results found."

    return "\n\n".join(parts)


WEB_SEARCH_TOOL = ToolDef(
    name="web_search",
    description="Search the web for information. Returns a list of results with titles, URLs, and snippets.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
            "num_results": {
                "type": "integer",
                "default": 5,
                "maximum": 10,
            },
        },
        "required": ["query"],
    },
    executor=execute,
)
