# Code Review — KIN-338: Background job hardening
**Date:** 2026-03-24
**Reviewer:** Gilfoyle
**Verdict:** CHANGES_REQUESTED
**Round:** 1

---

## Files Reviewed

- `packages/api/app/services/background.py` (MODIFIED)
- `packages/api/app/main.py` (MODIFIED)
- `packages/api/app/api/routes/documents.py` (MODIFIED)
- `packages/api/tests/test_background_jobs.py` (NEW)

---

## Schema Cross-Reference

All table and column references verified against `docs/db-schema-spec.md`.

| Reference | Location | Schema Match |
|---|---|---|
| `knowledge_base_documents` | background.py, documents.py | §12 — confirmed |
| `status`, `error_stage`, `error_message`, `updated_at`, `deleted_at` | background.py | §12 — all confirmed |
| `storage_uri`, `retry_count`, `tags`, `title`, `file_type` | documents.py | §12 — all confirmed |
| `knowledge_bases` → `project_id`, `agent_definition_id`, `user_id` | documents.py | §10 — all confirmed |
| `knowledge_base_chunks` DELETE by `document_id` | documents.py | §13 — confirmed |

No schema mismatches found.

---

## Findings

### C1 — Critical | `documents.py` lines 337–377 | Chunk cleanup before atomic lock (correctness bug)

**File:** `packages/api/app/api/routes/documents.py`
**Lines:** 337–377

