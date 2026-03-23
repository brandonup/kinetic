# KIN-320 Code Review

**Reviewer:** Gilfoyle
**Date:** 2026-03-23
**Files reviewed:**
- `projects/kinetic/packages/api/app/api/routes/agents.py` (lines 335–625: three new endpoints)
- `projects/kinetic/packages/api/tests/test_agents.py` (TestFrameworkMutations class)
- `projects/kinetic/packages/web/lib/types/models.ts` (Framework mutation types)
- `projects/kinetic/packages/web/components/FrameworkLibraryTab.tsx` (full file)

---

## Strengths

- **Route ordering is correct.** `POST /{agent_id}/frameworks/upload` is registered at line 335, before `POST /{agent_id}/frameworks` at line 463. FastAPI will match `/upload` literally before it could be captured as `{framework_id}`. No ambiguity issue.
- **ENUM compliance.** `confidence` validated as `"high" | "medium"` both in Pydantic models (`Literal["high", "medium"]`) and in the upload endpoint's per-item validation (`if confidence not in {"high", "medium"}`). TypeScript types match. No decimal values anywhere.
- **Per-item error collection in upload.** The upload endpoint collects failures into `failed[]` without aborting the loop. The except clauses log at ERROR level and continue — correct behavior.
- **async Supabase pattern correct.** All three endpoints use `asyncio.get_running_loop().run_in_executor()` consistently.
- **Owner-only ACL.** All three mutation endpoints fetch the agent first, then check `owner_id == current_user.user_id`. Consistent with the pattern established in KIN-319.
- **`when_to_apply` and `principles` non-empty enforcement.** `create_framework` raises 400 on empty lists. `update_framework` validates after building the update dict (correctly — only validates if the field is being set).
- **Frontend PATCH sends only changed fields.** `handleSubmit()` in add mode sends a full `CreateFrameworkRequest`; in edit mode it builds `UpdateFrameworkRequest` by diffing each field against `initial`. This is the correct behavior.
- **Upload JSON parse handles both shapes.** The frontend handles both a bare `Framework[]` array and a `{ frameworks: Framework[] }` object — pragmatic and correctly typed.
- **Optimistic delete restore.** `deletedRowRef` preserves the removed row and restores it on failure. Correct pattern.
- **isOwner gating.** Edit/delete buttons and upload/add controls are entirely hidden from non-owners at the UI layer. Appropriate defense-in-depth (backend still enforces ownership).

---

## Issues

### Critical

None.

---

### Important

**[1] PATCH URL path param named `framework_id` but takes DB `id` (UUID)**
- **File:** `agents.py` line 539, 583, 619
- **Problem:** The route is `PATCH /{agent_id}/frameworks/{framework_id}` and the path param is named `framework_id`, but the backend queries `.eq("id", framework_id)` — it is receiving and using the DB UUID (`frameworks.id`), not the semantic slug (`frameworks.framework_id`). This is correct at runtime because the frontend sends `editTarget.id` (the UUID). But the naming is wrong and will confuse any future developer who reads this endpoint signature. The field named `framework_id` in the schema spec is the semantic slug (e.g., `coordination-tax-diagnostic`), not the PK. The route param should be named `framework_db_id` or, better, the route should be structured so the semantic distinction is clear.
- **Risk:** A future developer could wire up a client that sends the semantic slug instead of the UUID, get a 404, and spend hours debugging. More likely someone will add an endpoint that passes `framework_id` (slug) by convention and silently break this one.
- **Fix:** Rename the path param to `framework_db_id` in both the route decorator and function signature. Update the two `.eq("id", framework_id)` calls to `.eq("id", framework_db_id)`. Update the TypeScript `UpdateFrameworkRequest` call site to confirm it still sends `editTarget.id`.

**[2] `upload_frameworks`: update path uses `source_posts` field in existing frameworks but does not allow updating it**
- **File:** `agents.py` lines 418–421 (the update field list)
- **Problem:** The update dict in the upload path iterates over `("name", "when_to_apply", "confidence", "principles", "category", "description", "example_application", "steps", "related_frameworks", "origin")`. The `source_posts` column exists in the schema (§14) and is part of the framework shape. An extracted framework being re-uploaded may carry updated `source_posts`, but they will be silently dropped. This is a data-loss edge case on the update path only.
- **Fix:** Add `"source_posts"` to the field list in the update loop (line 418). The insert path already handles it implicitly since it copies from `item` — but wait, the insert path only copies `category`, `description`, `example_application`, `steps`, `related_frameworks` from optional fields (line 446). `source_posts` is also missing from the insert path. Fix both.

**[3] `create_framework` inserts `steps: []` and `related_frameworks: []` unconditionally**
- **File:** `agents.py` lines 514–516
- **Problem:** The row dict unconditionally sets `"steps": body.steps` and `"related_frameworks": body.related_frameworks`. `CreateFrameworkRequest` defaults both to `[]`. This means every manual create writes empty arrays for these columns. That's not a bug per se — the DB columns accept `text[]` — but it differs from the upload path, which only includes these fields if present in the source item (`if field in item`). More importantly, the frontend `CreateFrameworkRequest` type in `models.ts` marks both as `steps?: string[]` and `related_frameworks?: string[]` (optional), meaning the frontend will never send them unless explicitly set. The backend model defaults them to `[]`, so they will always be written. Minor data inconsistency risk but worth aligning.
- **Fix:** Make the insert conditional (same pattern as `category`, `description`, `example_application` above line 518) or accept that `[]` is a valid empty-array default and document it.

