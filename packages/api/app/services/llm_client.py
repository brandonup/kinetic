"""
Unified LLM client using LiteLLM for multi-provider support.

Provides a single interface for Anthropic, OpenAI, Google, and Groq via LiteLLM.
All calls use BYOK (Bring Your Own Key): pass `api_key` to route user-supplied keys.
There are no platform-owned keys — every call must receive an explicit api_key.

Ported from FounderPanel with Kinetic-specific changes:
- `api_key` param added to all call surfaces (BYOK support)
- No global key configuration — all keys passed per-call
- get_model_for_use_case removed (Kinetic uses per-query user model selection)
"""

import asyncio
import logging
import random
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.core.config import settings

litellm_import_error: Optional[Exception] = None
try:
    import litellm
except ModuleNotFoundError as exc:
    litellm = None  # type: ignore[assignment]
    litellm_import_error = exc

logger = logging.getLogger(__name__)

if litellm is not None:
    # No global key configuration — all LLM keys are BYOK, passed per-call
    # via the api_key parameter. LiteLLM's global key slots are intentionally
    # left empty. For Google/Gemini, LiteLLM looks for GEMINI_API_KEY env var.

    # Suppress LiteLLM's verbose logging
    litellm.suppress_debug_info = True

    # Default request timeout — overridden per call
    litellm.request_timeout = 600


def _require_litellm() -> None:
    """Raise ModuleNotFoundError if litellm is not installed."""
    if litellm is None:
        raise ModuleNotFoundError(
            "litellm not found. Please install dependencies (pip install -r requirements.txt)."
        ) from litellm_import_error


def get_provider_model(model_name: str) -> str:
    """
    Convert model name to LiteLLM format with provider prefix.

    LiteLLM uses provider prefixes to route requests to the correct API.
    OpenAI models don't need a prefix.

    Args:
        model_name: Model name (e.g., "gpt-4o", "claude-haiku-3-5", "gemini-2.5-flash")

    Returns:
        Model string with provider prefix for LiteLLM routing.

    Examples:
        "gpt-4o"                 -> "gpt-4o"
        "claude-haiku-3-5"       -> "anthropic/claude-haiku-3-5"
        "gemini-2.5-flash"       -> "gemini/gemini-2.5-flash"
        "llama-3.3-70b-instruct" -> "groq/llama-3.3-70b-instruct"
    """
    if not model_name:
        logger.warning("Empty model name provided, defaulting to gpt-4o-mini")
        return "gpt-4o-mini"

    # Groq models with org prefixes must be checked before OpenAI routing
    if model_name.startswith("meta-llama/"):
        return f"groq/{model_name}"
    if model_name.startswith("openai/gpt-oss"):
        return f"groq/{model_name}"
    if model_name.startswith("claude"):
        return f"anthropic/{model_name}"
    elif model_name.startswith("gemini"):
        return f"gemini/{model_name}"
    elif model_name.startswith(("llama", "mixtral", "gemma")):
        return f"groq/{model_name}"
    elif model_name.startswith("grok"):
        return f"xai/{model_name}"

    # Default: OpenAI (gpt-*, o1-*, o3-*)
    return model_name


def _is_rate_limit_error(exc: Exception) -> bool:
    """
    Best-effort classification of rate limit exceptions across providers.
    """
    try:
        rate_limit_cls = getattr(litellm, "RateLimitError", None)
        if rate_limit_cls and isinstance(exc, rate_limit_cls):
            return True
    except Exception:
        pass

    msg = (str(exc) or "").lower()
    return any(
        s in msg
        for s in [
            "rate limit",
            "ratelimit",
            "too many requests",
            "tpm",
            "tokens per minute",
            "requests per minute",
        ]
    )


def _safe_error_message(exc: Exception, max_len: int = 300) -> str:
    """
    Truncate and sanitize exception messages so they are safe to show to end users.
    """
    msg = str(exc) or ""
    msg = msg.replace("https://", "").replace("http://", "")
    if len(msg) > max_len:
        msg = msg[:max_len] + "…"
    return msg


