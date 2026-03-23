"""
Tests for Kinetic LLM client abstraction (KIN-254).

Covers:
- Provider model routing (get_provider_model)
- Synchronous completion (call_llm)
- BYOK api_key pass-through on all call surfaces
- Retry logic on empty response + length finish_reason
- Async streaming (stream_llm)
- Rate limit detection (_is_rate_limit_error)
- Import guard (_require_litellm)

No real LLM calls are made — litellm is fully mocked.
"""

from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Pure-function tests — no mocks needed
# ---------------------------------------------------------------------------


class TestGetProviderModel:
    """get_provider_model routes model names to LiteLLM provider prefixes."""

    def test_get_provider_model_openai(self) -> None:
        from app.services.llm_client import get_provider_model

        assert get_provider_model("gpt-4o") == "gpt-4o"

    def test_get_provider_model_openai_mini(self) -> None:
        from app.services.llm_client import get_provider_model

        assert get_provider_model("gpt-4o-mini") == "gpt-4o-mini"

    def test_get_provider_model_claude(self) -> None:
        from app.services.llm_client import get_provider_model

        assert get_provider_model("claude-haiku-3-5") == "anthropic/claude-haiku-3-5"

    def test_get_provider_model_gemini(self) -> None:
        from app.services.llm_client import get_provider_model

        assert get_provider_model("gemini-2.5-flash") == "gemini/gemini-2.5-flash"

    def test_get_provider_model_groq(self) -> None:
        from app.services.llm_client import get_provider_model

        assert get_provider_model("llama-3.3-70b-instruct") == "groq/llama-3.3-70b-instruct"

    def test_get_provider_model_empty(self) -> None:
        from app.services.llm_client import get_provider_model

        assert get_provider_model("") == "gpt-4o-mini"


class TestIsRateLimitError:
    """_is_rate_limit_error classifies exceptions by message content."""

    def test_is_rate_limit_error_true_message(self) -> None:
        from app.services.llm_client import _is_rate_limit_error

        assert _is_rate_limit_error(Exception("rate limit exceeded")) is True

    def test_is_rate_limit_error_true_too_many(self) -> None:
        from app.services.llm_client import _is_rate_limit_error

        assert _is_rate_limit_error(Exception("too many requests")) is True

    def test_is_rate_limit_error_false(self) -> None:
        from app.services.llm_client import _is_rate_limit_error

        assert _is_rate_limit_error(Exception("connection reset by peer")) is False

    def test_is_rate_limit_error_false_generic(self) -> None:
        from app.services.llm_client import _is_rate_limit_error

        assert _is_rate_limit_error(ValueError("invalid model")) is False


# ---------------------------------------------------------------------------
# call_llm tests — mock litellm.completion
# ---------------------------------------------------------------------------