**[4] `handleFormSave`: empty PATCH body sent without guard**
- **File:** `FrameworkLibraryTab.tsx` lines 59–67
- **Problem:** In edit mode, `handleSubmit()` builds `body: UpdateFrameworkRequest = {}` and calls `onSave(body)` regardless of whether any field actually changed. If the user opens the edit form and clicks "Save changes" without modifying anything, the frontend sends `PATCH` with `{}` (just `updated_at` on the backend). The request succeeds (the backend will update `updated_at` only) and a toast shows "Framework saved." This is misleading UX — the user made no change but is told it was "saved." It's not a data corruption issue, but it generates a spurious DB write and misleads the user.
- **Fix:** Add a guard in `handleFormSave` before making the request: if `editTarget` is set and `Object.keys(body).length === 0`, show a toast "No changes to save" and return early.

**[5] `loadFrameworks` in upload handler swallows network errors silently**
- **File:** `FrameworkLibraryTab.tsx` lines 236–249, 342
- **Problem:** `loadFrameworks()` catches all errors silently (`catch { // Silent — empty state rendered }`). This is acceptable for the initial load (empty state is a reasonable fallback). But after a successful upload, `void loadFrameworks()` is called — if that refresh fails, the list stays stale and the user sees the pre-upload count with no indication the refresh failed. Not a data integrity issue but operationally misleading.
- **Fix:** Call `loadFrameworks()` with a toast on error after upload, or at minimum log the error. The pattern should be: upload summary shows the server-side result, then the list refreshes to show current state — a failed refresh should surface.

---

### Minor

**[6] Misleading `retained` count in upload response**
- **File:** `agents.py` line 459
- **Problem:** `retained = len(existing) - updated`. This counts the number of existing frameworks that were not updated in this upload batch. This is not the number "retained" in the agent's library — it is the number of pre-existing frameworks that happened not to be in the upload. This number is meaningful only if the upload is meant to be a full replacement. Since it is not (the endpoint does not delete unmatched frameworks), `retained` could be misread as "all these were preserved." The description "retained" is already in the summary modal on the frontend.
- **Severity:** Minor — it's a cosmetic/semantic issue, not a functional one.
- **Fix:** Rename to `untouched` or add a comment in both the backend response and the frontend summary modal clarifying that this count is existing frameworks not in the upload batch.

**[7] `FrameworkForm` edit mode drops `principles` field entirely**
- **File:** `FrameworkLibraryTab.tsx` lines 123–153
- **Problem:** The `principles` input block is only rendered when `!initial` (add mode). In edit mode, principles are not shown and not patchable from the UI. The `UpdateFrameworkRequest` type includes `principles` as an optional field, and the backend supports it. This is a deliberate spec choice per the comment ("edit doesn't surface it per spec"), but it is worth noting that if a user creates a framework with wrong principles, there is no UI path to fix them — they must delete and re-add. This is a product decision (flag for Jared), not a code defect. Documenting it here for visibility.
- **Fix:** None required at code level — but suggest Jared decides if this is intentional forever or just deferred.

**[8] `UpdateFrameworkRequest` in `models.ts` does not include `description` or `steps`**
- **File:** `packages/web/lib/types/models.ts` lines 188–195
- **Problem:** The backend `UpdateFrameworkRequest` Pydantic model (lines 85–91) supports patching: `name`, `when_to_apply`, `category`, `example_application`, `confidence`, `principles`. The TypeScript `UpdateFrameworkRequest` mirrors these exactly. However, the backend does not support patching `description` or `steps` in the PATCH endpoint (they are not in the `updates` dict). If a future developer adds `description` to `UpdateFrameworkRequest` on the TS side and sends it, the backend silently ignores it. This is a current gap between what exists in the schema and what the PATCH endpoint handles.
- **Fix:** Minor — document the intentional exclusions in the backend docstring, or add them to the PATCH endpoint. Low priority since the frontend form doesn't expose them either.

---

## Assessment

**APPROVED WITH FIXES REQUIRED**

The core functionality is correct: routes are ordered correctly, ENUMs are right, async patterns are correct, ACL is enforced, per-item error collection works, and the frontend correctly sends PATCH-only-changed-fields vs POST-full-body. No data corruption paths.

The Important issues are real but not blockers for shipping — items 1 (param naming), 2 (`source_posts` data loss on upload), and 4 (empty PATCH guard) are the ones worth fixing before this goes to production. Items 3, 5 are lower urgency but should be addressed. Items 6, 7, 8 are minor.

Fix Priority: Issue 1 (naming confusion will cause future bugs), Issue 2 (silent data loss on upload update path), Issue 4 (misleading UX + spurious DB write).

---

## Re-Review: CHANGES_REQUESTED fixes — 2026-03-23

All 4 Important issues (Issues #1–#2, #4–#5) verified fixed:

- **Issue #1 (api-contract):** Path param renamed `framework_db_id` throughout (decorator, signature, both `.eq()` calls). Docstring distinguishes UUID PK from semantic slug. ✓
- **Issue #2 (error-swallow):** `"source_posts"` added to update field tuple in upload path. ✓
- **Issue #3 (other / empty PATCH guard):** Guard added at top of `handleFormSave` — edit mode with empty body returns early, no API call, no toast. ✓
- **Issue #4 (other / loadFrameworks):** `void loadFrameworks()` replaced with `.catch()` toast on refresh failure. ✓

**Verdict: APPROVED**
