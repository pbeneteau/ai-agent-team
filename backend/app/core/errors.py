"""Standardized API error handling.

All API errors use this envelope (TDD-04 Section 1.4):

    {
      "error": {
        "code": "ERROR_CODE",
        "message": "Human-readable message.",
        "details": {}
      }
    }
"""

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Raise in route handlers to return a structured error response."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    """FastAPI exception handler — register with ``app.exception_handler(ApiError)``."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


# ---------------------------------------------------------------------------
# Error factories
# ---------------------------------------------------------------------------


def not_found(resource: str, resource_id: str) -> ApiError:
    """404 — resource does not exist."""
    return ApiError(
        status_code=404,
        code=f"{resource.upper()}_NOT_FOUND",
        message=f"{resource.capitalize()} with id '{resource_id}' not found.",
    )


def conflict(code: str, message: str, details: dict[str, Any] | None = None) -> ApiError:
    """409 — duplicate or invalid state transition."""
    return ApiError(status_code=409, code=code, message=message, details=details)


def validation_error(message: str, details: dict[str, Any] | None = None) -> ApiError:
    """400 — invalid request payload."""
    return ApiError(
        status_code=400, code="VALIDATION_ERROR", message=message, details=details
    )


def payload_too_large(message: str = "Payload too large.") -> ApiError:
    """413 — file upload exceeds limit."""
    return ApiError(status_code=413, code="PAYLOAD_TOO_LARGE", message=message)


def unprocessable_entity(
    message: str, details: dict[str, Any] | None = None
) -> ApiError:
    """422 — structurally valid but semantically wrong."""
    return ApiError(
        status_code=422,
        code="UNPROCESSABLE_ENTITY",
        message=message,
        details=details,
    )


def budget_exceeded(
    message: str = "Budget ceiling reached.", details: dict[str, Any] | None = None
) -> ApiError:
    """429 — monthly or per-artifact budget ceiling hit."""
    return ApiError(
        status_code=429, code="BUDGET_EXCEEDED", message=message, details=details
    )


def internal_error(
    message: str = "Internal server error.", details: dict[str, Any] | None = None
) -> ApiError:
    """500 — unexpected failure."""
    return ApiError(
        status_code=500, code="INTERNAL_ERROR", message=message, details=details
    )
