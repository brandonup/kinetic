# Code Review: KIN-336 — Document Ingestion Retry UX + AI Auto-Suggest Tags

**Reviewer:** Gilfoyle
**Date:** 2026-03-24
**Round:** 1
**Verdict:** CHANGES REQUESTED

---

## Files Reviewed

- `packages/api/app/services/ingestion/tag_suggester.py` (NEW)
- `packages/api/app/services/ingestion/pipeline.py` (MODIFIED)
- `packages/api/app/api/routes/documents.py` (MODIFIED)
- `packages/api/tests/test_ingestion.py` (MODIFIED — 16 new tests)

---

## Summary

Solid structural approach. Stage-resume design is clean, async handling is mostly correct, and the tag suggester's non-fatal contract is sensible. Three issues block approval: one Critical silent swallow on a write operation in the storage/update path at upload, one Important missing test for a branching fallback path in the retry endpoint, and one Important schema cross-reference gap (`indexing` stage name not in the `document_status` enum).

---

## Critical Findings

### C1 — `error-swallow`: Silent swallow on Storage upload + `storage_uri` update in upload endpoint

**File:** `packages/api/app/api/routes/documents.py`, lines 133–147

**Problem:** The block that uploads the raw file to Supabase Storage and then updates `storage_uri` on the document row is wrapped in a single `try/except Exception` that logs a warning and continues silently. If the Storage upload fails, the file is not available for retry. If the `storage_uri` update fails, the document row has no reference to the file. In both cases ingestion starts anyway with no record that retry will be broken. The comment says "non-fatal" — but the consequence of this silent swallow is that the retry endpoint will return HTTP 500 with "File not available for retry" and the user cannot recover without a re-upload. That outcome is not "non-fatal" from the user's perspective; it silently degrades the retry UX the ticket was designed to deliver.

**Fix:** The two operations should be separated and handled individually. Storage upload failure is acceptable to swallow (with a warning log) since ingestion can still proceed from `file_content` in memory. But the `storage_uri` update failure must also log. More importantly: if the Storage upload failed, the code must **not** attempt to update `storage_uri` at all (currently it unconditionally calls the update even when the upload raised). Split the try/except:

```python
storage_uploaded = False
try:
    await loop.run_in_executor(
        None,
        lambda: supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET)
        .upload(storage_path, content, {"content-type": content_type}),
    )
    storage_uploaded = True
except Exception as exc:
    logger.warning("Failed to store file in Storage (retry will require re-upload): %s", exc)

if storage_uploaded:
    try:
        await loop.run_in_executor(
            None,
            lambda: supabase.table("knowledge_base_documents")
            .update({"storage_uri": storage_path})
            .eq("id", str(document_id))
            .execute(),
        )
    except Exception as exc:
        logger.warning("Failed to update storage_uri on document row: %s", exc)
```

The retry endpoint already handles `storage_uri=None` gracefully (raises HTTP 500 with a clear message), so this fix makes the failure mode explicit without blocking ingestion.

---

## Important Findings

### I1 — `spec-gap`: `indexing` is not a valid `document_status` enum value

**File:** `packages/api/app/services/ingestion/pipeline.py`, line 175 (comment: "Index chunks (outside retry — indexer raises on failure)")

**Problem:** The `index_chunks` call in `_run_pipeline_stages` is intentionally placed outside the `_run_stage` retry wrapper, meaning if it fails, it raises without setting `status='indexing'`. That is fine. But the docstring for `run_ingestion` (lines 204–207) lists stages as `extracting → chunking → embedding → indexing → completed`. The `document_status` enum in `db-schema-spec.md §12` defines: `pending`, `extracting`, `chunking`, `embedding`, `completed`, `failed`. There is no `indexing` value. The docstring is misleading and implies a status transition that cannot be stored. If the indexer fails, the document status will be whatever the last successful `_run_stage` call left it at (i.e., `embedding`), not `failed`, because the indexer is outside the retry wrapper and raises without the failure bookkeeping.

**Fix (two parts):**
1. Remove `indexing` from the docstring stage list. The actual status sequence is `extracting → chunking → embedding → completed` (or `failed`).
2. Wrap `index_chunks` in the `_run_stage` wrapper, or add explicit `failed` bookkeeping on exception:

```python
try:
    await index_chunks(...)
except Exception as exc:
    await _update_document(
        supabase, document_id,
        status="failed",
        error_stage="embedding",  # last known stage
        error_message=str(exc)[:2000],
        retry_count=retry_count,
    )
    raise
```

Without this, an indexer failure leaves the document stuck in `embedding` status with no `error_stage` or `error_message`, and the retry endpoint reads `error_stage` to decide which branch to take. A stuck `embedding` status will hit the chunking resume path correctly, but the missing `error_message` means the user sees no failure reason in the GET status endpoint.

### I2 — `test-missing`: No test for the Storage fallback path in retry endpoint

