# Code Review — KIN-378: Add document delete endpoints

**Date:** 2026-03-26
**Reviewer:** Gilfoyle
**Verdict:** CHANGES REQUESTED
**Critical:** 2 | **Important:** 4

---

## Files Reviewed

- `packages/api/app/api/routes/documents.py` — lines 409–485 (single delete)
- `packages/api/app/api/routes/kb_management.py` — lines 179–260 (delete-all)
- `packages/api/tests/test_document_delete.py` — full file

---

## Critical Findings

### C1 — Schema mismatch: hard DELETE contradicts soft-delete spec

**File:** `documents.py` lines 461–467; `kb_management.py` lines 234–241

Both endpoints issue hard `DELETE` against `knowledge_base_documents` and claim CASCADE deletes chunks. This directly contradicts two authoritative sources:

1. **`docs/db-schema-spec.md` §12 + Cross-Cutting Patterns "Soft-Delete with Deferred Cleanup":**
   > Documents and conversations use soft-delete (`deleted_at` timestamp). Chunks belonging to soft-deleted documents are not immediately removed — a scheduled cleanup job hard-deletes chunks for documents where `deleted_at` is older than 7 days. This avoids expensive HNSW reindexing during user-facing operations.

2. **`MEMORY.md` decision (2026-03-22):**
   > Document deletion: soft-delete with deferred cleanup. `deleted_at` timestamp; chunks cleaned up after 7 days.

The schema column exists: `deleted_at | timestamptz | (soft-delete)`. The ticket spec itself is wrong — it describes "hard DELETE (CASCADE chunks)" but the locked design decision requires soft-delete. The ticket spec must have been written against the wrong behavior.

**Impact:** Issuing hard DELETEs triggers immediate CASCADE deletion of all `knowledge_base_chunks`, which forces an HNSW index rebuild. On a large KB this is expensive and directly degrades RAG query performance for all users sharing the pgvector index. The entire rationale for the soft-delete decision was to avoid this.

**Fix required:**
- Both delete endpoints must set `deleted_at = now()` instead of issuing `DELETE`.
- Chunk cleanup should be left to the scheduled cleanup job (7-day deferred).
- Storage cleanup timing is a product question: either leave it for the cleanup job or run it eagerly (non-fatal). Eager storage cleanup on soft-delete is acceptable since storage orphans are recoverable; chunk CASCADE is not.
- The docstrings referencing "CASCADE auto-deletes chunks" must be updated.
- Tests must be rewritten: assert `deleted_at` is set, not that a hard delete was called.
- The response models `DeleteDocumentResponse` and `DeleteAllDocumentsResponse` need no structural change — `deleted: true` / `deleted_count: N` remain valid for soft-delete.

Note: Brandon needs to confirm whether storage cleanup runs eagerly at soft-delete time (current behavior, just non-fatal) or is also deferred to the cleanup job. Flag this as a spec gap before re-implementing — see C2 section below.

---

### C2 — Auth asymmetry: single delete returns 403 instead of 404 for cross-tenant access

**File:** `documents.py` lines 450–451

```python
if not kb_check.data or kb_check.data.get("user_id") != current_user.user_id:
    raise HTTPException(status_code=403, detail="Access denied.")
```

The established convention for cross-tenant denials is 404 (anti-enumeration). From MEMORY.md (2026-03-24):
> MCP access control uses 404 for cross-tenant denials (anti-enumeration). No 403.

The `_verify_kb_ownership` helper in `kb_management.py` (which handles delete-all auth) correctly raises 404. The `_verify_doc_ownership` helper also uses 404. The single delete endpoint is the only place in the codebase that exposes a 403 for document ownership, and it leaks the existence of the document to the requesting user.

**Fix:** Change `status_code=403` to `status_code=404` and update the detail message to "Document not found." — consistent with all other cross-tenant denials in the codebase.

**Test impact:** `test_other_users_document_returns_403` must be updated to assert 404.

---

## Important Findings

