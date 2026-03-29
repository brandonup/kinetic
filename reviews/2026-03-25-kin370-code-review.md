# Code Review — KIN-370: Project KB — Document Upload UI

**Date:** 2026-03-25
**Reviewer:** Gilfoyle
**Ticket:** KIN-370 — [Dinesh] Project KB — document upload UI
**Verdict:** CHANGES REQUESTED

---

## Summary

Two findings: one Critical (missing test coverage for both new endpoints) and one Important (HTTP contract violation on the idempotent POST path). Architecture is solid. No schema mismatches. Async patterns are correct. No silent error swallowing. One round of fixes clears this.

---

## Files Reviewed

- `packages/api/app/api/routes/projects.py` (lines 285–371)
- `packages/web/app/(app)/projects/page.tsx`

---

## Findings

### C1 — CRITICAL: No test coverage for new KB endpoints

**File:** `packages/api/tests/test_projects.py`

**Problem:** `test_projects.py` covers the KIN-263 CRUD endpoints only. There are zero tests for:
- `GET /api/v1/projects/{project_id}/knowledge-base` — 200 (KB found), 404 (no KB), 404 (project not owned)
- `POST /api/v1/projects/{project_id}/knowledge-base` — 201 (created), 200 (idempotent return), 404 (project not owned), 500 (insert returns no data)

Both endpoints carry authorization logic (`eq("user_id", current_user.user_id)`) and an error path on the insert (`ValidationError` if `insert_result.data` is falsy). These are untested. Convention: every feature ships with tests. No exceptions.

**Fix:** Add a `TestProjectKnowledgeBase` class to `test_projects.py` covering all six paths above. Use the existing `PATCH_TARGET = "app.api.routes.projects.get_supabase_client"` and the `_project_row()` helper as the model. Chain the mock for the KB table lookup using a second `MagicMock`.

---

### I1 — IMPORTANT: Idempotent POST returns 201 for an existing resource

**File:** `packages/api/app/api/routes/projects.py`, line 357

**Problem:** The route decorator declares `status_code=201`. FastAPI applies this status code to all returns from the function — including the early-return idempotent path when the KB already exists:

```python
if kb_rows:
    return {"id": kb_rows[0]["id"]}  # FastAPI returns 201 — wrong
```

201 means "a new resource was created." Returning 201 when no creation occurred is an HTTP contract violation. Callers that inspect status codes (tests, SDKs, future MCP integration) will misread this as a creation event.

**Fix:** Use `Response` to return 200 on the idempotent path:

```python
from fastapi import Response

if kb_rows:
    return Response(content=..., status_code=200)
```

Or more cleanly, accept `Response` as a parameter and set it:

```python
async def create_project_knowledge_base(
    project_id: str,
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    ...
    if kb_rows:
        response.status_code = 200
        return {"id": kb_rows[0]["id"]}
```

Either approach is acceptable. The created path stays 201.

---

## What's Good

- **Schema alignment confirmed.** `knowledge_bases` insert passes `project_id` and `user_id` — both required per `db-schema-spec.md §10`. No missing columns.
- **Async patterns correct.** All Supabase calls use `run_in_executor` with `get_running_loop()`. No sync calls in async context.
- **Ownership verification correct.** Both endpoints verify `user_id` on the project lookup before touching `knowledge_bases`. No ACL leak.
- **Error handling correct on write path.** Insert failure raises `ValidationError` after logging — not a silent swallow. Compliant with conventions.
- **Frontend state management clean.** `kbLoading` set synchronously in `startSettings`, cleared in `.finally()` — correct for both success and error. `cancelSettings` resets all KB state. No leaks.
- **No duplication.** Reuses `KnowledgeBaseTab` component with correct `knowledgeBaseId` prop type (`string | null`, guarded by conditional render).
- **404 on GET is correct UX.** Lazy-loading treats 404 as "no KB" state, which drives the "Create Knowledge Base" button — appropriate first-time-setup flow.

---

## Defect Log Entries

| Date | Ticket | Reviewer | Category | Severity | Description |
|---|---|---|---|---|---|
| 2026-03-25 | KIN-370 | Gilfoyle | test-missing | Critical | No tests for GET/POST knowledge-base endpoints — 0 of 6 paths covered |
| 2026-03-25 | KIN-370 | Gilfoyle | api-contract | Important | Idempotent POST returns 201 instead of 200 when KB already exists |
