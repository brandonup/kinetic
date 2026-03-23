"""
Error handling and exception handlers for Kinetic API.

Ported from FounderPanel with CORS-aware error responses.
"""

import logging
import re
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, status
from fastapi import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from app.core.config import settings

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base exception for application errors."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class AuthenticationError(AppException):
    """Raised when authentication fails."""

    def __init__(
        self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None
    ):
        super().__init__("AUTHENTICATION_ERROR", message, details)


class AuthorizationError(AppException):
    """Raised when user lacks required permissions."""

    def __init__(
        self, message: str = "Insufficient permissions", details: Optional[Dict[str, Any]] = None
    ):
        super().__init__("AUTHORIZATION_ERROR", message, details)


class NotFoundError(AppException):
    """Raised when a resource is not found."""

    def __init__(
        self, message: str = "Resource not found", details: Optional[Dict[str, Any]] = None
    ):
        super().__init__("NOT_FOUND", message, details)


class ValidationError(AppException):
    """Raised when input validation fails."""

    def __init__(
        self, message: str = "Validation failed", details: Optional[Dict[str, Any]] = None
    ):
        super().__init__("VALIDATION_ERROR", message, details)


class MemoryCapExceededError(AppException):
    """Raised when a write would exceed the active memory token cap."""

    def __init__(self, current_tokens: int, cap_tokens: int):
        super().__init__(
            "MEMORY_CAP_EXCEEDED",
            f"Memory is full ({current_tokens}/{cap_tokens} tokens). Delete an entry to make room.",
            {"current_tokens": current_tokens, "cap_tokens": cap_tokens},
        )


def error_response(
    code: str, message: str, details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a structured error response body."""
    return {"error": {"code": code, "message": message, "details": details or {}}}


def add_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers with the FastAPI app."""

    def _origin_allowed(origin: Optional[str]) -> bool:
        if not origin:
            return False
        origins = getattr(settings, "CORS_ORIGINS", []) or []
        for allowed in origins:
            if not isinstance(allowed, str) or not allowed:
                continue
            if "*" in allowed:
                pattern = "^" + re.escape(allowed).replace("\\*", ".*") + "$"
                if re.match(pattern, origin):
                    return True
            elif origin == allowed:
                return True
        return False

    def _cors_headers(request: Request) -> Dict[str, str]:
        origin = request.headers.get("origin")
        if not origin or not _origin_allowed(origin):
            return {}
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        }

    @app.exception_handler(FastAPIHTTPException)
    async def http_exception_handler(request: Request, exc: FastAPIHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=_cors_headers(request),
        )

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        if isinstance(exc, AuthenticationError):
            status_code = status.HTTP_401_UNAUTHORIZED
        elif isinstance(exc, AuthorizationError):
            status_code = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, NotFoundError):
            status_code = status.HTTP_404_NOT_FOUND
        elif isinstance(exc, ValidationError):
            status_code = status.HTTP_400_BAD_REQUEST
        elif isinstance(exc, MemoryCapExceededError):
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

        logger.error(f"{exc.code}: {exc.message}", extra={"details": exc.details})
        return JSONResponse(
            status_code=status_code,
            content=error_response(exc.code, exc.message, exc.details),
            headers=_cors_headers(request),
        )

    @app.exception_handler(PydanticValidationError)
    async def pydantic_validation_handler(
        request: Request, exc: PydanticValidationError
    ) -> JSONResponse:
        logger.error(f"Validation error: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=error_response("VALIDATION_ERROR", str(exc)),
            headers=_cors_headers(request),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        error_id = f"internal_{uuid.uuid4().hex[:10]}"
        logger.exception(
            f"Unexpected error (error_id={error_id}, path={getattr(request.url, 'path', None)})"
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response(
                "INTERNAL_ERROR",
                "An unexpected error occurred. Please try again later.",
                details={"error_id": error_id},
            ),
            headers=_cors_headers(request),
        )
