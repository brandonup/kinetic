"""
Tests for Generation Endpoint + SSE Streaming — KIN-276 / KIN-296.

Scaffolded by Jìan (KIN-296). Activated by KIN-279 / KIN-292 once Big Head ships KIN-276.

Endpoint: POST /api/v1/conversations/{conversation_id}/messages

Spec ref: docs/specs/kin-257-projects-conversations-spec.md §2.3
"""

import pytest
from .conftest import make_company, make_project

SKIP_REASON = "Blocked — waiting for KIN-276 (Big Head generation endpoint implementation)"


# ---------------------------------------------------------------------------
# Message persistence
# ---------------------------------------------------------------------------

class TestMessagePersistence:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_user_message_persisted_with_role_user(self, auth_client):
        """After POST, a message row with role='user' and correct content must exist."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_assistant_message_persisted_on_stream_completion(self, auth_client):
        """After SSE stream ends, a message row with role='assistant' must exist."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_assistant_message_records_model_string(self, auth_client):
        """assistant message.model must be set to the model string used for generation."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_sequence_increments_per_message(self, auth_client):
        """Each new message's sequence must be previous_max + 1."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_system_messages_not_in_get_response(self, auth_client):
        """Any system-role messages written internally must not appear in GET /conversations/{id}."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_conversation_updated_at_bumped_after_message(self, auth_client):
        """conversations.updated_at must increase after a message is added."""
        ...


# ---------------------------------------------------------------------------
# SSE streaming
# ---------------------------------------------------------------------------

class TestSSEStreaming:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_response_is_event_stream(self, auth_client):
        """Response Content-Type must be text/event-stream."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_stream_emits_content_delta_events(self, auth_client):
        """Each SSE event carries a content delta chunk (non-empty data field)."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_stream_emits_done_event_at_end(self, auth_client):
        """The SSE stream must emit a terminal [DONE] or done event."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_stream_chunks_reassemble_to_full_response(self, auth_client):
        """Concatenating all delta chunks must produce the same text as the stored assistant message."""
        ...


# ---------------------------------------------------------------------------
# BYOK key routing
# ---------------------------------------------------------------------------

class TestBYOKRouting:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_no_byok_key_returns_402(self, auth_client):
        """If user has no API key configured for the selected model's provider, return 402."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_byok_key_used_for_generation(self, auth_client):
        """Generation call must use the user's BYOK key, not a platform key."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_model_override_per_message(self, auth_client):
        """model_id in request body overrides user's default_model_id for this message."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_falls_back_to_user_default_model(self, auth_client):
        """When model_id is omitted, user's default_model_id is used."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_disabled_model_id_rejected(self, auth_client, admin_client):
        """Requesting a disabled model returns 400 or 422."""
        ...


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestGenerationErrors:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_empty_content_returns_400(self, auth_client):
        """Empty or whitespace-only content must return 400."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_missing_content_returns_422(self, auth_client):
        """Missing content field must return 422."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_soft_deleted_conversation_returns_404(self, auth_client):
        """POST to a soft-deleted conversation must return 404."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_other_users_conversation_returns_404(self, auth_client, other_client):
        """POST to another user's conversation must return 404."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_llm_provider_error_returns_503(self, auth_client):
        """When the LLM provider returns an error, the endpoint must return 503."""
        ...


# ---------------------------------------------------------------------------
# Title generation (background job)
# ---------------------------------------------------------------------------

class TestTitleGeneration:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_title_auto_generated_after_first_message(self, auth_client):
        """After the first user message, conversation.title must be set (non-null)."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_title_not_overwritten_after_user_rename(self, auth_client):
        """If user has manually set a title via PATCH, title gen job must not overwrite it."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_title_stays_null_on_generation_failure(self, auth_client):
        """If title generation LLM call fails, title remains null (not an error)."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_title_max_60_chars(self, auth_client):
        """Auto-generated title must be 60 characters or fewer."""
        ...


# ---------------------------------------------------------------------------
# Agent attribution
# ---------------------------------------------------------------------------

class TestAgentAttribution:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_assistant_message_agent_definition_id_null_when_no_agent(self, auth_client):
        """When no agent is active, assistant message.agent_definition_id must be null."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_assistant_message_records_agent_id_when_agent_active(self, auth_client):
        """When an agent is active, assistant message.agent_definition_id = active_agent_id."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_prior_messages_agent_id_preserved_after_agent_switch(self, auth_client):
        """Switching agents mid-conversation must not alter existing message.agent_definition_id values."""
        ...


# ---------------------------------------------------------------------------
# Memory proposal stub (Sprint 5 hook)
# ---------------------------------------------------------------------------

class TestMemoryProposalTrigger:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_proposal_job_triggered_at_message_10_multiple(self, auth_client):
        """Memory proposal background job must be triggered when message count is a multiple of 10."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_proposal_job_not_triggered_before_message_10(self, auth_client):
        """Memory proposal job must not fire before 10 messages are exchanged."""
        ...
