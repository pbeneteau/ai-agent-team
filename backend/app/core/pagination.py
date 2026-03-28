"""Cursor-based pagination utilities (TDD-04 Section 1.3).

Cursor encoding
    The cursor is a base64-encoded JSON object holding the sort keys of the
    last item on the current page (e.g. ``{"id": "...", "created_at": "..."}``).
    Clients treat it as opaque.

LIMIT+1 pattern
    Fetch ``limit + 1`` rows.  If we get back ``limit + 1`` rows, there is
    another page (``has_more = True``) and we return only the first ``limit``
    rows.
"""

import base64
import json
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import Column, Select, desc, tuple_

T = TypeVar("T")

DEFAULT_LIMIT: int = 20
MAX_LIMIT: int = 100


# ---------------------------------------------------------------------------
# Cursor encode / decode
# ---------------------------------------------------------------------------


def encode_cursor(values: dict[str, Any]) -> str:
    """Encode sort-key values into an opaque cursor string.

    Datetime values are serialised to ISO-8601 so the JSON round-trips cleanly.
    """
    serialisable: dict[str, Any] = {}
    for key, val in values.items():
        if isinstance(val, datetime):
            serialisable[key] = val.isoformat()
        else:
            serialisable[key] = val
    payload = json.dumps(serialisable, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor_str: str | None) -> dict[str, Any] | None:
    """Decode an opaque cursor string back to sort-key values.

    Returns ``None`` when given ``None`` or an empty string.
    """
    if not cursor_str:
        return None
    payload = base64.urlsafe_b64decode(cursor_str.encode()).decode()
    return json.loads(payload)


# ---------------------------------------------------------------------------
# Query helper
# ---------------------------------------------------------------------------


def apply_cursor_pagination(
    query: Select,
    *,
    cursor: str | None,
    limit: int = DEFAULT_LIMIT,
    sort_columns: list[Column],
) -> Select:
    """Apply cursor-based WHERE, ORDER BY, and LIMIT+1 to a SELECT statement.

    Parameters
    ----------
    query:
        An existing ``select(...)`` that already contains any WHERE filters
        the caller needs (e.g. ``workspace_id = ...``).
    cursor:
        Opaque cursor from the client (or ``None`` for the first page).
    limit:
        Requested page size.  Clamped to [1, MAX_LIMIT].
    sort_columns:
        SQLAlchemy column objects to sort by (descending).  The cursor must
        contain keys matching each column's ``.key`` attribute.

    Returns the query with ORDER BY … DESC, WHERE (if cursor), LIMIT limit+1.
    """
    limit = max(1, min(limit, MAX_LIMIT))

    # Always order descending by the sort columns
    query = query.order_by(*(desc(col) for col in sort_columns))

    # Apply cursor WHERE clause if present
    decoded = decode_cursor(cursor)
    if decoded is not None:
        cursor_values = tuple(decoded[col.key] for col in sort_columns)
        query = query.where(
            tuple_(*(col for col in sort_columns)) < cursor_values
        )

    # Fetch one extra to determine has_more
    query = query.limit(limit + 1)
    return query


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard pagination envelope returned by all list endpoints."""

    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False


def paginate(
    rows: list[Any],
    *,
    limit: int,
    sort_keys: list[str],
) -> PaginatedResponse:
    """Build a ``PaginatedResponse`` from the raw rows returned by the query.

    Parameters
    ----------
    rows:
        The full result set (up to ``limit + 1`` items).
    limit:
        The page size the caller requested (before the +1).
    sort_keys:
        Attribute names on each row object used to build the cursor
        (must match the ``sort_columns`` passed to ``apply_cursor_pagination``).
    """
    limit = max(1, min(limit, MAX_LIMIT))
    has_more = len(rows) > limit
    items = rows[:limit]

    next_cursor: str | None = None
    if has_more and items:
        last = items[-1]
        cursor_values = {key: getattr(last, key) for key in sort_keys}
        next_cursor = encode_cursor(cursor_values)

    return PaginatedResponse(items=items, next_cursor=next_cursor, has_more=has_more)
