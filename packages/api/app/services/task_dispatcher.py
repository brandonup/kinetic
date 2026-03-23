"""
TaskDispatcher — thin abstraction over FastAPI BackgroundTasks.

Decision ref: MEMORY.md 2026-03-22 — "Background processing: in-process
(FastAPI BackgroundTasks) for MVP. Gilfoyle to add thin abstraction layer so
migration to Celery/RQ later is a one-file change."

Migration to Celery/RQ = implement CeleryTaskDispatcher here, swap injection
at the FastAPI dependency level. Zero changes to route code.
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine, Protocol, runtime_checkable

from fastapi import BackgroundTasks


@runtime_checkable
class TaskDispatcher(Protocol):
    """Protocol satisfied by any dispatcher implementation."""

    def dispatch(
        self,
        func: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> None: ...


class FastAPITaskDispatcher:
    """
    Wraps FastAPI BackgroundTasks.

    Background tasks run AFTER the HTTP response is sent. For streaming
    endpoints this means after the last SSE byte is flushed.
    """

    def __init__(self, background_tasks: BackgroundTasks) -> None:
        self._bg = background_tasks

    def dispatch(self, func: Callable[..., Any], /, *args: Any, **kwargs: Any) -> None:
        self._bg.add_task(func, *args, **kwargs)