### I1 — `ACTIVE_INGESTION_STATUSES` duplicated across two modules

**Files:** `documents.py` line 409; `kb_management.py` line 179

The same constant is defined in both files. If a new pipeline status is added (e.g., `reindexing`), it must be updated in two places and one is guaranteed to be missed.

**Fix:** Extract to `app/core/constants.py` (or a `documents` constants module) and import in both routes. One source of truth.

---

### I2 — `deleted_count=0` branch raises 500 with a misleading error message

**File:** `kb_management.py` lines 242–246

```python
deleted_count = len(delete_result.data) if delete_result.data else 0
if deleted_count == 0:
    logger.error("delete_all_documents: no rows deleted for KB %s", kb_id)
    raise HTTPException(status_code=500, detail="Failed to delete documents.")
```

The message "Failed to delete documents" implies a DB error. What actually happened is a race condition: documents were fetched, then deleted (or already soft-deleted) between fetch and delete. The 500 is appropriate but the log + detail message should describe the actual condition: "Unexpected state: documents not found at delete time (possible race condition)." This assists debugging when the 500 fires in production.

**Fix:** Update the log message and HTTP detail to reflect the race-condition interpretation.

(Note: this finding becomes moot if C1 is fixed and the endpoint switches to soft-delete via UPDATE — UPDATE returning `data=[]` means the race is less likely and the semantics differ. Revisit when C1 is addressed.)

---

### I3 — Missing test: storage cleanup failure on delete-all

**File:** `tests/test_document_delete.py`

`TestDeleteDocument` includes `test_storage_failure_does_not_fail_request` (line 166). `TestDeleteAllDocuments` has no equivalent. The delete-all endpoint loops over storage paths and catches exceptions individually — this should be verified.

**Fix:** Add `test_storage_failure_does_not_fail_delete_all` to `TestDeleteAllDocuments`. Set `mock_client.storage.from_.return_value.remove.side_effect = Exception("Storage unavailable")`, assert 200 and `deleted_count > 0`.

---

### I4 — Single-delete mock doesn't guard against delete-path filter additions

**File:** `tests/test_document_delete.py` lines 64–67

The `_mock_single_delete` helper wires the delete branch as:
```python
m.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=[doc])
```

The production delete is `.delete().eq("id", str(document_id)).execute()`. If a safety filter is ever added (e.g., `.eq("id",...).is_("deleted_at", "null").execute()`), the mock silently breaks — it returns `MagicMock()` instead of `MagicMock(data=[doc])`, causing the endpoint to raise 500 in tests without any obvious failure message.

**Fix:** After C1 is addressed (soft-delete replaces hard delete), the mock will need to be rewritten entirely. If hard delete is retained anywhere, add explicit assertion on `mock_client.table("knowledge_base_documents").delete()` call count and chain to make mock fragility visible.

---

## Spec Gap Requiring Brandon's Decision

The ticket spec says "storage cleanup (non-fatal)" but does not specify whether storage cleanup happens:
- (a) **Eagerly at soft-delete time** — non-fatal, files may be orphaned if cleanup fails
- (b) **Deferred with chunk cleanup** — cleanup job handles both chunks and storage files after 7 days

Option (a) is what was implemented (the non-fatal storage removal loop). Option (b) is simpler — the endpoint only writes `deleted_at = now()` and returns. Both are valid; the schema spec does not specify. This should be confirmed before re-implementation to avoid a third review cycle.

Flag for Brandon: **Should storage file cleanup happen immediately at delete time (non-fatal), or be handled by the deferred cleanup job alongside chunks?**

---

## Summary

The ticket spec contains a hard error: it specifies "hard DELETE (CASCADE chunks)" but the locked architectural decision in `db-schema-spec.md` and `MEMORY.md` requires soft-delete. Everything else (auth, async patterns, error handling structure, response models) is correct — the implementation is well-structured code built to the wrong spec. Fix C1 and C2, confirm the storage timing question, then re-submit.
