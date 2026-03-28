"""Tests for Ticket 2.4 — Shared backend utilities."""

import json
from datetime import datetime, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.errors import (
    ApiError,
    api_error_handler,
    budget_exceeded,
    conflict,
    internal_error,
    not_found,
    payload_too_large,
    unprocessable_entity,
    validation_error,
)
from app.core.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    PaginatedResponse,
    decode_cursor,
    encode_cursor,
    paginate,
)
from app.core.workspace_id import get_workspace_id


# ---------------------------------------------------------------------------
# Cursor encode / decode
# ---------------------------------------------------------------------------


class TestCursorRoundtrip:
    def test_simple_values(self) -> None:
        original = {"id": "abc-123", "created_at": "2026-03-26T10:00:00+00:00"}
        cursor = encode_cursor(original)
        assert isinstance(cursor, str)
        decoded = decode_cursor(cursor)
        assert decoded == original

    def test_datetime_serialisation(self) -> None:
        dt = datetime(2026, 3, 26, 10, 0, 0, tzinfo=timezone.utc)
        cursor = encode_cursor({"id": "x", "created_at": dt})
        decoded = decode_cursor(cursor)
        assert decoded is not None
        assert decoded["created_at"] == dt.isoformat()
        assert decoded["id"] == "x"

    def test_decode_none(self) -> None:
        assert decode_cursor(None) is None

    def test_decode_empty_string(self) -> None:
        assert decode_cursor("") is None

    def test_multiple_keys(self) -> None:
        original = {"a": 1, "b": "two", "c": 3.0}
        assert decode_cursor(encode_cursor(original)) == original


# ---------------------------------------------------------------------------
# Paginate helper
# ---------------------------------------------------------------------------


class _FakeRow:
    """Minimal object with attributes for pagination tests."""

    def __init__(self, id: str, created_at: str) -> None:
        self.id = id
        self.created_at = created_at


class TestPaginate:
    def test_no_rows(self) -> None:
        result = paginate([], limit=20, sort_keys=["created_at", "id"])
        assert result.items == []
        assert result.next_cursor is None
        assert result.has_more is False

    def test_fewer_than_limit(self) -> None:
        rows = [_FakeRow(id="1", created_at="2026-01-01")]
        result = paginate(rows, limit=20, sort_keys=["created_at", "id"])
        assert len(result.items) == 1
        assert result.has_more is False
        assert result.next_cursor is None

    def test_exactly_limit(self) -> None:
        rows = [_FakeRow(id=str(i), created_at=f"2026-01-{i:02d}") for i in range(1, 21)]
        result = paginate(rows, limit=20, sort_keys=["created_at", "id"])
        assert len(result.items) == 20
        assert result.has_more is False

    def test_has_more(self) -> None:
        # limit+1 rows means there's another page
        rows = [_FakeRow(id=str(i), created_at=f"2026-01-{i:02d}") for i in range(1, 22)]
        result = paginate(rows, limit=20, sort_keys=["created_at", "id"])
        assert len(result.items) == 20
        assert result.has_more is True
        assert result.next_cursor is not None
        # cursor should point to the last included item
        decoded = decode_cursor(result.next_cursor)
        assert decoded is not None
        assert decoded["id"] == "20"

    def test_limit_clamped(self) -> None:
        rows = [_FakeRow(id="1", created_at="2026-01-01")] * 200
        result = paginate(rows, limit=200, sort_keys=["created_at", "id"])
        # limit is clamped to MAX_LIMIT; 200 rows > 100 → has_more
        assert len(result.items) == MAX_LIMIT
        assert result.has_more is True


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_default_limit(self) -> None:
        assert DEFAULT_LIMIT == 20

    def test_max_limit(self) -> None:
        assert MAX_LIMIT == 100


# ---------------------------------------------------------------------------
# PaginatedResponse model
# ---------------------------------------------------------------------------


class TestPaginatedResponseModel:
    def test_serialises(self) -> None:
        resp = PaginatedResponse(items=["a", "b"], next_cursor="xyz", has_more=True)
        data = resp.model_dump()
        assert data == {"items": ["a", "b"], "next_cursor": "xyz", "has_more": True}

    def test_defaults(self) -> None:
        resp = PaginatedResponse(items=[])
        assert resp.next_cursor is None
        assert resp.has_more is False


# ---------------------------------------------------------------------------
# ApiError serialisation
# ---------------------------------------------------------------------------


class TestApiErrorSerialisation:
    def _make_app(self) -> FastAPI:
        test_app = FastAPI()
        test_app.exception_handler(ApiError)(api_error_handler)

        @test_app.get("/boom")
        async def boom() -> None:
            raise not_found("artifact", "abc-123")

        return test_app

    def test_error_envelope_format(self) -> None:
        client = TestClient(self._make_app())
        resp = client.get("/boom")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        err = body["error"]
        assert err["code"] == "ARTIFACT_NOT_FOUND"
        assert "abc-123" in err["message"]
        assert err["details"] == {}

    def test_each_factory_status_code(self) -> None:
        assert not_found("x", "1").status_code == 404
        assert conflict("C", "m").status_code == 409
        assert validation_error("m").status_code == 400
        assert payload_too_large().status_code == 413
        assert unprocessable_entity("m").status_code == 422
        assert budget_exceeded().status_code == 429
        assert internal_error().status_code == 500

    def test_conflict_with_details(self) -> None:
        err = conflict(
            "ALREADY_APPROVED",
            "Artifact already approved.",
            {"artifact_id": "xyz"},
        )
        assert err.status_code == 409
        assert err.code == "ALREADY_APPROVED"
        assert err.details == {"artifact_id": "xyz"}


# ---------------------------------------------------------------------------
# get_workspace_id dependency
# ---------------------------------------------------------------------------


class TestGetWorkspaceId:
    def test_as_fastapi_dependency(self) -> None:
        test_app = FastAPI()

        @test_app.get("/ws")
        async def ws_route(workspace_id: str = Depends(get_workspace_id)) -> dict:
            return {"workspace_id": workspace_id}

        client = TestClient(test_app)
        resp = client.get("/ws")
        assert resp.status_code == 200
        assert resp.json() == {"workspace_id": "1"}
