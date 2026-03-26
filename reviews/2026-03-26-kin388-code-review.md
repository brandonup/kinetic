# Code Review — KIN-388: Wire active memory triggers into chat — save action + periodic proposals

**Date:** 2026-03-26
**Reviewer:** Gilfoyle
**Verdict:** CHANGES_REQUESTED
**Critical:** 1 | **Important:** 1

---

## Files Reviewed

- `packages/api/app/api/routes/generation.py` — lines 308–343 (periodic trigger block)
- `packages/api/tests/test_generation.py` — `TestPeriodicProposalTriggerFires`, `TestPeriodicProposalTriggerSkipped`, `TestPeriodicProposalDebounced`

---

## Findings

### C1 — Critical | `other` | Unawaited `run_in_executor` — job may not execute

**File:** `packages/api/app/api/routes/generation.py`, line 328

**Problem:**

```python
_loop.run_in_executor(
    None,
    _generate_periodic_proposals_job,
    _conversation_id,
    current_user.user_id,
)
```

`run_in_executor` returns a coroutine/future. Without `await` or `asyncio.ensure_future`, no reference is held and the future is not scheduled on the event loop. CPython will GC it with a RuntimeWarning ("Future was garbage collected") and the job will silently not run. This is precisely the fire-and-forget antipattern — the intent is right but the mechanism is wrong.

Every other `run_in_executor` call in this file is correctly awaited (lines 131, 151, 164, 177, 201, 219, 287, 314). This is the only one without `await` or explicit scheduling.

**Fix:**

```python
asyncio.ensure_future(
    _loop.run_in_executor(
        None,
        _generate_periodic_proposals_job,
        _conversation_id,
        current_user.user_id,
    )
)
```

`ensure_future` schedules the future on the running loop without blocking the generator. This matches the fire-and-forget intent while actually guaranteeing the job is submitted.

---

### I1 — Important | `test-missing` | `TestPeriodicProposalTriggerFires` assertion does not prove production behavior

**File:** `packages/api/tests/test_generation.py`, line 1147

**Problem:**

```python
assert mock_job.called
```

`_generate_periodic_proposals_job` is passed *into* `run_in_executor` as a callable — the executor calls it in a thread pool, not inline. `mock_job.called` is only `True` in this test because `TestClient` runs under `anyio`'s synchronous ASGI adapter, where the executor resolves synchronously before the assertion. In a real async context with a real thread pool, `mock_job.called` would be `False` immediately after `run_in_executor` fires and before the thread finishes. The test is asserting test-harness behavior, not production behavior.

Additionally, the comment in the test at lines 1097–1099 is wrong: it says "Sequence 8 is the last existing message" but the fixture sets `sequence: 7`. The math in the comment leads a reader to conclude total=11 (not a multiple of 10), but the test is actually targeting total=10. The comment is internally contradictory and will mislead future maintainers.

**Fix:**

After C1 is fixed (using `ensure_future`), update the test to assert that the future was submitted to the event loop — not that the callable was invoked directly. One correct approach: patch `asyncio.ensure_future` and assert it was called with the expected future. Alternatively, use `asyncio.create_task` and assert the task was created. Either way, the current `mock_job.called` assertion is not a reliable proxy for "the job was dispatched."

Fix the comment to accurately describe the sequence arithmetic.

---

## What Is Good

- Placement of the trigger after the `done` event yield is correct — client receives the stream before the background work starts.
- The try/except wrapper is correct: non-fatal failure handling, proper log level (`warning`), no error surfaced to the client.
- Debounce logic (checking for pending proposals before dispatch) is the right design and matches the `store_message` pattern.
- Lazy import of `_generate_periodic_proposals_job` is correct — avoids circular import at module load time.
- `total_messages = _sequence + 1` arithmetic is correct (assistant seq is 0-indexed, +1 gives total count).
- 3 test classes cover the three distinct branches: fires, skipped, debounced — good structural coverage.

---

## Summary

One production defect: the job is never actually submitted to the event loop. The remaining issue is a test assertion that happens to pass in the test harness but doesn't prove the production code path works. Fix C1 first; I1 is a mandatory follow-on to verify the fix is actually tested correctly.
