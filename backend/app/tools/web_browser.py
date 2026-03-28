"""web_browser tool — fetch and extract text from a web page.

Ref: TDD-03 Section 6.3 (web_browser tool definition).
Truncates output to 8,000 characters per TDD spec.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.tools.registry import ExecutionContext, ToolDef

logger = logging.getLogger(__name__)

_MAX_CHARS = 8_000
_TIMEOUT = 15.0
_USER_AGENT = "AgentTeam/1.0 (web_browser tool)"


async def execute(tool_input: dict[str, Any], context: ExecutionContext) -> str:
    """Fetch a web page and extract its text content."""
    url: str = tool_input.get("url", "")
    if not url:
        return "Error: 'url' is required."

    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.TimeoutException:
        return f"Error: request timed out fetching '{url}'."
    except httpx.HTTPStatusError as exc:
        return f"Error: received HTTP {exc.response.status_code} from '{url}'."
    except httpx.HTTPError as exc:
        return f"Error: failed to fetch '{url}': {exc}"

    return extract_text(response.text)


def extract_text(html: str) -> str:
    """Extract readable text from HTML, truncated to 8,000 characters.

    Strips non-content elements (script, style, nav, footer, etc.) and
    collapses excessive whitespace.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove non-content elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)

    # Collapse multiple blank lines
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)

    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + "\n\n[Content truncated at 8,000 characters]"

    return text


WEB_BROWSER_TOOL = ToolDef(
    name="web_browser",
    description="Fetch and read the content of a web page. Returns extracted text content (max 8000 characters).",
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to fetch"},
        },
        "required": ["url"],
    },
    executor=execute,
)
