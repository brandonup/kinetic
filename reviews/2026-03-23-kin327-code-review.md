# Sprint 5 Code Review — KIN-327

**Reviewer:** Gilfoyle
**Date:** 2026-03-23
**Status:** Complete — 2 Important, 1 Minor
**Verdict:** Fix before shipping to production. Critical path is clean; two convention violations and one auth gap.

---

## Scope

| Ticket | File(s) |
|---|---|
| KIN-308 | `packages/api/app/api/routes/active_memory.py` |
| KIN-306 / KIN-307 | `packages/api/app/api/routes/conversations.py` |
| KIN-309 | `packages/web/components/ActiveMemoryPanel.tsx`, `ProposalReviewPanel.tsx` |
| KIN-310 / KIN-311 | `packages/api/app/api/routes/linked_upload.py` |
| Tests | `packages/api/tests/test_active_memory.py`, `packages/api/tests/test_linked_upload.py` |

---

## Findings

### [Important] IDOR on company and agent upload endpoints — `linked_upload.py`

`upload_company_document` and `upload_agent_document` accept `company_id` / `agent_id` as URL path parameters but **never verify the resource belongs to the authenticated user.** Any authenticated user can call:

```
POST /api/company/{any_company_id}/upload-document
POST /api/agent/{any_agent_id}/upload-document
```

The `company_id` and `agent_id` path params are accepted and ignored — they don't appear in any query. The only Supabase call is `user_api_keys` for the BYOK check, which is correctly scoped to `current_user.user_id`.

**Practical impact today:** Low. The endpoint is fully stateless (no reads or writes using the IDs) and returns only extraction results from the user's BYOK key. No data leakage, no unauthorized writes.

**Risk going forward:** High. The unvalidated path parameter creates a footgun — any future developer who adds a query using `company_id` or `agent_id` without noticing the missing ownership check will ship an IDOR. Also inconsistent with every other resource-scoped endpoint in the codebase.

**Fix:** Add an ownership check for each surface before the BYOK gate, e.g.:
```python
# For company endpoint — verify company belongs to current_user
company_row = await loop.run_in_executor(
    None,
    lambda: client.table("companies").select("id")
        .eq("id", company_id).eq("user_id", current_user.user_id).single().execute()
)
if not company_row.data:
    raise HTTPException(status_code=404, detail="Company not found.")
```

Filed as: `[Dinesh] linked_upload.py — add ownership check for company_id and agent_id path params`

---

### [Important] Extraction prompts hardcoded inline — `linked_upload.py`

The three prompt ID constants (`PROMPT_ID_PROFILE`, `PROMPT_ID_COMPANY`, `PROMPT_ID_AGENT`) are defined but serve only as dispatch labels. The actual prompt text is hardcoded inline inside `_extract_profile`, `_extract_company`, and `_extract_agent`:

```python
raw_name = call_llm(
    messages=[{
        "role": "user",
        "content": (
            "Extract the person's full name from this document. "
            "Return only the name — no additional text. "
            ...
        ),
    }],
    ...
)
```

`conventions.md` §GenAI: *"No hardcoded prompts in application logic — use a prompts module or config file. Every prompt gets an ID and version."*

The review spec (KIN-327) explicitly requires: *"Agent surface extraction prompt is versioned in prompts module, not hardcoded in route."*

This applies to all three surfaces, not just the agent surface. Prompt versioning is currently impossible — changing any prompt string produces no diffs traceable to a version ID.

**Fix:** Extract prompt text to `app/services/prompts.py` (or equivalent), keyed by the existing version IDs. The `LinkedUploadExtractor` methods look up prompt text by ID rather than containing it inline. Each `call_llm` receives the resolved string.

Filed as: `[Dinesh] linked_upload.py — move extraction prompts to prompts module`

---

### [Minor] `end_conversation` dispatches background job without verifying conversation ownership — `conversations.py`

`POST /api/v1/conversations/{conversation_id}/end` fetches no ownership check before calling `dispatcher.add_task(_generate_proposals_job, ...)`. Any authenticated user can POST this endpoint with an arbitrary `conversation_id` and trigger the proposal generation background job.

**Practical impact:** Low. The background job fetches conversation messages via `conversation_id` and the Supabase RLS policy on `messages` restricts access to conversation owners (`auth.uid() = (SELECT user_id FROM conversations WHERE id = conversation_id)`). The service role key bypasses RLS, which means the job will process messages from any conversation if passed a valid ID.

**Risk:** Medium. With the service-role key bypass, an authenticated user can trigger proposal generation on another user's conversation. The proposals would be inserted into `memory_proposals` with the job's `user_id`, which comes from the conversation row — so the proposals land in the correct user's queue. But it's still an unauthorized trigger against another user's data.

**Fix:** Add a conversation ownership check at the route level before dispatching, consistent with other endpoints that scope by `current_user.user_id`.

Filed as: `[Dinesh] conversations.py — verify conversation ownership before dispatching end_conversation background job`

---

## Clean

| File | Notes |
|---|---|
| `active_memory.py` | `run_in_executor` on all Supabase calls. Token cap `ceil(len/4)` correct. Cap constants 1000/500 match spec. Closure captures use default args correctly (`lambda _pid=proposal_id`). Writes raise on failure — no silent swallow. |
| `background.py` | Clean `TaskDispatcher` abstraction. One swap point for Celery. |
| `conversations.py` | Periodic trigger debounced correctly (skips if pending proposals exist). `trigger_type` set to `'conversation_end'` vs `'periodic'` correctly. BYOK key fetched inside job (not passed as arg). Dedup via content-level set. |
| `ActiveMemoryPanel.tsx` | Token usage bar with `TOKEN_RED_PCT` threshold. Inline edit/delete with optimistic update + re-fetch for accurate counts. `CHAR_SOFT_WARN` correctly capped at 400 chars. `estimateTokens` matches backend `ceil(len/4)`. |
| `ProposalReviewPanel.tsx` | Per-proposal accept/reject with `capExceededIds` UX for partial failures. Defaults all proposals to accept. `setAll` bulk action clears cap-exceeded state. |
| `test_active_memory.py` | Correct ownership check mocking, token cap boundary tests, proposal lifecycle. |
| `test_linked_upload.py` | BYOK gate enforced server-side (all 3 surfaces). Storage never called (success + failure). 422 for corrupted docs (all 3 surfaces). Prompt ID distinctness verified. LLM failure → no partial write. |

---

## Summary

| Severity | Count | Items |
|---|---|---|
| Critical | 0 | — |
| Important | 2 | IDOR on company/agent uploads; extraction prompts hardcoded |
| Minor | 1 | `end_conversation` missing ownership check |

**Recommendation:** Fix before production. The IDOR and missing ownership check are low-risk today (stateless + service-role scoped), but both create footguns for follow-on development. Inline prompts break versioning immediately. None block Sprint 6 development work — these can be fixed in a fast-tier batch.
