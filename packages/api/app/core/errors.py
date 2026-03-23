"""
Custom exception types and FastAPI exception handlers.

All API errors return: {"error": {"code": "...", "message": "..."}}
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class KineticError(Exception):
    """Base for all domain errors."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str = "An unexpected error occurred") -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(KineticError):
    status_code = 404
    code = "not_found"


class ForbiddenError(KineticError):
    status_code = 403
    code = "forbidden"


class UnauthorizedError(KineticError):
    status_code = 401
    code = "unauthorized"


class ValidationError(KineticError):
    status_code = 400
    code = "validation_error"


class ConflictError(KineticError):
    status_code = 409
    code = "conflict"


class PaymentRequiredError(KineticError):
    """Raised when a BYOK key is missing for the requested LLM provider."""

    status_code = 402
    code = "byok_key_required"


class LLMError(KineticError):
    """Raised when an upstream LLM provider returns an error."""

    status_code = 502
    code = "llm_error"


class LLMAuthError(LLMError):
    """Raised when the LLM provider rejects the API key."""

    status_code = 502
    code = "llm_auth_failed"


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------


def add_exception_handlers(app: FastAPI) -> None:
    """Register all error handlers on the FastAPI app instance."""

    @app.exception_handler(KineticError)
    async def _kinetic_error(request: Request, exc: KineticError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def _pydantic_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": exc.errors(),
                }
            },
        )
