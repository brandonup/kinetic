# Code Review — KIN-338: Background Job Hardening (Round 2)

**Date:** 2026-03-23
**Reviewer:** Gilfoyle
**Verdict:** APPROVED

---

## R1 Fix Verification

### C1 — Atomic lock before chunk cleanup
**Status: FIXED.**

`documents.py` lines 340–379. The atomic `UPDATE WHERE status='failed'` executes and its result is checked (raises 409 on empty return) before the chunk delete at lines 370–379. Comment on line 336 documents the ordering rationale explicitly. Correct.

### C2 — Ownership check before status check
**Status: FIXED.**

`documents.py` lines 255–271. KB ownership check (line 255–264) now runs before the `if doc["status"] != "failed"` guard (line 267). A cross-tenant user can no longer probe document status via the retry endpoint. Correct.

### I1 — Reverted to `get_event_loop()` in test helper
**Status: FIXED (correctly scoped).**

The `_run()` test helper in `test_background_jobs.py` line 26 uses `asyncio.get_event_loop().run_until_complete(coro)`, matching the `test_ingestion.py` convention. The service code (`background.py` line 53, `documents.py` lines 85, 181, 238, etc.) continues to use `asyncio.get_running_loop()` throughout, which is correct per conventions.md and Python 3.10+ guidance. No regression introduced.

### I2 — Mock pattern acknowledged
**Status: ACKNOWLEDGED.**

`MagicMock()` with chained attribute mocks is the established pattern across the test suite (matching `db_session` fixture in `conftest.py`, `test_ingestion.py`). No issue.

---

## Final Pass — New Findings

**None.**

The implementation is clean on all dimensions:

- `cleanup_stale_jobs` iterates all four processing states, catches per-state failures independently (resilience), and uses `run_in_executor` + `get_running_loop()` throughout (async correctness).
- The lambda capture `lambda s=status: ...` in the loop correctly closes over the iteration variable by value — no late-binding bug.
- The retry endpoint maintains the correct operation order: fetch → ownership → status guard → atomic lock → chunk cleanup → dispatch.
- HTTPException re-raise in the atomic lock block (lines 359–360) correctly prevents the outer `except Exception` from eating the 409.
- `main.py` lifespan non-fatal wrapping is appropriate — startup cleanup failure must not prevent the app from starting.
- Import ordering in `main.py` (router imports after `yield`) is non-standard but functionally harmless in Python's module loading model; not a blocking issue.
- Test coverage: 4 stale-cleanup tests + 1 retry dedup test. The dedup test wires ownership → atomic update → 409 path correctly, and verifies the "already in progress" message string.

---

## Summary

All 4 R1 findings confirmed fixed. No new issues identified. Architecture is correct, async patterns are correct, ordering constraints are enforced and documented.
