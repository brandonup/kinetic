"""
Retrieval debug context — accumulates per-stage timing and data during RAG retrieval.

Ported from FounderPanel's debug_logger.py, adapted for Kinetic's pipeline
(pgvector, async run_in_executor pattern, no ORM).

The RetrievalDebugContext is created before a retrieve() call and optionally
passed in. Each pipeline stage records its timing via StepTimer. After retrieve()
completes, the context is converted to kwargs for write_retrieval_trace().

Usage:
    ctx = RetrievalDebugContext(scope="project_kb")
    timer = ctx.start_step("embed")
    result = await loop.run_in_executor(...)
    timer.stop()
    ...
    trace_writer.write_retrieval_trace(message_id, **ctx.to_trace_kwargs(), supabase=client)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


class StepTimer:
    """Records wall-clock timing for a single pipeline stage.

    Uses start()/stop() instead of context manager because retrieve() stages
    are async — the timer must span an ``await``.

    Timing is stored as [start_ms, end_ms] relative to the pipeline start,
    not absolute timestamps. This makes the waterfall chart positioning trivial.
    """

    def __init__(self, ctx: RetrievalDebugContext, name: str) -> None:
        self._ctx = ctx
        self._name = name
        self._start: float = 0.0

    def start(self) -> StepTimer:
        """Record the start time. Returns self for inline use."""
        self._start = time.perf_counter()
        return self

    def stop(self) -> None:
        """Record the end time and store [start_ms, end_ms] on the context."""
        end = time.perf_counter()
        pipeline_start = self._ctx._pipeline_start
        start_ms = round((self._start - pipeline_start) * 1000, 2)
        end_ms = round((end - pipeline_start) * 1000, 2)
        self._ctx.timings[self._name] = [start_ms, end_ms]


@dataclass
class RetrievalDebugContext:
    """Accumulator for retrieval pipeline debug data.

    Created once per retrieve() call (one per scope). Passed through the
    pipeline stages to collect timing + intermediate results. Converted to
    a dict via to_trace_kwargs() for the trace writer.

    Attributes:
        scope: "project_kb" or "agent_kb".
        timings: Per-stage timing data {name: [start_ms, end_ms]}.
        vector_candidates: Pre-MMR candidates [{chunk_id, score}].
        mmr_selections: Post-MMR selections [{chunk_id, score}].
        injected_chunks: Final injected chunks [{chunk_id, score, text_preview}].
        gating_decision: 'injected', 'below_threshold', or 'error'.
        error_message: Populated on embedding/retrieval failure.
    """

    scope: str
    _pipeline_start: float = field(default_factory=time.perf_counter, repr=False)
    timings: dict[str, list[float]] = field(default_factory=dict)
    vector_candidates: list[dict] = field(default_factory=list)
    mmr_selections: list[dict] = field(default_factory=list)
    injected_chunks: list[dict] = field(default_factory=list)
    gating_decision: str = "below_threshold"
    error_message: Optional[str] = None

    def start_step(self, name: str) -> StepTimer:
        """Create and start a timer for the named pipeline stage."""
        timer = StepTimer(self, name)
        timer.start()
        return timer

    def total_duration_ms(self) -> int:
        """Elapsed wall-clock milliseconds since pipeline start."""
        return round((time.perf_counter() - self._pipeline_start) * 1000)

    def to_trace_kwargs(self) -> dict:
        """Convert accumulated data to kwargs for write_retrieval_trace().

        Returns a dict with keys matching write_retrieval_trace's parameters
        (excluding message_id, scope, query_text, and supabase which are
        supplied by the caller).
        """
        return {
            "vector_candidates": self.vector_candidates,
            "mmr_selections": self.mmr_selections,
            "injected_chunks": self.injected_chunks,
            "gating_decision": self.gating_decision,
            "error_message": self.error_message,
            "retrieval_duration_ms": self.total_duration_ms(),
            "timings": self.timings if self.timings else None,
        }
