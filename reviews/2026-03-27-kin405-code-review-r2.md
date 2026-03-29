# Code Review R2 — KIN-405: KB Deletion Not Removing Data from DB

**Date:** 2026-03-27
**Reviewer:** Gilfoyle
**Verdict:** Architecture approved

---

## R1 Issue Resolution

All 4 Important and 2 Minor issues from R1 are resolved.

| R1 ID | Issue | Status |
|---|---|---|
| I1 | Stale `deleted_at` filter on `delete_document` fetch | Fixed — filter removed |
| I2 | Scope mismatch in `delete_all_documents` (fetch vs delete) | Fixed — both now filter `.is_("deleted_at", "null")`, documented in comment |
| I3 | Missing ingestion guard in `delete_folder` (no reassign) | Fixed — guard added with 409 response, mirrors other delete paths |
| I4 | Test missing `assert_called` on delete mock | Fixed — `doc_delete_mock.assert_called_once()` added |
| M1 | Stale docstring "soft-deleted" in `test_successful_delete_all` | Fixed |
| M2 | Stale docstring "Soft-delete" in `test_successful_delete` | Fixed |

---

## Files Reviewed (R2 delta)

- `packages/api/app/api/routes/documents.py` (lines 432–508)
- `packages/api/app/api/routes/kb_management.py` (lines 179–264, 395–454)
- `packages/api/tests/test_kb_management.py` (lines 212–278)
- `packages/api/tests/test_document_delete.py` (lines 113–128, 197–208)

---

## New Issues Found in R2

### Critical

None.

### Important

None.

### Minor (Non-blocking)

**M1 (new) — Stale comment in `delete_all_documents`**
File: `packages/api/app/api/routes/kb_management.py`, line 225

Comment reads "Collect storage paths before soft-delete" — should say "before hard-delete." Carryover language from the pre-migration code.

**M2 (new) — `delete_folder` guard/delete scope asymmetry**
File: `packages/api/app/api/routes/kb_management.py`, lines 422–441

The ingestion guard fetch filters `.is_("deleted_at", "null")` (line 423), but the hard-delete at line 441 does not include the `deleted_at` filter. This means the delete could remove stale soft-deleted rows that the guard didn't check. Not a functional issue — stale soft-deleted rows won't be actively ingesting — but it's inconsistent with how `delete_all_documents` was aligned per I2 (both fetch and delete have matching `deleted_at` filters there). Non-blocking: the asymmetry is harmless and arguably desirable (cleaning up stale rows).

---

## Assessment

**Ready to merge.** All R1 blockers (I1–I4) are resolved correctly. The two new Minor issues are non-blocking housekeeping — they can be addressed in a follow-up or ignored.

The fix is architecturally sound: hard-delete with `ON DELETE CASCADE` for chunks, ingestion guards on all three delete paths, consistent scope alignment, and adequate test coverage including the new `test_delete_folder_active_doc_returns_409`.
