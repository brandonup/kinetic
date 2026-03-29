# KIN-336: Document Ingestion Retry + AI Auto-Suggest Tags

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add retry-from-failed-stage for document ingestion and AI-generated tag suggestions on upload.

**Architecture:** Two features, both extend the existing ingestion pipeline. Retry persists files to Supabase Storage on upload (`storage_uri` column, already in schema) and extracted text as a sibling file, enabling stage-resumption without re-processing. Tag suggestions follow the summarizer pattern — non-fatal, platform Haiku key, stored in the existing `tags text[]` column. Both features are backend-only; frontend wiring is KIN-346 (Dinesh).

**Tech Stack:** Python 3.11, FastAPI, Supabase (DB + Storage), LiteLLM (Haiku), pytest

**Spec ref:** `docs/prd.md` §7, `docs/db-schema-spec.md` §12

---

## Design Decisions

### Retry: File Persistence via Supabase Storage

The current upload flow reads file bytes into memory and passes them to the background pipeline. For retry, we need the file after the initial request is gone.

**Approach:** Use Supabase Storage (bucket: `settings.SUPABASE_STORAGE_BUCKET`, default `"uploads"`).
- On upload: store file → set `storage_uri` on document row
- After extraction: store extracted text as `{document_id}/extracted.txt`
- On retry: download file (if re-extracting) or text (if resuming from chunking+)
- Cleanup: delete storage files when document is soft-deleted (deferred — not in this ticket)

**Stage resumption logic:**
| `error_stage` | Retry starts from | Needs from Storage |
|---|---|---|
| `extracting` | extraction | file bytes |
| `chunking` | chunking | extracted text |
| `embedding` | chunking (re-chunk is fast, avoids storing chunk artifacts) | extracted text |

Re-chunking on embedding retry is a simplification: chunking is CPU-only and takes <1s for any reasonable document. Avoids needing to persist chunk objects.

### Retry: Chunk Cleanup

Before retry, delete any existing `knowledge_base_chunks` rows for this document. Ensures idempotency if a previous attempt partially indexed.

### Tags: Follows Summarizer Pattern

Non-fatal, sync `call_llm` wrapped in `run_in_executor`, platform Haiku key. Returns `List[str]` or `[]` on failure. Integrated into the pipeline after extraction, alongside summary generation.

---

## Task List

### Task 1: Create tag suggestion service

**Files:**
- Create: `packages/api/app/services/ingestion/tag_suggester.py`
- Test: `packages/api/tests/test_ingestion.py` (new class `TestTagSuggestion`)

**Implementation:**
Follow `summarizer.py` exactly. Same imports, same error handling pattern. Differences:
- Prompt asks for 3-5 single-word or short-phrase tags as a comma-separated list
- Parse response by splitting on commas, stripping whitespace, lowercasing
- Return `List[str]` (empty list on failure, not None)
- Use `_SNIPPET_CHARS = 8_000` (same as summarizer)
- Use `settings.CONVERSATION_COMPRESSION_MODEL` (Haiku)
- Guard on `settings.PLATFORM_ANTHROPIC_KEY` and `settings.ENRICHMENT_ENABLED`

**Tests (3):**
1. `test_tag_suggestion_happy_path` — mock `call_llm` to return `"strategy, leadership, decision-making"`, assert returns `["strategy", "leadership", "decision-making"]`
2. `test_tag_suggestion_failure_returns_empty_list` — mock `call_llm` to raise, assert returns `[]`
3. `test_tag_suggestion_disabled_returns_empty_list` — set `ENRICHMENT_ENABLED=False`, assert returns `[]`

**Commit:** `feat: add AI tag suggestion service (KIN-336)`

---

### Task 2: Integrate tags into pipeline

**Files:**
- Modify: `packages/api/app/services/ingestion/pipeline.py`
- Test: `packages/api/tests/test_ingestion.py` (modify `TestIngestionHappyPath`)