The partial-chunk cleanup runs before the atomic status reset. Two concurrent retry requests will both read `status='failed'` and pass the non-atomic status guard at line 255. Request A deletes all chunks (line 337–346), then Request B hits the atomic update and gets 0 rows (correctly returned 409), but Request A also proceeds past the atomic gate and dispatches the pipeline. The chunks Request A is about to produce are fine — but if Request B deleted them first, the pipeline dispatched by A runs on a document with no existing chunks (idempotent) which is actually okay for a fresh re-run. The real danger is the reverse ordering: Request B may delete chunks that Request A is currently writing mid-pipeline (B arrives late but passes the first status check before A's pipeline has updated status to `processing`).

The fix is to invert the order: perform the atomic status reset first, and only if it succeeds (returns a row) proceed to chunk cleanup and pipeline dispatch. Chunk cleanup is idempotent — it is safe to do after claiming the lock.

**Fix:**
```python
# Step 1: Atomic claim — must come FIRST
reset_result = await loop.run_in_executor(
    None,
    lambda: supabase.table("knowledge_base_documents")
    .update({"status": "pending", "error_stage": None, "error_message": None, "retry_count": 0})
    .eq("id", str(document_id))
    .eq("status", "failed")
    .execute(),
)
if not reset_result.data:
    raise HTTPException(status_code=409, detail="Document retry already in progress.")

# Step 2: Cleanup only after we hold the lock
try:
    await loop.run_in_executor(
        None,
        lambda: supabase.table("knowledge_base_chunks")
        .delete()
        .eq("document_id", str(document_id))
        .execute(),
    )
except Exception as exc:
    logger.warning("Chunk cleanup failed (non-fatal): %s", exc)

# Step 3: Dispatch
dispatcher.dispatch(run_ingestion_from_stage, ...)
```

---

### C2 — Critical | `documents.py` lines 254–259 | Status check before ownership check (multi-tenant information leak)

**File:** `packages/api/app/api/routes/documents.py`
**Lines:** 254–259

```python
# Only failed documents can be retried — check before ownership (fast reject)
if doc["status"] != "failed":
    raise HTTPException(
        status_code=409,
        detail=f"Document status is '{doc['status']}', not 'failed'. ...",
    )
```

This returns a 409 with the document's current status to the caller before verifying ownership. In a multi-tenant system, an authenticated user who knows (or guesses) a valid `document_id` belonging to another user can determine that document's ingestion state. The 404 from the initial `.is_("deleted_at", "null")` filter does not protect against this — the doc is found, then status is leaked before the ownership gate fires.

The comment justifies this as a "fast reject" optimization, but the ownership check is a single indexed Supabase query — not expensive. The security cost outweighs the microsecond gain.

**Fix:** Move the ownership check to immediately after the initial document fetch. Reject on ownership first (403 or 404 per anti-enumeration preference — see MEMORY.md 2026-03-24: MCP uses 404 for cross-tenant denials). Then check status.

```python
# RLS: verify ownership first
kb_check = await loop.run_in_executor(...)
if not kb_check.data or kb_check.data.get("user_id") != current_user.user_id:
    raise HTTPException(status_code=404, detail="Document not found.")

# Then check status
if doc["status"] != "failed":
    raise HTTPException(status_code=409, detail=...)
```

---

### I1 — Important | `test_background_jobs.py` line 26 | Deprecated `get_event_loop()` in test runner

**File:** `packages/api/tests/test_background_jobs.py`
**Line:** 26

```python
def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)
```

`asyncio.get_event_loop()` is deprecated in Python 3.10+ and raises a DeprecationWarning in 3.12. Conventions spec explicitly requires `get_running_loop()` (not `get_event_loop()`) for production async code, and the same standard applies to tests. For test runners, use `asyncio.run(coro)` which creates a fresh event loop per call and is the correct pattern for standalone coroutine execution outside an async context.

**Fix:**
```python
def _run(coro):
    return asyncio.run(coro)
```

---

### I2 — Important | `test_background_jobs.py` lines 124–168 | Fragile mock chain in `TestRetryDedup`

**File:** `packages/api/tests/test_background_jobs.py`
**Lines:** 124–168

The test mocks two separate `.select()` call paths on `mock_sb.table.return_value`:
- Document fetch: `.select(...).eq(id).is_("deleted_at", "null").single().execute()`
- KB ownership check: `.select(...).eq(id).single().execute()`

Both share the same `mock_sb.table.return_value.select.return_value` root. The document fetch mock (line 131) sets `...eq.return_value.is_.return_value.single.return_value.execute.return_value` and the KB check mock (line 144) sets `...eq.return_value.single.return_value.execute.return_value`. These chains diverge at `.eq(...).is_(...)` vs `.eq(...).single(...)`. In practice, `MagicMock` creates separate children for `.is_` and `.single` on the same parent, so these two paths do not collide — but this is an implementation detail of `MagicMock` autospeccing, not an explicit contract.

More critically: the storage `.download()` mock at line 153 returns `b"text content"` for all downloads. The retry path for `error_stage='embedding'` tries to download `extracted.txt` first (line 306–311). If that download succeeds (it will — mock returns `b"text content"`), `start_stage` is set to `"chunking"` and `file_content = None`. The test passes `error_stage='embedding'` but doesn't exercise the fallback path it appears to intend (the chunk cleanup + atomic update path which produces the 409). It works only because the storage mock returns bytes unconditionally, meaning the test accidentally exercises the correct dedup path but is not explicitly testing what it claims to test.

**Fix:** Add separate mock paths for storage download keyed by path argument, or use `side_effect` with a callable that inspects the path. Add a comment explaining the `embedding` → `chunking` fallback path explicitly. Consider a second test for the `extracting` stage path where storage download is unavailable.

---

## What Works Well

- `cleanup_stale_jobs` is correctly structured: per-status isolation with `try/except`, proper `run_in_executor` usage, `get_running_loop()` not `get_event_loop()`, descriptive error messages that include the stuck state name.
- Lifespan event error handling is correct: `logger.warning` + `yield` ensures startup failures are non-fatal. Non-blocking.
- Import placement (`get_supabase` inside `lifespan` body) is an acceptable pattern to avoid circular imports at module load time.
- The atomic dedup concept (`.eq("status", "failed")` in the UPDATE WHERE clause) is architecturally correct. C1 is about ordering, not the mechanism itself.
- All Supabase calls in async context use `run_in_executor` with `get_running_loop()`. No violations.
- Schema references are clean throughout.

---

## Required Before Approval

1. **C1:** Invert order — atomic status reset before chunk cleanup.
2. **C2:** Move ownership check before status check.
3. **I1:** Replace `asyncio.get_event_loop()` with `asyncio.run()`.
4. **I2:** Fix mock chain so KB ownership path is explicitly and correctly mocked.
