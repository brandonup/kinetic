# KIN-408 Code Review — KB Ingestion Reliability Fixes

**Date:** 2026-03-28
**Reviewer:** Gilfoyle
**Ticket:** KIN-408 — KB ingestion reliability (RC-2 secondary, RC-3, RC-4)
**Round:** 1

---

## Summary

Three targeted fixes to KB ingestion reliability based on the KIN-407 diagnosis. All three root causes are correctly addressed. The implementation is clean, the fixes are appropriately minimal, and the test coverage is solid across the new paths. One Important finding (orphaned row cleanup missing a test) and one Minor finding (hard-coded string match). No Criticals.

---

## Fix 1 — `background.py` — Stale cleanup preserves existing error_message (RC-3)

**File:** `packages/api/app/services/background.py`

### What was done

`cleanup_stale_jobs` now issues two updates per status instead of one:
1. Docs with `error_message IS NULL`: sets `status`, `error_stage`, and `error_message` (stale message).
2. Docs with `error_message IS NOT NULL`: sets only `status` and `error_stage`, preserving the real error.

### Assessment

Correct. The split-update approach is the right implementation of the RC-3 requirement. The use of `.is_("error_message", "null")` and `.not_.is_("error_message", "null")` is idiomatic for the Supabase Python client.

Count aggregation (`len(r_new.data) + len(r_preserve.data)`) correctly reflects total docs cleaned rather than just the null-message branch.

No issues found in this fix.

---

## Fix 2 — `documents.py` + `models.ts` + `DocumentRow.tsx` — `is_retryable` field (RC-4)

**Files:**
- `packages/api/app/api/routes/documents.py`
- `packages/web/lib/types/models.ts`
- `packages/web/components/DocumentRow.tsx`

### What was done

- `DocumentStatusResponse` Pydantic model gains `is_retryable: bool = True`.
- `get_document_status` computes: `is_retryable = "token limit" not in (error_message or "").lower()`.
- TypeScript `DocumentStatusResponse` interface gains `is_retryable: boolean`.
- `DocumentRow.tsx` retry button renders only when `status === "failed" && isRetryable`.
- `isRetryable = data?.is_retryable ?? true` (defaults true before data loads — correct, avoids hiding the button while polling).

### Assessment

Correct end-to-end. The server-side approach (field on `DocumentStatusResponse`) is the better choice — the frontend doesn't need to know the business rule and the rule is enforceable without client-side string matching. Field naming is consistent between backend (`is_retryable`) and frontend (`is_retryable` in the interface, `isRetryable` as the local camelCase variable — correct mapping per conventions).

---

## Fix 3 — `documents.py` upload route — orphaned row cleanup (RC-2 secondary)

**File:** `packages/api/app/api/routes/documents.py` (lines 164–208)

### What was done

After document row insertion, the remaining logic (key fetch + dispatch) is wrapped in `try/except`. On non-`HTTPException` exceptions: deletes the orphaned pending row, logs both the original error and any cleanup failure, then re-raises the original exception.

The `except HTTPException: raise` guard correctly passes through HTTP exceptions (e.g., the 400 for missing OpenAI key) without triggering cleanup — those exceptions are intentional API responses, not unexpected failures.

### Assessment

Logic is correct. The re-raise preserves the original exception rather than swallowing it, which is consistent with conventions (`§ Error Handling`). Nested `try/except` for the cleanup itself is correct — a cleanup failure should not replace the original error.

---

## Issues

### Important

**I1 — No test for the orphaned row cleanup path (Fix 3)**

**File:** `packages/api/tests/test_ingestion.py` (or a new `test_upload.py`)

There is no test that exercises the `except Exception` branch in the upload route that triggers orphaned row deletion. The happy path (dispatch succeeds) and file-too-large path (pre-insert) are covered, but the "dispatch throws unexpected exception → delete orphan" path is not. This is new error-handling code that changes observable state (DB delete) — it needs a test.

**Required test scenario:**
- Insert succeeds, storage upload succeeds, `fetch_user_key_async` raises an unexpected `RuntimeError`.
- Verify: (a) `supabase.table("knowledge_base_documents").delete()` is called with the correct document ID, (b) the route returns 500 (not 200, not 400).

**Fix:** Add one test case to `test_ingestion.py` covering this path.

---

### Minor

**M1 — Hard-coded string `"token limit"` in `get_document_status`**

**File:** `packages/api/app/api/routes/documents.py`, line 249

```python
is_retryable = "token limit" not in (error_message or "").lower()
```

This couples the retryability check to the exact string written by the ingestion pipeline in KIN-407. If the error message wording changes (e.g., "exceeds token limit" → "token count exceeded"), `is_retryable` silently regresses to `True` for non-retryable failures. The KIN-407 diagnosis recommended this approach explicitly, so it is acceptable for MVP. Worth a comment noting the dependency.

**No fix required before merge.** Note the coupling in a follow-up.

---

## Test Coverage Assessment

### `test_background_jobs.py`

Five tests covering RC-3:
- `test_stale_pending_docs_are_marked_failed` — happy path with both update branches.
- `test_no_stale_docs_returns_zero` — returns 0 when nothing is stale.
- `test_cleanup_continues_on_individual_status_failure` — per-status exception isolation.
- `test_stale_error_message_includes_state_name` — correct error message content.
- `test_stale_cleanup_preserves_existing_error_message` — **directly validates the RC-3 fix**: preserve-path updates contain no `error_message` key.

Coverage is thorough. The last test is the most important and correctly asserts that the second update dict does not include `error_message`.

### `test_document_status.py`

Five tests covering RC-4:
- `test_returns_status_for_owned_document` — asserts `is_retryable=True` on non-failed doc.
- `test_returns_404_when_document_deleted` — soft-delete / missing doc.
- `test_returns_403_when_document_belongs_to_other_user` — access control.
- `test_returns_status_with_error_fields_for_failed_doc` — retryable failure returns `is_retryable=True`.
- `test_token_limit_failure_returns_is_retryable_false` — **directly validates the RC-4 fix**.

Token limit test uses a realistic error message (`"Document exceeds token limit: 3,320,528 > 1,000,000"`) which correctly exercises the `.lower()` contains check.

### Gap

No test for the Fix 3 orphaned row cleanup path. See I1 above.

---

## Verdict

**Changes requested.** 1 Important.

Fix I1 (test for orphaned row cleanup path), then re-submit.
