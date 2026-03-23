"""
LiteLLM wrapper for BYOK-routed completions — KIN-276.

stream_completion() — async generator for SSE streaming
complete()          — non-streaming call (title generation, Haiku reranker)

All calls use the user-supplied BYOK API key.
Platform-internal calls (e.g. Haiku reranker) pass the key explicitly.
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator, Optional

from app.core.errors import LLMAuthError, LLMError

logger = logging.getLogger(__name__)


async def stream_completion(
    *,
    messages: list[dict],
    model: str,
    api_key: str,
    provider: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Stream LLM completion chunks via LiteLLM.

    Yields text delta strings. Raises LLMAuthError on 401/403, LLMError on other failures.
    """
    import litellm

    # LiteLLM accepts provider-prefixed model strings, e.g. "anthropic/claude-3-5-sonnet-20241022"
    litellm_model = _litellm_model_string(model, provider)

    try:
        response = await litellm.acompletion(
            model=litellm_model,
            messages=messages,
            api_key=api_key,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
    except Exception as exc:
        _raise_llm_error(exc)
        return  # unreachable — _raise_llm_error always raises


async def complete(
    *,
    messages: list[dict],
    model: str,
    api_key: str,
    provider: Optional[str] = None,
    max_tokens: int = 256,
) -> str:
    """Non-streaming completion. Returns the full response text.

    Used for: title generation, Haiku reranker calls.
    """
    import litellm

    litellm_model = _litellm_model_string(model, provider)

    try:
        response = await litellm.acompletion(
            model=litellm_model,
            messages=messages,
            api_key=api_key,
            stream=False,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        _raise_llm_error(exc)
        return ""  # unreachable


def _litellm_model_string(model: str, provider: Optional[str]) -> str:
    """Build the LiteLLM model string.

    LiteLLM routing:
      - anthropic/... → Anthropic SDK
      - openai/...    → OpenAI SDK
      - google/...    → Google SDK
      - groq/...      → Groq SDK
    If model is already prefixed, use as-is.
    """
    if "/" in model:
        return model  # already prefixed

    if provider == "anthropic" or model.startswith("claude"):
        return f"anthropic/{model}"
    if provider == "openai" or model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
        return f"openai/{model}"
    if provider == "google" or model.startswith("gemini"):
        return f"google/{model}"
    if provider == "groq" or model.startswith("llama") or model.startswith("mixtral"):
        return f"groq/{model}"
    return model


def _raise_llm_error(exc: Exception) -> None:
    """Convert LiteLLM / httpx / openai exceptions to KineticError subclasses."""
    exc_str = str(exc).lower()
    exc_type = type(exc).__name__

    # Auth errors: 401 Unauthorized, 403 Forbidden, "invalid api key", "authentication"
    if any(
        kw in exc_str
        for kw in ("401", "403", "invalid api key", "authentication", "unauthorized", "forbidden", "incorrect api key")
    ):
        raise LLMAuthError(
            "LLM authentication failed. Check your API key in Profile → API Keys."
        ) from exc

    # Quota / rate limit — surface as LLMError not payment (BYOK key's problem)
    if any(kw in exc_str for kw in ("429", "rate limit", "quota")):
        raise LLMError("LLM rate limit exceeded. Try again in a moment.") from exc

    raise LLMError(f"LLM request failed: {exc}") from exc
