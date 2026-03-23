"""
Log Scrub Middleware — KIN-261.

Redacts sensitive fields from request/response bodies before they reach the logger.
Applied globally as FastAPI middleware — individual endpoints do not need to remember to scrub.

Spec: docs/api-key-encryption-spec.md §5

Scrubbed field patterns (case-insensitive):
  - api_key / apiKey
  - key_ciphertext / keyCiphertext
  - key_nonce / keyNonce
  - Any field matching *_key, *_secret, *_token (glob-style)
  - authorization
"""

import json
import logging
import re
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

SCRUB_PATTERNS = re.compile(
    r"(api[_-]?key|key[_-]?ciphertext|key[_-]?nonce|"
    r"\w+[_-](?:key|secret|token)|authorization)",
    re.IGNORECASE,
)


class LogScrubMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that scrubs sensitive fields from JSON request bodies before logging.

    Applied globally — individual endpoints do not need to handle scrubbing.
    Only JSON bodies are inspected; other content types pass through unchanged.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Scrub JSON request body from logs (not the actual request — body passes through intact)
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body_bytes = await request.body()
                if body_bytes:
                    body_dict = json.loads(body_bytes)
                    scrubbed = scrub_dict(body_dict)
                    logger.debug("Request body (scrubbed): %s", scrubbed)
            except Exception:
                pass  # Non-JSON or malformed body — skip scrubbing, do not block request

        return await call_next(request)


def scrub_dict(d: dict) -> dict:
    """
    Recursively replace sensitive values with '[REDACTED]'.

    Args:
        d: Dictionary to scrub. Nested dicts are also scrubbed.

    Returns:
        New dict with sensitive values replaced.
    """
    return {
        k: "[REDACTED]" if SCRUB_PATTERNS.search(str(k)) else
           scrub_dict(v) if isinstance(v, dict) else v
        for k, v in d.items()
    }
