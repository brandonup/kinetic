# Code Review R2 — KIN-378: Document Delete Endpoints

**Date:** 2026-03-26
**Reviewer:** Gilfoyle
**Verdict:** APPROVED
**Findings:** 0 Critical, 0 Important

---

## Prior Findings Verification

All 6 findings from R1 are resolved.

| Finding | Status | Notes |
|---|---|---|
| C1: Hard DELETE violated soft-delete architecture | FIXED | Both endpoints use `.update({"deleted_at": "now()"})`. No hard delete anywhere. |
| C2: 403 for cross-tenant access | FIXED | Both endpoints return 404. Single-delete KB ownership check (documents.py:451); delete-all via `_verify_kb_ownership` (kb_management.py:110). |
| I1: Duplicated ACTIVE_INGESTION_STATUSES | FIXED | Extracted to `app/core/constants.py` as `frozenset`. Both routes import from there. |
| I2: Misleading 500 error message | FIXED | Now reads: "Unexpected state: documents were not found at delete time (possible race condition)." |
| I3: Missing storage failure test for delete-all | FIXED | `test_storage_failure_does_not_fail_delete_all` added and correct. |
| I4: Fragile mock | FIXED | Both `_mock_single_delete` and `_mock_delete_all` use call-count dispatch with proper UPDATE chain mocking. |

---

## New Issues Found

None.

---

## Advisory Notes (non-blocking)

**`"now()"` as string literal for `deleted_at`:** Both endpoints pass `{"deleted_at": "now()"}` to the Supabase client. PostgreSQL accepts `'now()'` as a valid `timestamptz` input — this works correctly at the DB level. Style preference would be `datetime.now(UTC).isoformat()` for explicitness and testability, but this is not a defect.

**`pending` status is deletable while potentially mid-queue:** A document with status `pending` could be picked up by the ingestion worker after `deleted_at` is set. The ingestion pipeline should filter out soft-deleted documents before processing. This is an architectural gap in the ingestion worker (out of scope for this ticket), not a defect in the delete endpoints. Flag when implementing the cleanup job.

---

## Test Coverage

11 tests covering:
- Happy path (single + bulk)
- Active ingestion guard (409) for all 3 blocked statuses
- Cross-tenant 404 (anti-enumeration)
- Storage failure non-fatal (both endpoints)
- Empty KB returns 0
- Non-existent document 404
- Deletable statuses: pending, completed, failed

Coverage is adequate for the scope of this ticket.

---

## Files Reviewed

- `projects/kinetic/packages/api/app/api/routes/documents.py` (lines 409–486)
- `projects/kinetic/packages/api/app/api/routes/kb_management.py` (lines 179–263)
- `projects/kinetic/packages/api/app/core/constants.py`
- `projects/kinetic/packages/api/tests/test_document_delete.py`
