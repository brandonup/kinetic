# KIN-376 Code Review — Profile Model Dropdown Fix

**Ticket:** KIN-376 — [Dinesh] Profile page — Default Model dropdown shows no options
**Reviewer:** Gilfoyle
**Date:** 2026-03-26
**Round:** 1
**Verdict:** APPROVED

---

## Files Reviewed

| File | Changes |
|---|---|
| `packages/web/app/(app)/profile/page.tsx` | 3 edits: state decl (L84), error tracking in `loadAll` (L134-144), conditional render (L516-552) |

---

## Findings

### Important (non-blocking)

**I1 — `modelsError` not reset on retry path.**
File: `packages/web/app/(app)/profile/page.tsx`, lines 134-144.
Issue: `setModelsError(false)` is called inside the `if (modelsRes.ok)` branch, which correctly resets on success. However, `loadAll()` is only called on mount (`useEffect` with `[]` deps). There is no retry mechanism — the error message says "Try refreshing the page," which triggers a full page reload and re-mount, so the state resets naturally. This is acceptable for a bug fix. If a "Retry" button is added later, `modelsError` must be reset at the top of `loadAll()` before the fetch, not just on success.

**I2 — Outer catch swallows models fetch error.**
File: `packages/web/app/(app)/profile/page.tsx`, lines 150-152.
Issue: If the `Promise.all` itself throws (network error, not an HTTP error), the outer `catch` block silently swallows it — `modelsError` stays `false`, and the user sees the empty-state message ("No generation models available") instead of the error message. This is a pre-existing issue (not introduced by this PR) and the empty state is still informative, so not blocking. But it should be noted: a network-level failure on models fetch will show the wrong empty state.

### Notes (informational)

**N1 — Admin endpoint used by non-admin page.**
The profile page fetches `GET /api/v1/admin/models` to populate the model dropdown. If admin endpoints are later gated by role, this will break for non-admin users. This is a pre-existing pattern, not introduced by this PR.

---

## Done-When Checklist

| Criterion | Met? |
|---|---|
| Default Model dropdown populates with all admin-enabled generation models | Yes -- existing logic unchanged, filters `category === "generation" && m.enabled` |
| User can select a model and it saves to their profile | Yes -- `setDefaultModel()` PATCH flow unchanged |
| If no generation models enabled, dropdown shows empty state with helpful message | Yes -- empty state with link to admin models page |
| Error state when fetch fails | Yes -- "Failed to load models. Try refreshing the page." |

---

## Summary

Clean, minimal fix. The three edits are correctly scoped: state flag, error tracking, and three-branch render. The existing model selection and save flow is untouched. Both Important findings are pre-existing edge cases, not regressions introduced by this PR. Approved.
