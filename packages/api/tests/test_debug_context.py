"""
Tests for RetrievalDebugContext and StepTimer.

Covers:
  - StepTimer: timing accuracy, relative ms calculation
  - RetrievalDebugContext: step accumulation, total_duration_ms, to_trace_kwargs
"""

import time

from app.services.rag.debug_context import RetrievalDebugContext, StepTimer


class TestStepTimer:
    def test_start_stop_records_timing(self):
        """StepTimer records [start_ms, end_ms] relative to pipeline start."""
        ctx = RetrievalDebugContext(scope="project_kb")
        timer = ctx.start_step("embed")
        time.sleep(0.01)  # ~10ms
        timer.stop()

        assert "embed" in ctx.timings
        start_ms, end_ms = ctx.timings["embed"]
        assert start_ms >= 0
        assert end_ms > start_ms
        duration = end_ms - start_ms
        assert duration >= 5  # at least 5ms (sleep(0.01) = ~10ms, allow slack)

    def test_multiple_steps_recorded_sequentially(self):
        """Multiple steps are recorded with non-overlapping times."""
        ctx = RetrievalDebugContext(scope="agent_kb")

        t1 = ctx.start_step("embed")
        time.sleep(0.005)
        t1.stop()

        t2 = ctx.start_step("vector_search")
        time.sleep(0.005)
        t2.stop()

        assert "embed" in ctx.timings
        assert "vector_search" in ctx.timings

        embed_end = ctx.timings["embed"][1]
        vs_start = ctx.timings["vector_search"][0]
        assert vs_start >= embed_end  # vector_search starts after embed ends

    def test_start_returns_self(self):
        """StepTimer.start() returns self for inline use."""
        ctx = RetrievalDebugContext(scope="project_kb")
        timer = StepTimer(ctx, "test")
        result = timer.start()
        assert result is timer


class TestRetrievalDebugContext:
    def test_defaults(self):
        """RetrievalDebugContext starts with empty accumulators."""
        ctx = RetrievalDebugContext(scope="project_kb")
        assert ctx.scope == "project_kb"
        assert ctx.timings == {}
        assert ctx.vector_candidates == []
        assert ctx.mmr_selections == []
        assert ctx.injected_chunks == []
        assert ctx.gating_decision == "below_threshold"
        assert ctx.error_message is None

    def test_total_duration_ms(self):
        """total_duration_ms() returns elapsed time since construction."""
        ctx = RetrievalDebugContext(scope="project_kb")
        time.sleep(0.01)
        duration = ctx.total_duration_ms()
        assert duration >= 5  # at least 5ms

    def test_to_trace_kwargs_empty(self):
        """to_trace_kwargs() returns correct shape with no steps recorded."""
        ctx = RetrievalDebugContext(scope="project_kb")
        kwargs = ctx.to_trace_kwargs()

        assert kwargs["vector_candidates"] == []
        assert kwargs["mmr_selections"] == []
        assert kwargs["injected_chunks"] == []
        assert kwargs["gating_decision"] == "below_threshold"
        assert kwargs["error_message"] is None
        assert kwargs["timings"] is None  # empty timings → None
        assert isinstance(kwargs["retrieval_duration_ms"], int)

    def test_to_trace_kwargs_with_data(self):
        """to_trace_kwargs() includes accumulated data and timings."""
        ctx = RetrievalDebugContext(scope="agent_kb")
        ctx.vector_candidates = [{"chunk_id": "c1", "score": 0.9}]
        ctx.mmr_selections = [{"chunk_id": "c1", "score": 0.9}]
        ctx.injected_chunks = [{"chunk_id": "c1", "score": 0.9, "text_preview": "..."}]
        ctx.gating_decision = "injected"

        t = ctx.start_step("embed")
        time.sleep(0.005)
        t.stop()

        kwargs = ctx.to_trace_kwargs()

        assert kwargs["gating_decision"] == "injected"
        assert len(kwargs["vector_candidates"]) == 1
        assert kwargs["timings"] is not None
        assert "embed" in kwargs["timings"]

    def test_to_trace_kwargs_with_error(self):
        """to_trace_kwargs() includes error fields."""
        ctx = RetrievalDebugContext(scope="project_kb")
        ctx.gating_decision = "error"
        ctx.error_message = "OpenAI API timeout"

        kwargs = ctx.to_trace_kwargs()
        assert kwargs["gating_decision"] == "error"
        assert kwargs["error_message"] == "OpenAI API timeout"