def _make_completion_response(content: str, finish_reason: str = "stop") -> MagicMock:
    """Build a minimal mock litellm completion response."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = finish_reason
    resp = MagicMock()
    resp.choices = [choice]
    return resp


class TestCallLlm:
    """call_llm synchronous completion surface."""

    def test_call_llm_success(self) -> None:
        """Happy path: mocked completion returns text."""
        from app.services.llm_client import call_llm

        mock_resp = _make_completion_response("Hello from LLM")

        with patch("app.services.llm_client.litellm") as mock_litellm:
            mock_litellm.completion.return_value = mock_resp
            result = call_llm(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o-mini",
            )

        assert result == "Hello from LLM"

    def test_call_llm_passes_api_key(self) -> None:
        """BYOK: api_key present in kwargs flows through to litellm.completion."""
        from app.services.llm_client import call_llm

        mock_resp = _make_completion_response("response")

        with patch("app.services.llm_client.litellm") as mock_litellm:
            mock_litellm.completion.return_value = mock_resp
            call_llm(
                messages=[{"role": "user", "content": "hi"}],
                model="claude-haiku-3-5",
                api_key="sk-ant-user-byok-key",
            )
            call_kwargs = mock_litellm.completion.call_args[1]

        assert call_kwargs.get("api_key") == "sk-ant-user-byok-key"

    def test_call_llm_platform_key_used_when_no_byok(self) -> None:
        """Without api_key, LiteLLM uses env (platform key) — no api_key kwarg passed."""
        from app.services.llm_client import call_llm

        mock_resp = _make_completion_response("response")

        with patch("app.services.llm_client.litellm") as mock_litellm:
            mock_litellm.completion.return_value = mock_resp
            call_llm(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o-mini",
            )
            call_kwargs = mock_litellm.completion.call_args[1]

        assert "api_key" not in call_kwargs

    def test_call_llm_raises_on_failure(self) -> None:
        """LLM errors must propagate — no silent swallow."""
        from app.services.llm_client import call_llm

        with patch("app.services.llm_client.litellm") as mock_litellm:
            mock_litellm.completion.side_effect = RuntimeError("provider down")

            with pytest.raises(RuntimeError, match="provider down"):
                call_llm(
                    messages=[{"role": "user", "content": "hi"}],
                    model="gpt-4o-mini",
                    max_attempts=1,
                )

    def test_call_llm_retries_on_empty_with_length_finish(self) -> None:
        """Empty content + finish_reason='length' triggers retry with 4x tokens."""
        from app.services.llm_client import call_llm

        empty_resp = _make_completion_response("", finish_reason="length")
        good_resp = _make_completion_response("full content after retry")

        with patch("app.services.llm_client.litellm") as mock_litellm:
            mock_litellm.completion.side_effect = [empty_resp, good_resp]
            result = call_llm(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o-mini",
                max_tokens=256,
                max_attempts=2,
            )

        assert result == "full content after retry"
        assert mock_litellm.completion.call_count == 2
        # Second call should have 4x tokens
        second_call_kwargs = mock_litellm.completion.call_args_list[1][1]
        assert second_call_kwargs.get("max_tokens") == 1024


# ---------------------------------------------------------------------------
# stream_llm tests — mock litellm.acompletion
# ---------------------------------------------------------------------------


async def _async_chunks(texts: list[str]) -> AsyncIterator[MagicMock]:
    """Yield mock stream chunks for each text delta."""
    for text in texts:
        chunk = MagicMock()
        delta = MagicMock()
        delta.content = text
        choice = MagicMock()
        choice.delta = delta
        chunk.choices = [choice]
        yield chunk


class TestStreamLlm:
    """stream_llm async streaming surface."""

    @pytest.mark.asyncio
    async def test_stream_llm_yields_text(self) -> None:
        """stream_llm yields text deltas from the mock stream."""
        from app.services.llm_client import stream_llm

        with patch("app.services.llm_client.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                return_value=_async_chunks(["Hello", " world", "!"])
            )
            chunks = []
            async for chunk in stream_llm(
                messages=[{"role": "user", "content": "hi"}],
                model="gpt-4o-mini",
            ):
                chunks.append(chunk)

        assert "".join(chunks) == "Hello world!"

    @pytest.mark.asyncio
    async def test_stream_llm_passes_api_key(self) -> None:
        """BYOK: api_key flows through to litellm.acompletion."""
        from app.services.llm_client import stream_llm

        with patch("app.services.llm_client.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(
                return_value=_async_chunks(["ok"])
            )
            async for _ in stream_llm(
                messages=[{"role": "user", "content": "hi"}],
                model="claude-haiku-3-5",
                api_key="sk-ant-user-byok-key",
            ):
                pass
            call_kwargs = mock_litellm.acompletion.call_args[1]

        assert call_kwargs.get("api_key") == "sk-ant-user-byok-key"


# ---------------------------------------------------------------------------
# Import guard
# ---------------------------------------------------------------------------


class TestRequireLitellm:
    """_require_litellm raises when litellm is not installed."""

    def test_require_litellm_raises_when_none(self) -> None:
        import app.services.llm_client as llm_mod

        original = llm_mod.litellm
        try:
            llm_mod.litellm = None  # type: ignore[assignment]
            with pytest.raises(ModuleNotFoundError):
                llm_mod._require_litellm()
        finally:
            llm_mod.litellm = original