def call_llm(
    messages: List[Dict[str, str]],
    model: str,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    max_completion_tokens: Optional[int] = None,
    timeout: int = 20,
    reasoning_effort: Optional[str] = None,
    max_attempts: int = 2,
    **kwargs: Any,
) -> str:
    """
    Call LLM with provider-agnostic interface (synchronous).

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        model: Model name — converted to LiteLLM provider format internally.
        api_key: User's BYOK API key. When provided, overrides platform env key for
            this call. When None, LiteLLM uses platform-configured env keys.
        temperature: Sampling temperature (0-1). None uses provider default.
        max_tokens: Max tokens to generate (legacy parameter).
        max_completion_tokens: Max completion tokens (preferred for reasoning models).
        timeout: Request timeout in seconds.
        reasoning_effort: Reasoning effort for models that support it ("low"/"medium"/"high").
        max_attempts: Maximum retry attempts (default 2). Set to 1 to disable retries.
        **kwargs: Additional parameters passed to litellm.completion.

    Returns:
        Response text from the LLM.

    Raises:
        Exception: If the LLM call fails after all attempts.
    """
    _require_litellm()
    provider_model = get_provider_model(model)

    _attempt = 0

    while _attempt < max_attempts:
        _attempt += 1

        try:
            completion_params: Dict[str, Any] = {
                "model": provider_model,
                "messages": messages,
                "timeout": timeout,
            }

            if temperature is not None:
                completion_params["temperature"] = temperature

            if max_completion_tokens is not None:
                completion_params["max_completion_tokens"] = max_completion_tokens
            elif max_tokens is not None:
                completion_params["max_tokens"] = max_tokens

            if reasoning_effort is not None:
                completion_params["reasoning_effort"] = reasoning_effort

            # BYOK: pass user key only when explicitly provided
            if api_key:
                completion_params["api_key"] = api_key

            # Filter out internal params from kwargs
            filtered_kwargs = {k: v for k, v in kwargs.items() if k != "max_attempts"}
            completion_params.update(filtered_kwargs)

            logger.debug(
                "Calling LLM model: %s (attempt %d/%d)", provider_model, _attempt, max_attempts
            )

            response = litellm.completion(**completion_params)

            if not response.choices or len(response.choices) == 0:
                logger.error("LLM returned empty choices")
                raise ValueError("LLM returned empty response")

            def _get(obj: Any, key: str, default: Any = None) -> Any:
                return (
                    obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)
                )

            content = (
                response.choices[0].message.content
                if hasattr(response.choices[0].message, "content")
                else None
            )
            if content is None and hasattr(response.choices[0].message, "text"):
                content = response.choices[0].message.text

            # Fallbacks for providers that return text outside chat message.content
            if content is None or (isinstance(content, str) and content.strip() == ""):
                alt_text = _get(response, "output_text", None)
                if isinstance(alt_text, str) and alt_text.strip():
                    content = alt_text
                else:
                    output = _get(response, "output", None)
                    if output:
                        try:
                            for item in output if isinstance(output, list) else [output]:
                                parts = _get(item, "content", None)
                                if not parts:
                                    continue
                                for part in parts if isinstance(parts, list) else [parts]:
                                    txt = _get(part, "text", None)
                                    if isinstance(txt, str) and txt.strip():
                                        content = txt
                                        raise StopIteration
                        except StopIteration:
                            pass
                    if content is None or (isinstance(content, str) and content.strip() == ""):
                        msg2 = _get(response, "message", None)
                        alt2 = _get(msg2, "content", None) if msg2 else None
                        if isinstance(alt2, str) and alt2.strip():
                            content = alt2

            finish_reason = getattr(response.choices[0], "finish_reason", None)

            # Retry on empty content with max-tokens finish reason
            if (content is None or content.strip() == "") and finish_reason in [
                "length",
                "max_tokens",
            ]:
                if _attempt < max_attempts:
                    logger.warning(
                        "Empty response with finish_reason=%s, retrying with 4x tokens",
                        finish_reason,
                    )
                    if max_completion_tokens is not None:
                        max_completion_tokens = max_completion_tokens * 4
                    elif max_tokens is not None:
                        max_tokens = max_tokens * 4
                    else:
                        max_tokens = 4096
                    continue

            if content is None:
                logger.error("LLM returned None content")
                raise ValueError("LLM returned None content")

            return str(content)

        except Exception as e:
            logger.error("LLM call failed for model %s: %s", provider_model, e)
            raise

    raise ValueError(f"Failed to get valid response after {max_attempts} attempts")


def call_llm_with_response(
    messages: List[Dict[str, str]],
    model: str,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    max_completion_tokens: Optional[int] = None,
    timeout: int = 20,
    **kwargs: Any,
) -> Any:
    """
    Call LLM and return the full response object (synchronous).

    Use when you need access to usage statistics or other metadata.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        model: Model name — converted to LiteLLM provider format internally.
        api_key: User's BYOK API key. When provided, overrides platform env key.
        Same remaining args as call_llm().

    Returns:
        Full LiteLLM response object.
    """
    _require_litellm()
    provider_model = get_provider_model(model)

    try:
        completion_params: Dict[str, Any] = {
            "model": provider_model,
            "messages": messages,
            "timeout": timeout,
        }

        if temperature is not None:
            completion_params["temperature"] = temperature

        if max_completion_tokens is not None:
            completion_params["max_completion_tokens"] = max_completion_tokens
        elif max_tokens is not None:
            completion_params["max_tokens"] = max_tokens

        if api_key:
            completion_params["api_key"] = api_key

        completion_params.update(kwargs)

        logger.debug("Calling LLM (full response) model: %s", provider_model)

        response = litellm.completion(**completion_params)
        return response

    except Exception as e:
        logger.error("LLM call failed for model %s: %s", provider_model, e)
        raise


