"""
Custom error classes and FastAPI exception handlers — Kinetic API.

Schema ref: docs/db-schema-spec.md (error conventions)
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


# ---------------------------------------------------------------------------
# Base + domain errors
# ---------------------------------------------------------------------------


class KineticError(Exception):
    status_code: int = 500
    detail: str = "Internal server error"


class NotFoundError(KineticError):
    status_code = 404

    def __init__(self, detail: str = "Not found") -> None:
        self.detail = detail


class ForbiddenError(KineticError):
    status_code = 403

    def __init__(self, detail: str = "Forbidden") -> None:
        self.detail = detail


class ValidationError(KineticError):
    status_code = 422

    def __init__(self, detail: str = "Validation error") -> None:
        self.detail = detail


class PaymentRequiredError(KineticError):
    """Raised when a BYOK API key is missing for the selected model provider."""

    status_code = 402

    def __init__(self, detail: str = "API key required for selected model provider") -> None:
        self.detail = detail


class ServiceUnavailableError(KineticError):
    """Raised when an upstream LLM provider returns an error."""

    status_code = 503

    def __init__(self, detail: str = "LLM provider unavailable") -> None:
        self.detail = detail


class UnauthorizedError(KineticError):
    status_code = 401

    def __init__(self, detail: str = "Not authenticated") -> None:
        self.detail = detail


# ---------------------------------------------------------------------------
# Exception handler (register on the FastAPI app)
# ---------------------------------------------------------------------------


async def kinetic_error_handler(request: Request, exc: KineticError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )
