# Code Review: KIN-336 — Document Ingestion Retry UX + AI Auto-Suggest Tags

**Reviewer:** Gilfoyle
**Date:** 2026-03-23
**Round:** 2
**Verdict:** CHANGES REQUESTED

---

## Files Reviewed

- `packages/api/app/services/ingestion/tag_suggester.py` (NEW)
- `packages/api/app/services/ingestion/pipeline.py` (MODIFIED)
- `packages/api/app/api/routes/documents.py` (MODIFIED)
- `packages/api/tests/test_ingestion.py` (MODIFIED — 18 new tests, 26 total)

---

## R1 Fix Verification

### C1 — FIXED

`documents.py` lines 131–155: storage upload and `storage_uri` update are now split into two independent guarded blocks. `storage_ok` flag gates the update. If upload fails, `storage_uri` update is skipped. Both failures log a warning. Correct.

### I1 — FIXED

`pipeline.py` lines 166–187: `index_chunks` is now wrapped in a `try/except`. On failure it calls `_update_document` with `status="failed"`, `error_stage="embedding"`, truncated `error_message`, and `retry_count`, then re-raises. The `error_stage="embedding"` value is intentional (comment explains indexing has no enum value). Retry logic routes to `start_stage="chunking"` for any non-extracting `error_stage`, so this is functionally correct. Fix accepted.

### I2 — FIXED

`TestRetryEndpoint.test_retry_fallback_to_full_extraction_when_text_unavailable` (line 691) and `test_retry_500_when_no_storage_available` (line 712) are present and test both fallback branches. Correct.

---

## New Findings

### I3 — `error-swallow`: Status reset write in retry endpoint has no error handler

**Severity:** Important

**File:** `packages/api/app/api/routes/documents.py`, lines 348–360

**Problem:**

```python
# Reset document status
await loop.run_in_executor(
    None,
    lambda: supabase.table("knowledge_base_documents")
    .update({
        "status": "pending",
        "error_stage": None,
        "error_message": None,
        "retry_count": 0,
    })
    .eq("id", str(document_id))
    .execute(),
)
```

This write has no `try/except` and no logging. At this point in the function, the chunk cleanup has already run (partial rows deleted) and file/text bytes have been downloaded from Storage. If this write fails, the exception propagates as a generic 500 with no context in the logs — no document ID, no indication of what operation failed. The document is left in a corrupted state: chunks deleted but status still `failed`, no error context. Downstream retries will succeed on the 409 guard read but will restart from an inconsistent base.

This is not a silent swallow — it raises — but it is a bare write failure with no logging, which violates the "log before catching" convention even though it's not being caught. Per conventions: write operations should at minimum log before propagation so an operator can diagnose the failure.

**Fix:**

```python
try:
    await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_base_documents")
        .update({
            "status": "pending",
            "error_stage": None,
            "error_message": None,
            "retry_count": 0,
        })
        .eq("id", str(document_id))
        .execute(),
    )
except Exception as exc:
    logger.error(
        "Failed to reset document status for retry (document %s): %s",
        document_id,
        exc,
    )
    raise HTTPException(
        status_code=500,
        detail="Failed to reset document status. Please try again.",
    )
```

This surfaces the error explicitly (fast-fail before dispatch), gives the operator a document ID in logs, and returns a clean 500 rather than propagating an internal exception.

---

## No New Test Required

The fix for I3 is a straightforward error wrapper on an existing write path. The retry endpoint tests already cover the success path (line 638). A test for this failure mode would require mocking the update call mid-sequence (after chunk delete, before dispatch) — worthwhile but not a blocker here given the low operational frequency of Supabase write failures.

---

## Remaining Minor Findings (from R1 — not blocks)

- **M1** (prompt inline in service module): Still present. Accepted as pre-existing pattern; tracked as technical debt.
- **M2** (`get_event_loop()` in `_run()`): Still present. Pre-existing pattern across the test suite. Not a block.

---

## What's Good

All three R1 Critical/Important issues are resolved correctly. The overall architecture of the feature is sound:

- Async hygiene is correct throughout — every Supabase call in async context uses `run_in_executor` with `get_running_loop()`.
- Non-fatal tag suggester contract is correctly implemented and tested (5 unit tests + 2 integration tests).
- Stage resumption (`run_ingestion_from_stage`) correctly re-runs enrichment on chunking-resume path.
- Access control is solid — both endpoints verify KB ownership via `kb.user_id == current_user.user_id`.
- 26 tests cover primary paths, failure modes, and the two new fallback branches from I2.

---

## Defect Summary

| # | Severity | Category | Description |
|---|---|---|---|
| I3 | Important | `error-swallow` | Status reset write in retry endpoint has no try/except or logging; bare failure leaves document in corrupted state with no diagnostics |
