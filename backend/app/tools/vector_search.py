"""vector_search tool — semantic search on uploaded project documents via pgvector.

Ref: TDD-03 Section 6.3 (vector_search definition),
     TDD-02 Section 2.2 (embedding model: voyage-3-lite, 1024 dims),
     TDD-02 Section 2.4 (retrieval query with cosine distance).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import text

from app.config.settings import settings
from app.tools.registry import ExecutionContext, ToolDef

logger = logging.getLogger(__name__)

_VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
_EMBEDDING_MODEL = "voyage-3-lite"
_TIMEOUT = 10.0


async def embed_query(query_text: str) -> list[float]:
    """Embed a query string using the Voyage API.

    Returns a 1024-dimensional embedding vector.
    Raises ValueError if the API key is missing.
    """
    api_key = settings.VOYAGE_API_KEY
    if not api_key:
        raise ValueError("VOYAGE_API_KEY is not configured — vector search unavailable")

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(
            _VOYAGE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": _EMBEDDING_MODEL,
                "input": [query_text],
                "input_type": "query",
            },
        )
        response.raise_for_status()
        data = response.json()

    return data["data"][0]["embedding"]


async def execute(tool_input: dict[str, Any], context: ExecutionContext) -> str:
    """Search uploaded documents using pgvector cosine similarity.

    Searches project-level documents (scoped by project_id) and workspace-level
    documents (scoped by workspace_id) in a single query. During the learning
    phase only workspace_id is set; during execution both are available.

    Ref: TDD-02 Section 2.4 — retrieval query.
    """
    query: str = tool_input.get("query", "")
    if not query:
        return "Error: 'query' is required."

    top_k: int = min(tool_input.get("top_k", 5), 15)

    if context.db_session is None:
        return "Error: database session not available for vector search."

    if not context.project_id and not context.workspace_id:
        return "Error: project_id or workspace_id is required for vector search."

    # Step 1: Embed the query
    try:
        embedding = await embed_query(query)
    except ValueError as exc:
        return f"Error: {exc}"
    except httpx.HTTPStatusError as exc:
        return f"Error: embedding API returned HTTP {exc.response.status_code}."
    except httpx.HTTPError as exc:
        return f"Error: embedding request failed: {exc}"

    # Step 2: Build WHERE clause — include project docs and/or workspace docs
    conditions: list[str] = []
    params: dict[str, Any] = {
        "query_embedding": str(embedding),
        "top_k": top_k,
    }
    if context.project_id:
        conditions.append("d.project_id = :project_id")
        params["project_id"] = context.project_id
    if context.workspace_id:
        conditions.append("d.workspace_id = :workspace_id")
        params["workspace_id"] = context.workspace_id

    where_clause = " OR ".join(conditions)

    # Step 3: Run pgvector cosine similarity query (TDD-02 Section 2.4)
    sql = text(f"""
        SELECT dc.content, dc.chunk_index, d.filename
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        WHERE ({where_clause})
          AND d.processing_status = 'ready'
        ORDER BY dc.embedding <=> CAST(:query_embedding AS vector)
        LIMIT :top_k
    """)

    try:
        result = await context.db_session.execute(sql, params)
        rows = result.fetchall()
    except Exception as exc:
        logger.exception("Vector search query failed")
        return f"Error: vector search query failed: {exc}"

    if not rows:
        return "No relevant documents found."

    # Step 3: Format results
    parts: list[str] = []
    for i, row in enumerate(rows, 1):
        content, chunk_index, filename = row
        parts.append(
            f"--- Result {i} (from '{filename}', chunk {chunk_index}) ---\n{content}"
        )

    return "\n\n".join(parts)


VECTOR_SEARCH_TOOL = ToolDef(
    name="vector_search",
    description="Search uploaded project documents using semantic similarity. Returns the most relevant text chunks.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language search query",
            },
            "top_k": {
                "type": "integer",
                "default": 5,
                "maximum": 15,
            },
        },
        "required": ["query"],
    },
    executor=execute,
)