**Implementation:**
After the summary generation block (line ~156), add tag generation:
```python
from app.services.ingestion.tag_suggester import suggest_tags

# ... after summary block ...
tags = await loop.run_in_executor(None, lambda: suggest_tags(text))
if tags:
    await _update_document(supabase, document_id, tags=tags)
```

Import `suggest_tags` at the top of the file alongside `generate_summary`.

**Tests:**
- Update `test_document_processes_through_all_stages`: patch `suggest_tags` to return `["test-tag"]`, verify `tags` appears in update calls.
- New `test_tag_failure_does_not_block_ingestion`: patch `suggest_tags` to return `[]`, verify pipeline completes normally.

**Commit:** `feat: integrate tag suggestions into ingestion pipeline (KIN-336)`

---

### Task 3: Store file in Supabase Storage on upload

**Files:**
- Modify: `packages/api/app/api/routes/documents.py`
- Test: `packages/api/tests/test_ingestion.py` (new class `TestFileStorage`)

**Implementation:**
In `upload_document()`, after creating the document row, upload to Storage:
```python
storage_path = f"{document_id}/{file.filename or 'document'}"
await loop.run_in_executor(
    None,
    lambda: supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET)
    .upload(storage_path, content, {"content-type": content_type}),
)
await loop.run_in_executor(
    None,
    lambda: supabase.table("knowledge_base_documents")
    .update({"storage_uri": storage_path})
    .eq("id", str(document_id))
    .execute(),
)
```

If storage upload fails, log warning and continue — don't fail the upload. The document can still process; retry will fail gracefully if storage is unavailable.

**Tests:**
1. `test_upload_stores_file_in_storage` — mock `supabase.storage.from_().upload()`, verify called with correct path and content
2. `test_upload_continues_if_storage_fails` — mock storage upload to raise, verify upload endpoint still returns 200 and pipeline is dispatched

**Commit:** `feat: persist uploaded files to Supabase Storage (KIN-336)`

---

### Task 4: Store extracted text in Storage after extraction

**Files:**
- Modify: `packages/api/app/services/ingestion/pipeline.py`
- Test: `packages/api/tests/test_ingestion.py`

**Implementation:**
After extraction succeeds (line ~149), store extracted text to Storage:
```python
# Persist extracted text for stage-resume retry
text_storage_path = f"{document_id}/extracted.txt"
try:
    await loop.run_in_executor(
        None,
        lambda: supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET)
        .upload(text_storage_path, text.encode("utf-8"), {"content-type": "text/plain"}),
    )
except Exception as exc:
    logger.warning("Failed to persist extracted text (non-fatal): %s", exc)
```

Non-fatal — if storage fails, the document still processes. Retry from chunking+ just won't be available (retry from scratch will still work).

**Tests:**
1. `test_extracted_text_stored_after_extraction` — mock storage, verify `upload` called with `{doc_id}/extracted.txt`
2. `test_extraction_continues_if_text_storage_fails` — mock storage upload to raise, verify pipeline completes

**Commit:** `feat: persist extracted text to Storage for retry (KIN-336)`

---

### Task 5: Add retry endpoint

**Files:**
- Modify: `packages/api/app/api/routes/documents.py`
- Test: `packages/api/tests/test_ingestion.py` (new class `TestRetryEndpoint`)

**Implementation:**
Add `POST /api/v1/documents/{document_id}/retry`:

```python
class RetryResponse(BaseModel):
    document_id: str
    status: str
    message: str

@router.post("/{document_id}/retry", response_model=RetryResponse)
async def retry_document(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
) -> RetryResponse:
```

**Logic:**
1. Fetch document row — 404 if not found or soft-deleted
2. Verify `status == 'failed'` — 409 if not failed
3. Ownership check via KB chain — 403 if not owner
4. Read `error_stage` and `storage_uri`
5. Determine resume strategy:
   - `error_stage == 'extracting'`: download file from Storage via `storage_uri`, run full pipeline
   - `error_stage` in `('chunking', 'embedding')`: download extracted text from `{document_id}/extracted.txt`, run pipeline with `start_stage='chunking'`