**File:** `packages/api/tests/test_ingestion.py`, `TestRetryEndpoint`

**Problem:** The retry endpoint has a multi-branch fallback in the `else` block (lines 293–326 in documents.py): if the document failed at chunking/embedding, it tries to download extracted text from Storage; if that fails, it falls back to downloading the original file and running from `extracting`. This fallback path is not tested. `_mock_supabase_for_retry` hardcodes a successful Storage download. There is no test that exercises: (a) extracted text download fails → fallback to original file, or (b) both downloads fail → HTTP 500. These are non-trivial branches with their own exception handling.

**Fix:** Add two tests to `TestRetryEndpoint`:
- `test_retry_falls_back_to_full_extraction_when_text_unavailable`: Storage download for `extracted.txt` raises, original file download succeeds → response 200, `message` contains "Retry initiated from extracting".
- `test_retry_returns_500_when_no_file_available`: Storage download for `extracted.txt` raises, `storage_uri` is None → response 500.

---

## Minor Findings

### M1 — Prompt not version-controlled / not in prompts module

**File:** `packages/api/app/services/ingestion/tag_suggester.py`, line 26

**Per conventions.md:** "Prompts are code. Version-control them. No hardcoded prompts in application logic — use a prompts module or config file. Every prompt gets an ID and version."

`_TAG_PROMPT` is hardcoded inline in the service module. This is consistent with how `generate_summary` presumably works (not reviewed here), so this may be a pre-existing pattern — flag as technical debt rather than a blocker. Track in MEMORY.md, do not block on this review round.

### M2 — `asyncio.get_event_loop()` in test helper `_run()`

**File:** `packages/api/tests/test_ingestion.py`, line 45

```python
def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)
```

`get_event_loop()` is deprecated in Python 3.10+ and raises a deprecation warning in 3.12. Tests should use `asyncio.run(coro)` instead. This is a pre-existing pattern in the test suite (carried from prior tickets), so do not block — but fix alongside these changes since the file is being touched. No new tests should use `_run()` with `get_event_loop()`.

---

## What's Good

- **Async hygiene is correct** throughout the new code. Every Supabase call in async context uses `run_in_executor` with `get_running_loop()`. No violations.
- **Schema cross-reference:** `tags` column is `text[]` per §12. Implementation writes `List[str]` — correct. `storage_uri` column exists in §12. `retry_count`, `error_stage`, `error_message` all present and correctly typed.
- **Tag suggester design:** Non-fatal contract is correct. Fail-open on read-path tag suggestion is explicitly documented with a comment. `call_llm` wrapped in try/except with a warning log before returning `[]` — meets the "log before catching" convention.
- **Access control:** Both `GET /{document_id}` and `POST /{document_id}/retry` verify ownership through the KB chain (`kb.user_id == current_user.user_id`). The upload endpoint does the same. No ACL leak.
- **Retry endpoint correctness:** Status=`failed` guard (409 on non-failed), ownership check before any state mutation, chunk cleanup before re-dispatch, status reset to `pending` — all correct.
- **Stage resumption logic:** `run_ingestion_from_stage` routes cleanly between full re-extraction and chunking-resume. Token recount from `extracted_text` before passing to `_run_pipeline_stages` is correct.
- **Test coverage:** 16 tests cover the primary happy paths and main failure modes well. Missing branches (I2) are the only gap.

---

## Schema Cross-Reference (§12)

| Field used in code | In §12? | Match? |
|---|---|---|
| `knowledge_base_id` | Yes | ✓ |
| `title` | Yes | ✓ |
| `file_type` | Yes | ✓ |
| `file_size_bytes` | Yes | ✓ |
| `status` (document_status enum) | Yes | ✓ (but see I1 re: `indexing` in docstring) |
| `retry_count` | Yes | ✓ |
| `storage_uri` | Yes | ✓ |
| `token_count` | Yes | ✓ |
| `summary` | Yes | ✓ |
| `tags` (text[]) | Yes | ✓ |
| `error_stage` | Yes | ✓ |
| `error_message` | Yes | ✓ |
| `deleted_at` (soft-delete filter) | Yes | ✓ |

---

## Defect Summary

| # | Severity | Category | Description |
|---|---|---|---|
| C1 | Critical | `error-swallow` | Storage upload and `storage_uri` update batched in one swallowed try/except; upload failure silently leaves document unretriable |
| I1 | Important | `spec-gap` | `indexing` stage in docstring doesn't exist in `document_status` enum; indexer failure outside retry wrapper leaves document in undefined state without `error_stage` |
| I2 | Important | `test-missing` | No tests for retry Storage fallback paths (extracted text unavailable → full re-extraction, both unavailable → 500) |
| M1 | Minor | `other` | Tag prompt inline in service module, not in prompts module per convention |
| M2 | Minor | `other` | `_run()` helper uses deprecated `get_event_loop()` |
