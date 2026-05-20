# KIN-407 — KB Ingestion Failure Diagnosis

**Date:** 2026-03-28
**Author:** Gilfoyle
**Status:** Complete — handed off to Dinesh (KIN-408)

---

## Failure Inventory

From the `knowledge_base_documents` table observed by Brandon:

| Status | Error Stage | Error Message | Retry Count | Root Cause |
|---|---|---|---|---|
| failed | pending | Stale job timeout | 0 | RC-2: BackgroundTask dropped on server restart |
| failed | pending | Stale job timeout | 0 | RC-2: BackgroundTask dropped on server restart |
| failed | pending | Stale job timeout | 0 | RC-2: BackgroundTask dropped on server restart |
| failed | extracting | Document exceeds token limit: 3,320,528 > 1,000,000 | 0 | RC-5: File too large — correct behavior |
| failed | extracting | Stale job timeout | 3 | RC-3: Real error overwritten by stale cleanup |
| failed | embedding | Stale job timeout | 0 | RC-2: BackgroundTask dropped on server restart |
| completed | — | — | — | OK |
| completed | — | — | — | OK |
| pending | — | — | — | In flight or stuck |

**All rows: `storage_uri` = NULL → RC-1**

---

## Root Cause Analysis

### RC-1 — Critical: Supabase Storage bucket `"uploads"` not provisioned

**Evidence:** `storage_uri` is NULL on all document rows. The upload route sets `storage_uri` only when `supabase.storage.from_("uploads").upload(...)` succeeds. Since all rows show NULL, every storage upload is silently failing (caught, logged as WARNING, non-fatal).

**Why this matters:**
- Retry is broken for all failed documents. The retry endpoint checks `storage_uri` when `error_stage == "extracting"`. With NULL, it returns HTTP 500: "File not available for retry." Users see a retry button that always fails.
- `_store_extracted_text()` in the pipeline is also failing silently for the same reason — stage-resume retry (chunking path) has no extracted text to fall back to.

**Root cause:** The `"uploads"` bucket does not appear to have been created in the Supabase project. The bucket name is hardcoded in `config.py` as `SUPABASE_STORAGE_BUCKET = "uploads"` with no migration or setup script to create it. Supabase Storage buckets must be created manually in the Dashboard.

**Fix (deployment, not code):** Brandon creates the `"uploads"` bucket in Supabase Dashboard → Storage → New bucket. Set to private. Verify the service-role key (used by the backend) has storage insert/select permissions. After creating the bucket, new uploads will populate `storage_uri`, and retry will work.

---

### RC-2 — High: FastAPI BackgroundTasks are non-durable — tasks dropped on server restart

**Evidence:** 3 documents and 1 embedding job stuck in processing states with `retry_count=0` — the background task either never started or was abandoned mid-execution. The `cleanup_stale_jobs` at startup (correctly) marked them failed.

**Root cause:** FastAPI `BackgroundTasks` are in-process and ephemeral. If the dev server restarted (e.g., uvicorn hot reload during a file edit) while tasks were queued or running, those tasks are silently dropped. The document row stays at `pending`/`embedding` until the next startup sweep.

**This is MVP accepted risk** — the `TaskDispatcher` abstraction is in place for a future Celery/RQ migration. The stale cleanup at startup is the correct short-term mitigation.

**Secondary: orphaned `pending` rows on upload failure.** The upload route inserts the document row first, then checks the OpenAI key. If `fetch_user_key_async` raises unexpectedly (not the HTTPException path), the document row exists at `pending` with no background task dispatched. Low probability, but worth cleaning up.

**Fix (code):** Add document row cleanup inside the upload route's exception handler — if any step after the insert fails with a non-HTTP exception, delete the orphaned row before propagating.

---

### RC-3 — Medium: `cleanup_stale_jobs` overwrites real error messages

**Evidence:** The document with `retry_count=3` shows "Stale job timeout: stuck in 'extracting' for >30 minutes" — but 3 retries means the pipeline was actively running and had set real error messages. The stale cleanup overwrote them.

**Root cause:** `cleanup_stale_jobs` calls `.update({"error_message": "Stale job timeout..."})` unconditionally, regardless of whether the column already has a value. When a job is mid-retry-sleep and the server restarts, the real failure reason is destroyed.

**Impact:** We can't diagnose why extraction failed 3x for that document. The JSONL extraction is pure Python (no I/O), so a persistent failure suggests malformed content or a decode error — but the real error is gone.

**Fix (code):** In `cleanup_stale_jobs`, only set `error_message` when the existing value is NULL. Postgres: add `.is_("error_message", "null")` to the update's WHERE clause, OR update only the `status` and `error_stage` fields and leave `error_message` unchanged if it already exists.

---

### RC-4 — Informational: Token limit exceeded — correct behavior, minor retry UX gap

**Evidence:** "Document exceeds token limit: 3,320,528 > 1,000,000" — the full `nate_b_jones_content.jsonl` file (3.3M tokens, 3.3x the 1M limit). `TokenLimitExceeded` is non-retryable by design — no retry loop is attempted.

**UI gap:** The Retry button appears for ALL failed documents including this one. Clicking it will: reset status to `pending`, dispatch the pipeline, re-run extraction, hit the same token limit, fail again. Net result: user gets confused, document row is reset unnecessarily.

**Fix (code):** Suppress the Retry button in `DocumentRow` when the error is non-retryable. Simplest check: `errorMessage?.includes("token limit")`. Better: add an `is_retryable: boolean` field to the `DocumentStatusResponse` API model (defaulting to true, false for `TokenLimitExceeded`).

**User action required:** Split `nate_b_jones_content.jsonl` into files under 1M tokens each, or use `nate_b_jones_content_sample.jsonl` (the sample file — already completed successfully).

---

### RC-5 — Informational: NULL chunk enrichment fields — expected/deferred

**Evidence:** `chunk_summary`, `keywords`, `section_path`, `page_range`, `tsv` are NULL on all chunk rows.

**Root cause:** These are deferred V1 schema fields. The MVP pipeline runs document-level enrichment only (summary, tags). Chunk-level enrichment and FTS (`tsv`) are not implemented in MVP.

**Fix:** None — this is expected behavior.

---

## Priority Fix Order for Dinesh (KIN-408)

| Priority | Fix | Type | Owner |
|---|---|---|---|
| 0 | Create `"uploads"` bucket in Supabase | Deployment | Brandon |
| 1 | Preserve real error message in stale cleanup | Code — `app/services/background.py` | Dinesh |
| 2 | Suppress retry button for token-limit failures | Code — `DocumentRow.tsx` OR `documents.py` | Dinesh |
| 3 | Orphaned pending row cleanup on upload failure | Code — `app/api/routes/documents.py` | Dinesh |
| — | BackgroundTasks durability | MVP accepted — no code change | — |
| — | NULL chunk enrichment fields | Deferred V1 — no action | — |

---

## Verification Steps (post-fix)

1. Create `"uploads"` bucket in Supabase → upload a new document → confirm `storage_uri` is populated
2. Verify retry works for a `failed` document with valid `storage_uri`
3. Upload a token-limit-exceeding file → confirm Retry button is suppressed or shows a non-retryable message
4. Force a stale cleanup scenario (manual DB update) → confirm real `error_message` is preserved

— Gilfoyle
