"""
Task dispatcher — fire-and-forget async background jobs.

Usage:
    dispatcher = TaskDispatcher()
    dispatcher.dispatch(my_async_fn, arg1=val1, arg2=val2)

Errors in dispatched tasks are logged but never propagate to callers.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class TaskDispatcher:
    """Schedules coroutine functions as non-blocking background tasks."""

    def dispatch(
        self,
        fn: Callable[..., Coroutine[Any, Any, Any]],
        **kwargs: Any,
    ) -> None:
        """Schedule fn(**kwargs) as a fire-and-forget asyncio task.

        Errors in the task are caught and logged — they never propagate.
        """
        async def _run_safe() -> None:
            try:
                await fn(**kwargs)
            except Exception:
                logger.exception("Background task %s failed", fn.__name__)

        asyncio.ensure_future(_run_safe())
