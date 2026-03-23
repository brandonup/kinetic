"""
Thin background task abstraction.

MVP: delegates to FastAPI BackgroundTasks.
Migration to Celery/RQ: replace TaskDispatcher.dispatch() body only — no other changes needed.

ADR-001: Background processing uses FastAPI BackgroundTasks for MVP.
Gilfoyle requirement: thin abstraction layer so Celery migration is a one-file change.
"""

from __future__ import annotations

from fastapi import BackgroundTasks


class TaskDispatcher:
    """
    Enqueue background tasks via FastAPI BackgroundTasks.

    Usage:
        dispatcher = TaskDispatcher(background_tasks)
        dispatcher.dispatch(my_async_fn, arg1, arg2, kwarg=value)
    """

    def __init__(self, background_tasks: BackgroundTasks) -> None:
        self._bt = background_tasks

    def dispatch(self, fn, *args, **kwargs) -> None:
        """
        Enqueue fn(*args, **kwargs) for background execution.

        MVP: delegates to BackgroundTasks.add_task.
        Celery migration: replace with celery_app.send_task(fn, args, kwargs).
        """
        self._bt.add_task(fn, *args, **kwargs)
