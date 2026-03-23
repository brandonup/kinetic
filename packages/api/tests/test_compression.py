"""
Tests for Conversation History Compression — KIN-277 / KIN-296.

Scaffolded by Jìan (KIN-296). Activated by KIN-279 / KIN-292 once Big Head ships KIN-277.

Spec ref: docs/specs/kin-257-projects-conversations-spec.md §2.7
ADR ref:  ADR-004 (Gilfoyle) — threshold values, verbatim window, model choice.
          Spec placeholder: threshold=20 total messages, verbatim window=10 recent.
          Update these tests once ADR-004 is published.
"""

import pytest

SKIP_REASON = "Blocked — waiting for KIN-277 (Big Head compression implementation) and ADR-004 (threshold values)"

# Placeholder constants — update when ADR-004 locks the values.
COMPRESSION_THRESHOLD = 20   # total non-system messages that trigger compression
VERBATIM_WINDOW = 10          # most recent messages kept verbatim


# ---------------------------------------------------------------------------
# Trigger conditions
# ---------------------------------------------------------------------------

class TestCompressionTrigger:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_compression_not_triggered_below_threshold(self, auth_client):
        """No conversation_summaries row created when message count < COMPRESSION_THRESHOLD."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_compression_triggered_at_threshold(self, auth_client):
        """A conversation_summaries row must be created when message count reaches COMPRESSION_THRESHOLD."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_system_messages_excluded_from_threshold_count(self, auth_client):
        """Only user+assistant messages count toward the threshold — system messages are ignored."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_compression_not_triggered_again_until_new_messages_exceed_window(self, auth_client):
        """After compression runs, it must not fire again until enough new messages accumulate."""
        ...


# ---------------------------------------------------------------------------
# Summary storage
# ---------------------------------------------------------------------------

class TestSummaryStorage:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_summary_stored_in_conversation_summaries(self, auth_client):
        """compression job writes a row to conversation_summaries with non-empty summary_text."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_messages_covered_up_to_is_correct(self, auth_client):
        """summary.messages_covered_up_to must equal the sequence number of the last compressed message."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_model_field_recorded_on_summary(self, auth_client):
        """conversation_summaries.model must be set to the model string used for the summary call."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_summary_rows_are_append_only(self, auth_client):
        """Successive compression runs append new rows — they do not overwrite existing ones."""
        ...


# ---------------------------------------------------------------------------
# Context assembly with compression active
# ---------------------------------------------------------------------------

class TestContextAssemblyWithCompression:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_latest_summary_injected_for_old_messages(self, auth_client):
        """When a summary exists, context assembly injects it in place of the compressed messages."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_verbatim_window_preserved(self, auth_client):
        """The VERBATIM_WINDOW most recent messages are injected verbatim after the summary."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_messages_before_summary_coverage_not_injected_verbatim(self, auth_client):
        """Messages with sequence <= summary.messages_covered_up_to are NOT injected verbatim."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_most_recent_summary_used_when_multiple_exist(self, auth_client):
        """When multiple summary rows exist, only the latest (by created_at) is injected."""
        ...


# ---------------------------------------------------------------------------
# BYOK failure fallback
# ---------------------------------------------------------------------------

class TestCompressionFallback:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_truncation_fallback_when_byok_key_missing(self, auth_client):
        """When no BYOK key is available, oldest messages are truncated instead of summarised."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_truncation_fallback_when_byok_call_fails(self, auth_client):
        """When the BYOK LLM call fails, fallback truncation applies without raising an error."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_no_summary_row_written_on_truncation_fallback(self, auth_client):
        """Truncation fallback must not write a conversation_summaries row."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_inline_notification_sent_on_fallback(self, auth_client):
        """On truncation fallback, the generation response must include an inline notification event."""
        ...


# ---------------------------------------------------------------------------
# Background job isolation
# ---------------------------------------------------------------------------

class TestCompressionJobIsolation:
    @pytest.mark.skip(reason=SKIP_REASON)
    def test_compression_is_per_conversation(self, auth_client):
        """Compression triggered for conversation A must not affect conversation B."""
        ...

    @pytest.mark.skip(reason=SKIP_REASON)
    def test_compression_runs_as_background_task(self, auth_client):
        """The generation SSE stream must complete before compression runs — not blocking the response."""
        ...
