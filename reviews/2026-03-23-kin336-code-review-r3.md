# Code Review — KIN-336: Document Ingestion Retry UX + AI Auto-Suggest Tags
## Round 3 (Final)
**Reviewer:** Gilfoyle
**Date:** 2026-03-23
**Files reviewed:**
- `packages/api/app/services/ingestion/tag_suggester.py` (NEW)
- `packages/api/app/services/ingestion/pipeline.py` (MODIFIED)
- `packages/api/app/api/routes/documents.py` (MODIFIED)
- `packages/api/tests/test_ingestion.py` (MODIFIED — 26 total tests)

---

## I3 Fix Verification

**Finding:** I3 — status reset write in retry endpoint needed `try/except` + `logger.error` + `HTTPException(500)`.

**Applied correctly.** `documents.py` lines 348–367:
```python
# Reset document status — failure here is fatal (chunks already cleaned up)
try:
    await loop.run_in_executor(...)
except Exception as exc:
    logger.error("Failed to reset document %s status for retry: %s", document_id, exc)
    raise HTTPException(
        status_code=500,
        detail="Failed to reset document status. Please try again.",
    )
```
All three required elements present: `try/except`, `logger.error`, `HTTPException(500)`. The comment correctly characterizes the failure as fatal (chunks have already been deleted). Fix is correct.

---

## Prior Findings Status

| ID | Severity | Description | Status |
|---|---|---|---|
| C1 | Critical | Storage upload + storage_uri update split into separate guarded blocks | ✓ Fixed |
| I1 | Important | Indexer failure now sets `status=failed` with `error_stage` + `error_message` | ✓ Fixed |
| I2 | Important | Two new tests for retry fallback branches | ✓ Fixed |
| I3 | Important | Status reset write in retry endpoint has `try/except` + `logger.error` + `HTTPException(500)` | ✓ Fixed |

---

## Final Pass

### tag_suggester.py
Clean. `suggest_tags` is synchronous (called via `run_in_executor` in pipeline), returns empty list on any failure. Snippet truncation at 8000 chars is reasonable. `max_tokens=100` with a `timeout=15` kwarg passed to `call_llm` — acceptable. No issues.

### pipeline.py
- `_run_enrichment` wraps both `generate_summary` and `suggest_tags` — neither failure propagates to the pipeline. Tags stored via `_update_document` only when non-empty. Correct.
- `_run_pipeline_stages` — indexer failure path (lines 167–187) now sets `status="failed"`, `error_stage="embedding"`, `error_message`. The comment noting "embedding is the closest available status enum value" is honest about the approximation. Acceptable.
- `run_ingestion_from_stage` — resuming from `chunking` re-runs enrichment before `_run_pipeline_stages`. This is correct: tags may have failed on the original run, so re-running them on retry is good behavior.
- No swallowed errors on write paths. `_update_document` propagates exceptions correctly.

### documents.py
- Upload endpoint: storage upload and `storage_uri` update are in separate guarded blocks (lines 131–155). Both failures log at `WARNING` as non-fatal. Pipeline still dispatched regardless. Correct.
- Retry endpoint: all three failure paths (storage download for extracting, storage download for fallback file, status reset) have proper error handling with distinct log levels (`error` for fatal, `warning` for non-fatal).
- One minor observation (not a blocker): the inner fallback `except Exception:` at line 326 has no log statement — it just re-raises. This is intentional (the outer `except` at line 294 already logged the first storage failure), so the re-raise without a second log is fine.
- Ownership check pattern (KB → `user_id`) is consistent across upload, status GET, and retry POST.

### test_ingestion.py
- 26 tests across 9 classes. No duplicate class names.
- I2 tests are present: `test_retry_fallback_to_full_extraction_when_text_unavailable` and `test_retry_500_when_no_storage_available` (lines 691–725).
- `TestRetryEndpoint` covers the full state machine: reset, 409 (non-failed), 404 (not found), 403 (wrong user), fallback extraction, and no-storage 500.
- Tag tests cover: happy path, failure → empty list, disabled, cap-at-5, empty response.
- Pipeline integration tests verify tags are stored and that tag failure does not block ingestion.
- Stage resumption tests verify extraction is skipped when `start_stage="chunking"` and that full pipeline runs when `start_stage="extracting"`.

No gaps found.

---

## Verdict

**APPROVED.** All four prior findings (1 Critical, 3 Important) correctly resolved. No new issues found. Code is production-ready.