6. If storage download fails: 500 with "File not available for retry"
7. Delete existing chunks for this document (idempotency)
8. Reset: `status='pending'`, `error_stage=None`, `error_message=None`, `retry_count=0`
9. Dispatch `run_ingestion` (or `run_ingestion_from_stage`) to background
10. Return `{document_id, status: "pending", message: "Retry initiated"}`

**Tests (5):**
1. `test_retry_resets_failed_document` — mock failed doc, verify status reset and pipeline dispatched
2. `test_retry_non_failed_returns_409` — mock doc with `status='completed'`, expect 409
3. `test_retry_not_found_returns_404` — no doc, expect 404
4. `test_retry_cleans_existing_chunks` — verify `knowledge_base_chunks` delete called
5. `test_retry_access_denied_returns_403` — different user, expect 403

**Commit:** `feat: add retry endpoint for failed documents (KIN-336)`

---

### Task 6: Modify pipeline to support stage resumption

**Files:**
- Modify: `packages/api/app/services/ingestion/pipeline.py`
- Test: `packages/api/tests/test_ingestion.py` (new class `TestStageResumption`)

**Implementation:**
Add new function `run_ingestion_from_stage`:

```python
async def run_ingestion_from_stage(
    supabase,
    document_id: UUID,
    knowledge_base_id: UUID,
    project_id: Optional[UUID],
    agent_definition_id: Optional[UUID],
    start_stage: str,  # 'extracting' or 'chunking'
    file_content: Optional[bytes] = None,  # required if start_stage == 'extracting'
    extracted_text: Optional[str] = None,  # required if start_stage == 'chunking'
    filename: str = "",
    content_type: str = "application/octet-stream",
) -> None:
```

If `start_stage == 'extracting'`: call existing `run_ingestion` with `file_content`.
If `start_stage == 'chunking'`: skip extraction, use `extracted_text`, run chunking → embedding → indexing → completed. Reuse `_run_stage` helper and the same enrichment flow (summary + tags use the provided text).

**Tests:**
1. `test_resume_from_chunking_skips_extraction` — provide text, verify `extract_text` not called
2. `test_resume_from_chunking_runs_full_pipeline` — verify chunking, embedding, indexing all run
3. `test_resume_from_extracting_runs_full_pipeline` — verify all stages run

**Commit:** `feat: add stage-resumption to ingestion pipeline (KIN-336)`

---

### Task 7: Update DocumentStatusResponse to include tags

**Files:**
- Modify: `packages/api/app/api/routes/documents.py`
- Test: `packages/api/tests/test_ingestion.py`

**Implementation:**
Add `tags: list[str] = []` to `DocumentStatusResponse`. Update the `get_document_status` handler to include `tags` in the select query and response.

**Tests:**
1. `test_document_status_includes_tags` — mock doc with tags, verify response includes them

**Commit:** `feat: include tags in document status response (KIN-336)`

---

## Done-When Checklist

- [ ] Retry from failed stage works (correct stage resumption, retry counter reset)
- [ ] AI tag suggestions generated on upload, returned via status endpoint
- [ ] Tag suggestion failure is silent (no user-facing error)
- [ ] File persisted in Supabase Storage on upload (`storage_uri` populated)
- [ ] Extracted text persisted for chunking+ retry
- [ ] Existing chunks cleaned up before retry (idempotency)
- [ ] Tests: retry from each stage, tag happy path, tag failure (silent skip)
- [ ] All existing tests still pass

## Test Strategy

| Area | What to test | Type |
|---|---|---|
| Tag suggester | Happy path, failure silence, disabled flag | Unit |
| Pipeline + tags | Tags stored after extraction, failure doesn't block | Unit |
| File storage | Upload persists to Storage, failure non-fatal | Unit |
| Extracted text storage | Text persisted after extraction, failure non-fatal | Unit |
| Retry endpoint | Happy path, 409/404/403 guards, chunk cleanup | API (TestClient) |
| Stage resumption | Skip extraction on chunking resume, full pipeline on extracting resume | Unit |
| Status response | Tags included in response | API (TestClient) |
