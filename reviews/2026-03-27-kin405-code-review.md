# Code Review — KIN-405: KB Deletion Not Removing Data from DB

**Date:** 2026-03-27
**Reviewer:** Gilfoyle
**Verdict:** Architecture approved

---

## Files Reviewed

- `packages/api/app/api/routes/documents.py` (lines 432–508)
- `packages/api/app/api/routes/kb_management.py` (lines 179–434)
- `packages/api/tests/test_document_delete.py`
- `packages/api/tests/test_kb_management.py` (lines 44–82, 207–222)

---

## Strengths

**Correct core fix.** Switching from `.update({"deleted_at": "now()"})` to `.delete().eq(...).execute()` directly satisfies the acceptance criteria. `ON DELETE CASCADE` on `knowledge_base_chunks.document_id` handles chunk removal atomically with zero application-layer orchestration. This is the right approach.

**Ingestion guard preserved.** The 409 guard against deleting actively-ingesting documents is correctly retained across all three endpoints. Deleting a document mid-ingest without this guard would leave orphaned workers writing to a vacuum.

**Lambda closure capture in storage loop is correct.** The `lambda p=path: ...` pattern in the storage cleanup loops correctly captures the loop variable by value, avoiding the classic late-binding closure bug. This was done right.

**Storage cleanup is appropriately non-fatal.** Wrapping storage removal in try/except with a warning log is the correct posture — storage cleanup will get a proper background job later, and a failed storage call should never roll back a completed DB delete.

**`delete_all_documents` race condition detection.** Logging and raising 500 when `deleted_count == 0` after a successful pre-flight fetch catches the concurrent-deletion race. Good defensive programming.

**Test coverage is adequate for the happy path.** 22 affected tests cover the core flows: successful delete, 409 active ingestion, 404 not found, auth enforcement, and storage failure resilience.

---

## Issues

### Critical (Must Fix)

None.

---

### Important (Should Fix)

**I1 — `delete_document`: stale `.is_("deleted_at", "null")` filter on fetch**
File: `packages/api/app/api/routes/documents.py`, line 455

The fetch still filters `.is_("deleted_at", "null")`. After this migration to hard-delete, rows are physically removed — `deleted_at` is never set, so no row will ever have a non-null `deleted_at` from this code path. The filter is harmless today (it just adds a redundant AND clause) but it's misleading: it implies a soft-delete model is still in play. As the system grows, a future developer reading this will be confused about whether the table still has soft-deleted rows. If `deleted_at` is being fully abandoned, the column should either be dropped in a migration or the filter removed from all reads.

Recommendation: Remove the `.is_("deleted_at", "null")` filter from the fetch. If `deleted_at` is still needed for other purposes in the schema (audit history, other code paths), add a comment explaining why the fetch guards on it even though deletions are now hard.

**I2 — `delete_all_documents`: same stale `deleted_at` filter on pre-flight fetch**
File: `packages/api/app/api/routes/kb_management.py`, line 206

Same issue as I1. The pre-flight document fetch filters `.is_("deleted_at", "null")`. This creates a subtle inconsistency: the hard-delete at line 236 deletes `.eq("knowledge_base_id", ...)` with no `deleted_at` filter, which correctly deletes all rows. But the preceding count used for `deleted_count` (and for the active-ingestion check) only counts non-null-`deleted_at` rows. If any rows exist with a non-null `deleted_at` from a previous code version or data migration, they'd be hard-deleted by the `.delete()` call but not counted in `deleted_count` and not checked for active ingestion status.

This is a data consistency gap. The pre-flight fetch and the delete operation must scope identically. Either both filter on `deleted_at` or neither does.

**I3 — `delete_folder` (no reassign): no ingestion guard before deleting documents**
File: `packages/api/app/api/routes/kb_management.py`, lines 413–423

When `reassign_to` is None, the endpoint hard-deletes all documents in the folder with no check for active ingestion status. `delete_document` and `delete_all_documents` both guard against this — a document being actively ingested when deleted leaves a running worker with no DB row to write results to. `delete_folder` is now the odd one out. This is an inconsistent behavior across the deletion surface and will produce a confusing failure mode in production when a user deletes a folder while a document is ingesting.

The fix mirrors what `delete_all_documents` does: fetch the documents in the folder, check for `ACTIVE_INGESTION_STATUSES`, and return 409 if any are active.

**I4 — `test_delete_folder_without_reassign_deletes_documents`: test body does not assert the delete was actually called**
File: `packages/api/tests/test_kb_management.py`, lines 209–222

The test asserts `resp.status_code == 200` and response body fields, but does not assert that `mock_client.table("knowledge_base_documents").delete` was actually called. The test would pass even if the code path branched into the reassignment path instead of the delete path, as long as the response structure matched. Given that the entire purpose of this test is to verify the new hard-delete behavior is exercised, the absence of a `.assert_called()` check on the delete mock is a coverage gap.

---

### Minor (Nice to Have)

**M1 — Stale docstring in `test_successful_delete_all`**
File: `packages/api/tests/test_document_delete.py`, line 201

The docstring reads "returns 200 with count of soft-deleted documents" — should be "hard-deleted documents".

**M2 — `test_successful_delete` docstring mislabeled**
File: `packages/api/tests/test_document_delete.py`, line 117

Docstring reads "Soft-delete returns 200" — this endpoint is now a hard-delete. Minor, but it's the first test a future developer reads.

---

## Summary

The core fix is correct and clean. Two Important issues need resolution before this is production-solid:

- I2 is the highest-priority: the scope mismatch between the pre-flight fetch and the hard-delete in `delete_all_documents` is a data integrity gap that will silently produce wrong `deleted_count` values and skip ingestion guards for any rows carrying a non-null `deleted_at` from the prior soft-delete era.
- I3 introduces a behavioral inconsistency across the deletion surface — folder deletion without reassignment has no ingestion guard, where every other deletion path does.
- I1 is housekeeping but flags a misleading artifact of the migration.
- I4 is a test coverage gap on the specific behavior this ticket was meant to verify.

---

## Assessment

**Ready to merge?** With fixes (I2, I3 are blockers; I1 and I4 should ship in the same pass).

**Reasoning:** The core hard-delete logic is sound and the cascade behavior will work correctly, but the scope mismatch in `delete_all_documents` (I2) and the missing ingestion guard in `delete_folder` (I3) are production-correctness gaps that should not go to main in this state.
