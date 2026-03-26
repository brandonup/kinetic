"""
Rolling summary compression tests — KIN-392 / KIN-393

Covers:
  - _generate_summary_job: fresh summary, incremental, skip conditions, LLM failure
  - Compression fallback: BYOK/LLM failure inserts system notification (KIN-393)
  - Context assembler: messages_covered_up_to boundary respected
  - Generation endpoint: summary job dispatched on 10th message

Schema ref: docs/db-schema-spec.md §5 (conversations), §7 (conversation_summaries),
            §6 (messages), §1 (users), §2 (user_api_keys), §20 (llm_models)
Tickets: KIN-392, KIN-393
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_USER_ID

CONV_ID = str(uuid4())
MODEL_UUID = str(uuid4())
MODEL_NAME = "gpt-4o"
PROVIDER = "openai"

# Canonical encrypted key bytes (32-byte zero key in test env)
FAKE_CIPHERTEXT = b"\x00" * 48
FAKE_NONCE = b"\x00" * 12


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_messages(count: int) -> list[dict]:
    """Create `count` alternating user/assistant messages with sequences 0..count-1."""
    msgs = []
    for i in range(count):
        msgs.append({
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"Message {i}",
            "sequence": i,
        })
    return msgs


def _base_mock_client(
    messages: list[dict],
    prior_summary: dict | None = None,
    has_byok: bool = True,
    llm_response: str | None = "Summary of earlier conversation.",
    insert_raises: bool = False,
) -> MagicMock:
    """
    Build a mock Supabase client for _generate_summary_job tests.

    Covers: conversations, messages, conversation_summaries, users,
            llm_models, user_api_keys.
    """
    client = MagicMock()
    inserted: list[dict] = []

    def _table(name: str) -> MagicMock:
        chain = MagicMock()

        if name == "conversations":
            chain.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                data={"id": CONV_ID}
            )

        elif name == "messages":
            chain.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                data=messages
            )

        elif name == "conversation_summaries":
            # Fetch latest summary
            chain.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[prior_summary] if prior_summary else []
            )
            # Insert new summary
            if insert_raises:
                chain.insert.return_value.execute.side_effect = RuntimeError("DB insert error")
            else:
                def _insert(row):
                    inserted.append(row)
                    ret = MagicMock()
                    ret.execute.return_value = MagicMock(data=[{**row, "id": str(uuid4())}])
                    return ret
                chain.insert.side_effect = _insert

        elif name == "users":
            chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"default_model_id": MODEL_UUID}
            )

        elif name == "llm_models":
            chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"model_id": MODEL_NAME, "provider": PROVIDER}
            )

        elif name == "user_api_keys":
            if has_byok:
                chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={
                        "key_ciphertext": FAKE_CIPHERTEXT.hex(),
                        "key_nonce": FAKE_NONCE.hex(),
                    }
                )
            else:
                chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data=None
                )

        return chain

    client.table.side_effect = _table
    client._inserts = inserted
    return client


# ---------------------------------------------------------------------------
# _generate_summary_job — happy path: fresh summary
# ---------------------------------------------------------------------------


class TestGenerateSummaryJobFresh:
    """Fresh summary generated when no prior summary exists."""

    @patch("app.api.routes.conversations.call_llm")
    @patch("app.api.routes.conversations.load_master_key")
    @patch("app.api.routes.conversations.decrypt_api_key")
    @patch("app.api.routes.conversations.get_supabase_client")
    def test_fresh_summary_generated_and_inserted(
        self, mock_sb_fn, mock_decrypt, mock_load_key, mock_call_llm
    ):
        """22 messages → RECENT_TURNS_KEEP=20 → summary covers messages 0-1."""
        from app.api.routes.conversations import _generate_summary_job

        messages = _make_messages(22)
        mock_client = _base_mock_client(messages=messages, prior_summary=None)
        mock_sb_fn.return_value = mock_client
        mock_load_key.return_value = b"\x00" * 32
        mock_decrypt.return_value = "sk-test-key"
        mock_call_llm.return_value = "Summary of first 2 messages."

        _generate_summary_job(CONV_ID, TEST_USER_ID)

        mock_call_llm.assert_called_once()
        assert len(mock_client._inserts) == 1
        inserted = mock_client._inserts[0]
        assert inserted["conversation_id"] == CONV_ID
        assert inserted["summary_text"] == "Summary of first 2 messages."
        # 22 messages, RECENT_TURNS_KEEP=20 → covers messages 0..1 → target_covered_up_to=1
        assert inserted["messages_covered_up_to"] == 1
        assert inserted["model"] == MODEL_NAME

    @patch("app.api.routes.conversations.call_llm")
    @patch("app.api.routes.conversations.load_master_key")
    @patch("app.api.routes.conversations.decrypt_api_key")
    @patch("app.api.routes.conversations.get_supabase_client")
    def test_fresh_summary_prompt_uses_full_messages(
        self, mock_sb_fn, mock_decrypt, mock_load_key, mock_call_llm
    ):
        """Prompt text includes all messages outside the recent window."""
        from app.api.routes.conversations import _generate_summary_job, RECENT_TURNS_KEEP

        n = 25
        messages = _make_messages(n)
        mock_client = _base_mock_client(messages=messages, prior_summary=None)
        mock_sb_fn.return_value = mock_client
        mock_load_key.return_value = b"\x00" * 32
        mock_decrypt.return_value = "sk-test-key"
        mock_call_llm.return_value = "Summary text."

        _generate_summary_job(CONV_ID, TEST_USER_ID)

        call_args = mock_call_llm.call_args
        prompt_content = call_args.kwargs["messages"][0]["content"]
        # Summarize_new prompt should not reference prior summary
        assert "Previous summary" not in prompt_content
        # Should include messages outside the recent window
        messages_to_summarize = messages[:-RECENT_TURNS_KEEP]
        assert f"Message {messages_to_summarize[0]['sequence']}" in prompt_content
        assert f"Message {messages[-(RECENT_TURNS_KEEP+1)]['sequence']}" in prompt_content
        # Recent messages should NOT be in the prompt
        assert f"Message {messages[-1]['sequence']}" not in prompt_content


# ---------------------------------------------------------------------------
# _generate_summary_job — incremental update
# ---------------------------------------------------------------------------


class TestGenerateSummaryJobIncremental:
    """Incremental: prior summary folded with new messages."""

    @patch("app.api.routes.conversations.call_llm")
    @patch("app.api.routes.conversations.load_master_key")
    @patch("app.api.routes.conversations.decrypt_api_key")
    @patch("app.api.routes.conversations.get_supabase_client")
    def test_incremental_uses_prior_summary_in_prompt(
        self, mock_sb_fn, mock_decrypt, mock_load_key, mock_call_llm
    ):
        """Prior summary covering seq 0-4 + 30 total messages → incremental prompt."""
        from app.api.routes.conversations import _generate_summary_job, RECENT_TURNS_KEEP

        messages = _make_messages(30)  # seq 0-29
        prior = {"summary_text": "Prior summary text.", "messages_covered_up_to": 4}
        mock_client = _base_mock_client(messages=messages, prior_summary=prior)
        mock_sb_fn.return_value = mock_client
        mock_load_key.return_value = b"\x00" * 32
        mock_decrypt.return_value = "sk-test-key"
        mock_call_llm.return_value = "Updated summary."

        _generate_summary_job(CONV_ID, TEST_USER_ID)

        call_args = mock_call_llm.call_args
        prompt_content = call_args.kwargs["messages"][0]["content"]
        assert "Prior summary text." in prompt_content
        # New messages = seq 5 to (30 - RECENT_TURNS_KEEP - 1) = seq 5..9
        assert "Message 5" in prompt_content
        assert "Message 9" in prompt_content
        # Recent window NOT in prompt
        assert "Message 29" not in prompt_content

        # Inserted summary covers seq 9 (last of messages_to_summarize: seq 0..9)
        assert len(mock_client._inserts) == 1
        assert mock_client._inserts[0]["messages_covered_up_to"] == 9

    @patch("app.api.routes.conversations.call_llm")
    @patch("app.api.routes.conversations.load_master_key")
    @patch("app.api.routes.conversations.decrypt_api_key")
    @patch("app.api.routes.conversations.get_supabase_client")
    def test_incremental_skips_when_no_new_messages(
        self, mock_sb_fn, mock_decrypt, mock_load_key, mock_call_llm
    ):
        """Prior summary already covers all messages outside recent window → skip."""
        from app.api.routes.conversations import _generate_summary_job, RECENT_TURNS_KEEP

        n = 25  # seq 0-24
        messages = _make_messages(n)
        # Covered up to seq 4 (messages_to_summarize = seq 0..4, target_covered_up_to=4)
        target = messages[:-RECENT_TURNS_KEEP][-1]["sequence"]  # seq 4
        prior = {"summary_text": "Already current.", "messages_covered_up_to": target}
        mock_client = _base_mock_client(messages=messages, prior_summary=prior)
        mock_sb_fn.return_value = mock_client
        mock_load_key.return_value = b"\x00" * 32
        mock_decrypt.return_value = "sk-test-key"

        _generate_summary_job(CONV_ID, TEST_USER_ID)

        # Already current — LLM should not be called
        mock_call_llm.assert_not_called()
        assert len(mock_client._inserts) == 0


# ---------------------------------------------------------------------------
# _generate_summary_job — skip conditions
# ---------------------------------------------------------------------------


class TestGenerateSummaryJobSkips:
    """Silent-skip conditions: no insert, no LLM call."""

    @patch("app.api.routes.conversations.get_supabase_client")
    def test_skip_too_few_messages(self, mock_sb_fn):
        """Fewer than RECENT_TURNS_KEEP+1 messages → nothing to summarize."""
        from app.api.routes.conversations import _generate_summary_job, RECENT_TURNS_KEEP

        messages = _make_messages(RECENT_TURNS_KEEP)  # exactly at threshold
        mock_client = _base_mock_client(messages=messages)
        mock_sb_fn.return_value = mock_client

        _generate_summary_job(CONV_ID, TEST_USER_ID)

        # No insert called (no summary stored)
        assert len(mock_client._inserts) == 0

    @patch("app.api.routes.conversations.get_supabase_client")
    def test_skip_already_current(self, mock_sb_fn):
        """Summary already covers up to target → skip."""
        from app.api.routes.conversations import _generate_summary_job, RECENT_TURNS_KEEP

        n = 22
        messages = _make_messages(n)
        target = messages[:-RECENT_TURNS_KEEP][-1]["sequence"]
        prior = {"summary_text": "Current.", "messages_covered_up_to": target}
        mock_client = _base_mock_client(messages=messages, prior_summary=prior)
        mock_sb_fn.return_value = mock_client

        _generate_summary_job(CONV_ID, TEST_USER_ID)

        assert len(mock_client._inserts) == 0

    @patch("app.api.routes.conversations.get_supabase_client")
    def test_skip_no_byok_key(self, mock_sb_fn):
        """No BYOK key for provider → silent skip."""
        from app.api.routes.conversations import _generate_summary_job

        messages = _make_messages(25)
        mock_client = _base_mock_client(messages=messages, has_byok=False)
        mock_sb_fn.return_value = mock_client

        _generate_summary_job(CONV_ID, TEST_USER_ID)

        assert len(mock_client._inserts) == 0

    @patch("app.api.routes.conversations.call_llm")
    @patch("app.api.routes.conversations.load_master_key")
    @patch("app.api.routes.conversations.decrypt_api_key")
    @patch("app.api.routes.conversations.get_supabase_client")
    def test_skip_llm_failure(self, mock_sb_fn, mock_decrypt, mock_load_key, mock_call_llm):
        """LLM call raises → silent skip, no insert."""
        from app.api.routes.conversations import _generate_summary_job

        messages = _make_messages(25)
        mock_client = _base_mock_client(messages=messages)
        mock_sb_fn.return_value = mock_client
        mock_load_key.return_value = b"\x00" * 32
        mock_decrypt.return_value = "sk-test-key"
        mock_call_llm.side_effect = RuntimeError("LLM provider unavailable")

        # Should not raise
        _generate_summary_job(CONV_ID, TEST_USER_ID)

        assert len(mock_client._inserts) == 0

    @patch("app.api.routes.conversations.call_llm")
    @patch("app.api.routes.conversations.load_master_key")
    @patch("app.api.routes.conversations.decrypt_api_key")
    @patch("app.api.routes.conversations.get_supabase_client")
    def test_skip_empty_llm_response(self, mock_sb_fn, mock_decrypt, mock_load_key, mock_call_llm):
        """LLM returns empty string → silent skip."""
        from app.api.routes.conversations import _generate_summary_job

        messages = _make_messages(25)
        mock_client = _base_mock_client(messages=messages)
        mock_sb_fn.return_value = mock_client
        mock_load_key.return_value = b"\x00" * 32
        mock_decrypt.return_value = "sk-test-key"
        mock_call_llm.return_value = "   "  # whitespace only

        _generate_summary_job(CONV_ID, TEST_USER_ID)

        assert len(mock_client._inserts) == 0

    @patch("app.api.routes.conversations.call_llm")
    @patch("app.api.routes.conversations.load_master_key")
    @patch("app.api.routes.conversations.decrypt_api_key")
    @patch("app.api.routes.conversations.get_supabase_client")
    def test_insert_failure_logs_but_does_not_raise(
        self, mock_sb_fn, mock_decrypt, mock_load_key, mock_call_llm
    ):
        """DB insert failure → logged, does not raise."""
        from app.api.routes.conversations import _generate_summary_job

        messages = _make_messages(25)
        mock_client = _base_mock_client(messages=messages, insert_raises=True)
        mock_sb_fn.return_value = mock_client
        mock_load_key.return_value = b"\x00" * 32
        mock_decrypt.return_value = "sk-test-key"
        mock_call_llm.return_value = "A summary."

        # Must not raise
        _generate_summary_job(CONV_ID, TEST_USER_ID)

    @patch("app.api.routes.conversations.get_supabase_client")
    def test_conversation_not_found(self, mock_sb_fn):
        """Conversation not found for user → skip."""
        from app.api.routes.conversations import _generate_summary_job

        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_sb_fn.return_value = client

        _generate_summary_job(CONV_ID, TEST_USER_ID)

        # Nothing inserted
        client.table.return_value.insert.assert_not_called()


# ---------------------------------------------------------------------------
# Context assembler: messages_covered_up_to boundary
# ---------------------------------------------------------------------------


class TestAssemblerSummaryCoverage:
    """Context assembler: recent messages use messages_covered_up_to, not flat last-20."""

    @pytest.mark.asyncio
    async def test_recent_messages_exclude_summarized_range(self):
        """
        30 messages (seq 0-29), summary covers up to seq 9.
        Recent = messages with seq > 9 = seq 10..29 = 20 messages.
        Total history = 1 system (summary) + 20 = 21.
        No overlap between summary and recent.
        """
        from app.services.context_assembler import ContextAssembler

        messages = _make_messages(30)

        mock_sb = MagicMock()

        def _table(name):
            chain = MagicMock()
            if name == "conversations":
                chain.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"company_id": str(uuid4()), "project_id": None, "active_agent_id": None}
                )
            elif name == "users":
                chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"name": "Test", "bio": None, "default_model_id": None}
                )
            elif name == "companies":
                chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"name": "TestCo", "description": None}
                )
            elif name == "messages":
                chain.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                    data=messages
                )
            elif name == "conversation_summaries":
                chain.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"summary_text": "Summary text.", "messages_covered_up_to": 9}]
                )
            return chain

        mock_sb.table.side_effect = _table

        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=TEST_USER_ID,
            conversation_id=CONV_ID,
            query_text="test",
        )

        # 1 summary message + 20 recent messages (seq 10-29)
        assert len(result.conversation_history) == 21
        assert result.conversation_history[0]["role"] == "system"
        assert "Summary text." in result.conversation_history[0]["content"]
        # First recent message has sequence 10
        assert result.conversation_history[1]["content"] == "Message 10"
        # Last recent message has sequence 29
        assert result.conversation_history[-1]["content"] == "Message 29"

    @pytest.mark.asyncio
    async def test_no_summary_uses_last_20_messages(self):
        """Without a summary, fall back to last 20 messages."""
        from app.services.context_assembler import ContextAssembler

        messages = _make_messages(30)  # seq 0-29

        mock_sb = MagicMock()

        def _table(name):
            chain = MagicMock()
            if name == "conversations":
                chain.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"company_id": str(uuid4()), "project_id": None, "active_agent_id": None}
                )
            elif name == "users":
                chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"name": "Test", "bio": None, "default_model_id": None}
                )
            elif name == "companies":
                chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"name": "TestCo", "description": None}
                )
            elif name == "messages":
                chain.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
                    data=messages
                )
            elif name == "conversation_summaries":
                chain.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[]  # no summary
                )
            return chain

        mock_sb.table.side_effect = _table

        assembler = ContextAssembler()
        result = await assembler.assemble(
            supabase=mock_sb,
            user_id=TEST_USER_ID,
            conversation_id=CONV_ID,
            query_text="test",
        )

        # No summary, last 20 messages (seq 10-29)
        assert len(result.conversation_history) == 20
        assert result.conversation_history[0]["content"] == "Message 10"
        assert result.conversation_history[-1]["content"] == "Message 29"
        # No system message prepended
        assert all(m["role"] != "system" for m in result.conversation_history)


# ---------------------------------------------------------------------------
# prompts.py: summary prompts registered
# ---------------------------------------------------------------------------


class TestSummaryPromptsRegistered:
    def test_summarize_new_registered(self):
        from app.services.prompts import get_prompt

        text = get_prompt("conversation-summary-v1", "summarize_new")
        assert isinstance(text, str)
        assert len(text) > 0
        assert "summary" in text.lower()

    def test_summarize_incremental_registered(self):
        from app.services.prompts import get_prompt

        text = get_prompt("conversation-summary-v1", "summarize_incremental")
        assert isinstance(text, str)
        assert len(text) > 0
        assert "previous summary" in text.lower() or "running summary" in text.lower()


# ---------------------------------------------------------------------------
# Compression fallback — truncation notification (KIN-393)
# ---------------------------------------------------------------------------


def _make_fallback_client(
    messages: list[dict],
    has_byok: bool = False,
    existing_seq: int = 21,
) -> MagicMock:
    """
    Mock client for KIN-393 fallback tests. Tracks notification inserts on the
    messages table separately from summary inserts on conversation_summaries.
    """
    client = MagicMock()
    notification_inserts: list[dict] = []

    def _table(name: str) -> MagicMock:
        chain = MagicMock()

        if name == "conversations":
            chain.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                data={"id": CONV_ID}
            )

        elif name == "messages":
            # Main fetch: .select.eq.order.execute → message list
            order_chain = MagicMock()
            order_chain.execute.return_value = MagicMock(data=messages)
            # Sequence lookup for notification: .select.eq.order.limit.execute
            limit_chain = MagicMock()
            limit_chain.execute.return_value = MagicMock(
                data=[{"sequence": existing_seq}]
            )
            order_chain.limit.return_value = limit_chain
            chain.select.return_value.eq.return_value.order.return_value = order_chain

            def _insert(row):
                notification_inserts.append(row)
                ret = MagicMock()
                ret.execute.return_value = MagicMock(data=[{**row, "id": str(uuid4())}])
                return ret

            chain.insert.side_effect = _insert

        elif name == "conversation_summaries":
            chain.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[]
            )

        elif name == "users":
            chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"default_model_id": MODEL_UUID}
            )

        elif name == "llm_models":
            chain.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data={"model_id": MODEL_NAME, "provider": PROVIDER}
            )

        elif name == "user_api_keys":
            if has_byok:
                chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data={
                        "key_ciphertext": FAKE_CIPHERTEXT.hex(),
                        "key_nonce": FAKE_NONCE.hex(),
                    }
                )
            else:
                chain.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                    data=None
                )

        return chain

    client.table.side_effect = _table
    client._notification_inserts = notification_inserts
    return client


class TestCompressionFallbackNotification:
    """KIN-393: BYOK/LLM failure triggers truncation fallback + inline system notification."""

    @patch("app.api.routes.conversations.get_supabase_client")
    def test_no_byok_key_inserts_notification(self, mock_sb_fn):
        """No BYOK key for provider → system notification inserted with correct content."""
        from app.api.routes.conversations import (
            _TRUNCATION_NOTIFICATION,
            _generate_summary_job,
        )

        messages = _make_messages(25)
        mock_client = _make_fallback_client(messages=messages, has_byok=False, existing_seq=24)
        mock_sb_fn.return_value = mock_client

        _generate_summary_job(CONV_ID, TEST_USER_ID)

        assert len(mock_client._notification_inserts) == 1
        row = mock_client._notification_inserts[0]
        assert row["role"] == "system"
        assert row["content"] == _TRUNCATION_NOTIFICATION
        assert row["conversation_id"] == CONV_ID
        assert row["sequence"] == 25  # existing max seq=24, next=25

    @patch("app.api.routes.conversations.load_master_key")
    @patch("app.api.routes.conversations.decrypt_api_key")
    @patch("app.api.routes.conversations.get_supabase_client")
    def test_key_decryption_failure_inserts_notification(
        self, mock_sb_fn, mock_decrypt, mock_load_key
    ):
        """Key decryption failure → system notification inserted."""
        from app.api.routes.conversations import (
            _TRUNCATION_NOTIFICATION,
            _generate_summary_job,
        )

        messages = _make_messages(25)
        mock_client = _make_fallback_client(messages=messages, has_byok=True)
        mock_sb_fn.return_value = mock_client
        mock_load_key.return_value = b"\x00" * 32
        mock_decrypt.side_effect = ValueError("InvalidTag — wrong key")

        _generate_summary_job(CONV_ID, TEST_USER_ID)

        assert len(mock_client._notification_inserts) == 1
        assert mock_client._notification_inserts[0]["role"] == "system"
        assert mock_client._notification_inserts[0]["content"] == _TRUNCATION_NOTIFICATION

    @patch("app.api.routes.conversations.call_llm")
    @patch("app.api.routes.conversations.load_master_key")
    @patch("app.api.routes.conversations.decrypt_api_key")
    @patch("app.api.routes.conversations.get_supabase_client")
    def test_llm_failure_inserts_notification(
        self, mock_sb_fn, mock_decrypt, mock_load_key, mock_call_llm
    ):
        """LLM call failure (rate limit / outage) → system notification inserted."""
        from app.api.routes.conversations import (
            _TRUNCATION_NOTIFICATION,
            _generate_summary_job,
        )

        messages = _make_messages(25)
        mock_client = _make_fallback_client(messages=messages, has_byok=True)
        mock_sb_fn.return_value = mock_client
        mock_load_key.return_value = b"\x00" * 32
        mock_decrypt.return_value = "sk-test-key"
        mock_call_llm.side_effect = RuntimeError("rate limit exceeded")

        _generate_summary_job(CONV_ID, TEST_USER_ID)

        assert len(mock_client._notification_inserts) == 1
        assert mock_client._notification_inserts[0]["role"] == "system"
        assert mock_client._notification_inserts[0]["content"] == _TRUNCATION_NOTIFICATION

    @patch("app.api.routes.conversations.get_supabase_client")
    def test_too_few_messages_no_notification(self, mock_sb_fn):
        """Fewer than RECENT_TURNS_KEEP messages → nothing to compress → no notification."""
        from app.api.routes.conversations import RECENT_TURNS_KEEP, _generate_summary_job

        messages = _make_messages(RECENT_TURNS_KEEP)  # exactly at threshold, nothing to summarize
        mock_client = _make_fallback_client(messages=messages, has_byok=False)
        mock_sb_fn.return_value = mock_client

        _generate_summary_job(CONV_ID, TEST_USER_ID)

        assert len(mock_client._notification_inserts) == 0

    @patch("app.api.routes.conversations.call_llm")
    @patch("app.api.routes.conversations.load_master_key")
    @patch("app.api.routes.conversations.decrypt_api_key")
    @patch("app.api.routes.conversations.get_supabase_client")
    def test_successful_summary_no_notification(
        self, mock_sb_fn, mock_decrypt, mock_load_key, mock_call_llm
    ):
        """Successful compression → no notification inserted."""
        from app.api.routes.conversations import _generate_summary_job

        messages = _make_messages(25)
        mock_client = _make_fallback_client(messages=messages, has_byok=True)
        mock_sb_fn.return_value = mock_client
        mock_load_key.return_value = b"\x00" * 32
        mock_decrypt.return_value = "sk-test-key"
        mock_call_llm.return_value = "A good summary."

        _generate_summary_job(CONV_ID, TEST_USER_ID)

        assert len(mock_client._notification_inserts) == 0

    @patch("app.api.routes.conversations.get_supabase_client")
    def test_notification_sequence_increments_from_max(self, mock_sb_fn):
        """Notification sequence = max existing sequence + 1."""
        from app.api.routes.conversations import _generate_summary_job

        messages = _make_messages(25)
        mock_client = _make_fallback_client(messages=messages, has_byok=False, existing_seq=99)
        mock_sb_fn.return_value = mock_client

        _generate_summary_job(CONV_ID, TEST_USER_ID)

        assert len(mock_client._notification_inserts) == 1
        assert mock_client._notification_inserts[0]["sequence"] == 100

    @patch("app.api.routes.conversations.get_supabase_client")
    def test_already_current_summary_no_notification(self, mock_sb_fn):
        """Summary already current → nothing to do → no notification."""
        from app.api.routes.conversations import RECENT_TURNS_KEEP, _generate_summary_job

        n = 22
        messages = _make_messages(n)
        target = messages[:-RECENT_TURNS_KEEP][-1]["sequence"]

        client = MagicMock()
        notification_inserts: list[dict] = []

        def _table(name: str) -> MagicMock:
            chain = MagicMock()
            if name == "conversations":
                chain.select.return_value.eq.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value = MagicMock(
                    data={"id": CONV_ID}
                )
            elif name == "messages":
                order_chain = MagicMock()
                order_chain.execute.return_value = MagicMock(data=messages)
                chain.select.return_value.eq.return_value.order.return_value = order_chain

                def _insert(row):
                    notification_inserts.append(row)
                    return MagicMock()

                chain.insert.side_effect = _insert
            elif name == "conversation_summaries":
                chain.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                    data=[{"summary_text": "Current.", "messages_covered_up_to": target}]
                )
            return chain

        client.table.side_effect = _table
        mock_sb_fn.return_value = client

        _generate_summary_job(CONV_ID, TEST_USER_ID)

        assert len(notification_inserts) == 0
