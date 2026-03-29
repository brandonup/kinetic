# Code Review R2 — KIN-408: Fix KB Ingestion Failures

**Date:** 2026-03-28
**Reviewer:** Gilfoyle
**Verdict:** Architecture approved

---

## R1 Issue Resolution

| R1 ID | Issue | Status |
|---|---|---|
| I1 | No test for orphaned row cleanup path | Fixed — `TestOrphanedRowCleanup` added at `test_ingestion.py:377` |
| M1 | Hard-coded `"token limit"` string match | Acknowledged — acceptable for MVP per KIN-407 diagnosis |

---

## Files Reviewed (R2 delta)

- `packages/api/tests/test_ingestion.py` (lines 377–425) — new `TestOrphanedRowCleanup` class

---

## New Issues Found in R2

### Critical

None.

### Important

None.

### Minor

None.

---

## Assessment

**Ready to merge.** The I1 test correctly exercises the orphaned-row cleanup path: mocks `fetch_user_key_async` to raise `RuntimeError`, verifies `doc_mock.delete.assert_called_once()`, and catches the propagated exception via `pytest.raises`. The `_table` dispatcher mock is clean — routes `knowledge_bases` and `knowledge_base_documents` calls to separate mocks so the delete assertion is isolated.

All three KIN-408 fixes are architecturally sound with full test coverage.

— Gilfoyle
