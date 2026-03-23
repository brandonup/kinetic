"""
Unit tests for services/compression.py — KIN-279.

Tests cover:
  - compress() skips when message count <= threshold
  - compress() calls LLM and persists summary
  - compress() uses prior summary as context for incremental compression
  - compress() falls back to truncation when no BYOK key provided
  - compress() falls back to truncation on LLM failure
  - should_compress() threshold boundary

Spec ref: docs/specs/kin-257-projects-conversations-spec.md §2.7
KIN-277: implementation ticket
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.compression import (
    COMPRESSION_THRESHOLD,
    VERBATIM_WINDOW,
    compress,
    should_compress,
)

CONV_ID = str(uuid4())


def _mock_chain(return_data):
    result = MagicMock()
    result.data = return_data
    chain = MagicMock()
    for method in (
        "select", "eq", "neq", "is_", "order", "limit",
        "maybe_single", "insert", "update", "delete",
    ):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = result
    return chain, result


def _make_supabase(messages: list[dict], summary: dict | None = None):
    sb = MagicMock()

    def _table(name):
        if name == "messages":
            chain, _ = _mock_chain(messages)
        elif name == "conversation_summaries":
            data = [summary] if summary else []
            chain, _ = _mock_chain(data)
            # Make insert work
            insert_chain, _ = _mock_chain([{"id": str(uuid4())}])
            chain.insert.return_value = insert_chain
        else:
            chain, _ = _mock_chain(None)
        return chain

    sb.table.side_effect = _table
    return sb


def _make_messages(count: int) -> list[dict]:
    msgs = []
    for i in range(count):
        role = "user" if i % 2 == 0 else "assistant"
        msgs.append({"role": role, "content": f"Message {i}", "sequence": i})
    return msgs


# ---------------------------------------------------------------------------
# should_compress
# ---------------------------------------------------------------------------


class TestShouldCompress:
    def test_false_at_threshold(self):
        assert should_compress(COMPRESSION_THRESHOLD) is False

    def test_false_below_threshold(self):
        assert should_compress(5) is False

    def test_true_above_threshold(self):
        assert should_compress(COMPRESSION_THRESHOLD + 1) is True


# ---------------------------------------------------------------------------
# compress()
# ---------------------------------------------------------------------------


class TestCompress:
    def test_skips_when_below_threshold(self):
        msgs = _make_messages(COMPRESSION_THRESHOLD - 1)
        sb = _make_supabase(msgs)
        result = asyncio.run(compress(CONV_ID, sb, api_key="key", model_string="anthropic/claude-haiku-4-5-20251001"))
        assert result is False

    def test_skips_when_not_enough_new_messages(self):
        # We have threshold+1 messages but all within verbatim window after the last summary
        msgs = _make_messages(COMPRESSION_THRESHOLD + 1)
        # Summary already covers most messages, leaving only VERBATIM_WINDOW uncovered
        summary = {
            "summary_text": "Previous summary",
            "messages_covered_up_to": msgs[-VERBATIM_WINDOW - 1]["sequence"],
        }
        sb = _make_supabase(msgs, summary=summary)
        result = asyncio.run(compress(CONV_ID, sb, api_key="key", model_string="model"))
        assert result is False

    def test_falls_back_to_truncation_when_no_key(self):
        msgs = _make_messages(COMPRESSION_THRESHOLD + 10)
        inserts: list[dict] = []

        sb = MagicMock()

        def _table(name):
            if name == "messages":
                chain, _ = _mock_chain(msgs)
            elif name == "conversation_summaries":
                chain, r = _mock_chain([])
                insert_chain = MagicMock()
                insert_result = MagicMock()
                insert_result.data = [{"id": str(uuid4())}]
                insert_chain.execute.return_value = insert_result

                def capture_insert(row):
                    inserts.append(row)
                    return insert_chain

                chain.insert.side_effect = capture_insert
            else:
                chain, _ = _mock_chain(None)
            return chain

        sb.table.side_effect = _table

        result = asyncio.run(compress(CONV_ID, sb, api_key=None, model_string=None))

        assert result is True
        assert len(inserts) == 1
        summary_text = inserts[0]["summary_text"]
        # Fallback truncation inserts a placeholder summary
        assert "truncated" in summary_text.lower() or "unavailable" in summary_text.lower()

    def test_calls_llm_and_persists_summary(self):
        msgs = _make_messages(COMPRESSION_THRESHOLD + 5)
        inserts: list[dict] = []

        sb = MagicMock()

        def _table(name):
            if name == "messages":
                chain, _ = _mock_chain(msgs)
            elif name == "conversation_summaries":
                chain, r = _mock_chain([])
                insert_chain = MagicMock()
                insert_result = MagicMock()
                insert_result.data = [{"id": str(uuid4())}]
                insert_chain.execute.return_value = insert_result

                def capture_insert(row):
                    inserts.append(row)
                    return insert_chain

                chain.insert.side_effect = capture_insert
            else:
                chain, _ = _mock_chain(None)
            return chain

        sb.table.side_effect = _table

        async def _run():
            with patch("app.services.compression.litellm") as mock_litellm:
                mock_response = MagicMock()
                mock_response.choices = [
                    MagicMock(message=MagicMock(content="LLM generated summary"))
                ]
                mock_litellm.acompletion = AsyncMock(return_value=mock_response)
                return await compress(
                    CONV_ID, sb,
                    api_key="sk-test",
                    model_string="anthropic/claude-haiku-4-5-20251001",
                )

        result = asyncio.run(_run())

        assert result is True
        assert len(inserts) == 1
        assert inserts[0]["summary_text"] == "LLM generated summary"
        assert inserts[0]["conversation_id"] == CONV_ID

    def test_uses_prior_summary_in_llm_prompt(self):
        """When a prior summary exists, it should be included in the compression prompt."""
        msgs = _make_messages(COMPRESSION_THRESHOLD + 10)
        prior_summary = {
            "summary_text": "Prior summary content",
            "messages_covered_up_to": 3,
        }
        llm_prompts: list[str] = []

        sb = MagicMock()

        def _table(name):
            if name == "messages":
                chain, _ = _mock_chain(msgs)
            elif name == "conversation_summaries":
                chain, r = _mock_chain([prior_summary])
                insert_chain = MagicMock()
                insert_result = MagicMock()
                insert_result.data = [{"id": str(uuid4())}]
                insert_chain.execute.return_value = insert_result
                chain.insert.return_value = insert_chain
            else:
                chain, _ = _mock_chain(None)
            return chain

        sb.table.side_effect = _table

        async def _run():
            with patch("app.services.compression.litellm") as mock_litellm:
                mock_response = MagicMock()
                mock_response.choices = [
                    MagicMock(message=MagicMock(content="New summary"))
                ]

                async def _capture_call(**kwargs):
                    prompt_text = kwargs["messages"][0]["content"]
                    llm_prompts.append(prompt_text)
                    return mock_response

                mock_litellm.acompletion = _capture_call
                return await compress(
                    CONV_ID, sb,
                    api_key="sk-test",
                    model_string="anthropic/claude-haiku-4-5-20251001",
                )

        asyncio.run(_run())

        assert llm_prompts, "LLM should have been called"
        assert "Prior summary content" in llm_prompts[0]

    def test_falls_back_to_truncation_on_llm_error(self):
        msgs = _make_messages(COMPRESSION_THRESHOLD + 5)
        inserts: list[dict] = []

        sb = MagicMock()

        def _table(name):
            if name == "messages":
                chain, _ = _mock_chain(msgs)
            elif name == "conversation_summaries":
                chain, r = _mock_chain([])
                insert_chain = MagicMock()
                insert_result = MagicMock()
                insert_result.data = [{"id": str(uuid4())}]
                insert_chain.execute.return_value = insert_result

                def capture_insert(row):
                    inserts.append(row)
                    return insert_chain

                chain.insert.side_effect = capture_insert
            else:
                chain, _ = _mock_chain(None)
            return chain

        sb.table.side_effect = _table

        async def _run():
            with patch("app.services.compression.litellm") as mock_litellm:
                mock_litellm.acompletion = AsyncMock(side_effect=Exception("LLM down"))
                return await compress(
                    CONV_ID, sb,
                    api_key="sk-test",
                    model_string="anthropic/claude-haiku-4-5-20251001",
                )

        result = asyncio.run(_run())

        assert result is True
        assert len(inserts) == 1
        # Fallback summary should be a truncation placeholder
        assert "unavailable" in inserts[0]["summary_text"].lower() or \
               "truncated" in inserts[0]["summary_text"].lower()