def _extract_text_from_chunk(provider_model: str, chunk: Any) -> Optional[str]:
    """
    Normalize streaming deltas across providers into plain text.
    LiteLLM normalizes most providers to OpenAI-style; fallbacks handle raw formats.
    """
    try:
        def get_attr(obj: Any, key: str, default: Any = None) -> Any:
            return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

        # Standard OpenAI format (LiteLLM normalizes most providers to this)
        choices = get_attr(chunk, "choices", None)
        if choices and len(choices) > 0:
            delta = get_attr(choices[0], "delta", {})
            content = get_attr(delta, "content", None)
            if content is not None:
                return str(content)

        # Fallback: Anthropic raw (delta.text)
        delta = get_attr(chunk, "delta", None)
        if delta:
            text = get_attr(delta, "text", None)
            if text is not None:
                return str(text)

        # Fallback: Raw Gemini candidates format
        candidates = get_attr(chunk, "candidates", None)
        if candidates and len(candidates) > 0:
            content = get_attr(candidates[0], "content", {})
            parts = get_attr(content, "parts", None)
            if parts and len(parts) > 0:
                text = get_attr(parts[0], "text", None)
                if text is not None:
                    return str(text)

    except Exception as e:
        logger.warning("Failed to extract text from chunk for %s: %s", provider_model, e)

    return None


async def stream_llm(
    messages: List[Dict[str, str]],
    model: str,
    api_key: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    max_completion_tokens: Optional[int] = None,
    timeout: int = 40,
    reasoning_effort: Optional[str] = None,
    max_attempts: int = 2,
    fallback_models: Optional[List[str]] = None,
    **kwargs: Any,
) -> AsyncGenerator[str, None]:
    """
    Stream LLM deltas with provider-normalized text (async).

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        model: Model name — converted to LiteLLM provider format internally.
        api_key: User's BYOK API key. When provided, overrides platform env key.
        temperature: Sampling temperature. None uses provider default.
        max_tokens: Max tokens to generate.
        max_completion_tokens: Preferred for reasoning models.
        timeout: Per-stream timeout in seconds.
        reasoning_effort: Reasoning effort level for supporting models.
        max_attempts: Max retry attempts on rate limits.
        fallback_models: Additional models to try if primary is rate-limited.
        **kwargs: Additional parameters passed to litellm.acompletion.

    Yields:
        Text delta chunks as they arrive from the provider.
    """
    _require_litellm()
    # Default conservative completion budget if caller doesn't specify.
    if max_tokens is None and max_completion_tokens is None:
        max_completion_tokens = 1024

    attempt = 0
    models_to_try: List[str] = [model] + (fallback_models or [])
    last_exc: Optional[Exception] = None

    while attempt < max(1, int(max_attempts)):
        attempt += 1
        chosen_model = models_to_try[min(attempt - 1, len(models_to_try) - 1)]
        provider_model = get_provider_model(chosen_model)

        completion_params: Dict[str, Any] = {
            "model": provider_model,
            "messages": messages,
            "timeout": timeout,
            "stream": True,
        }

        if temperature is not None:
            completion_params["temperature"] = temperature

        if max_completion_tokens is not None:
            completion_params["max_completion_tokens"] = max_completion_tokens
        elif max_tokens is not None:
            completion_params["max_tokens"] = max_tokens

        if reasoning_effort is not None:
            completion_params["reasoning_effort"] = reasoning_effort

        # BYOK: pass user key only when explicitly provided
        if api_key:
            completion_params["api_key"] = api_key

        filtered_kwargs = {
            k: v for k, v in kwargs.items() if k not in {"max_attempts", "fallback_models"}
        }
        completion_params.update(filtered_kwargs)

        try:
            stream = await litellm.acompletion(**completion_params)
        except Exception as e:
            last_exc = e
            if _is_rate_limit_error(e) and attempt < max(1, int(max_attempts)):
                if attempt < len(models_to_try):
                    logger.warning(
                        "Rate limit starting stream for %s; falling back to %s",
                        provider_model,
                        models_to_try[attempt],
                    )
                else:
                    backoff = min(20.0, 1.5 * (2 ** (attempt - 1)))
                    backoff += random.uniform(0.0, 0.25)
                    logger.warning(
                        "Rate limit starting stream for %s; backing off %.2fs (attempt %d/%d)",
                        provider_model,
                        backoff,
                        attempt,
                        max_attempts,
                    )
                    await asyncio.sleep(backoff)
                continue

            logger.error(
                "Failed to start streaming completion for %s: %s",
                provider_model,
                _safe_error_message(e),
            )
            raise

        start_time = asyncio.get_event_loop().time()

        try:
            async for chunk in stream:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    raise asyncio.TimeoutError(
                        f"LLM streaming exceeded timeout ({timeout}s)"
                    )
                text = _extract_text_from_chunk(provider_model, chunk)
                if text:
                    yield text
            return
        except asyncio.TimeoutError:
            logger.error("LLM stream timed out after %ds for model %s", timeout, provider_model)
            raise
        except Exception as e:
            # Mid-stream failures are not retryable (partial output may already be yielded).
            logger.error(
                "LLM streaming failed for %s: %s",
                provider_model,
                _safe_error_message(e),
            )
            raise

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Failed to start streaming completion (unknown error)")
