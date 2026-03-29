# Code Review: KIN-372 — Framework Library Pin/Exclude UI (Round 2)

**Date:** 2026-03-25
**Reviewer:** Gilfoyle
**File:** `packages/web/components/FrameworkLibraryTab.tsx`
**Verdict:** CHANGES REQUESTED

---

## Summary

R1 finding (zero test coverage) resolved — 9 tests covering pin, exclude, mutual exclusion, rollback, and badge rendering are present and well-structured. One new Critical defect found: the override arrays store `f.id` (row UUID) instead of `f.framework_id` (stable semantic ID). This violates the schema spec, ADR-003 §5, and creates a silent data-correctness bug.

---

## Findings

### C1 — CRITICAL: Override arrays store row UUID (`f.id`) instead of stable semantic ID (`f.framework_id`)

**Files:**
- `packages/web/components/FrameworkLibraryTab.tsx`, lines 276–278, 608–609, 682–683, 697
- `packages/web/app/__tests__/components/FrameworkLibraryTab.test.tsx`, lines 53, 73, 813, etc.

**Problem:**

The `Framework` type has two identifier fields:
- `id` — the DB row UUID (changes if a framework is deleted and re-imported)
- `framework_id` — the stable semantic identifier (kebab-case, e.g., `"coordination-tax-diagnostic"`; survives re-imports because bulk upload merges on `framework_id`)

The implementation uses `f.id` (row UUID) as the override key everywhere:
- `overrides.pinned.includes(f.id)` (line 608)
- `overrides.excluded.includes(f.id)` (line 609)
- `handleToggleOverride(f.id, ...)` (lines 682, 697)
- `frameworkId` throughout `handleToggleOverride` (lines 276–279)

The schema spec (`docs/db-schema-spec.md`, line 262) documents the `framework_overrides` column as:
```json
{ "pinned": ["framework-id"], "excluded": ["framework-id"] }
```

`"framework-id"` refers to the `framework_id` text column (semantic ID), not the `id` UUID — consistent with ADR-003 §5 which states "The API layer validates that all referenced `framework_id` values exist in the parent AgentDefinition's frameworks."

**Impact:**

The backend currently stores whatever strings the client sends (no validation implemented in `update_instance`). This means it won't fail at runtime today. However:

1. **Framework re-import breaks overrides silently.** When a user deletes all frameworks and re-uploads (or triggers a merge upload that replaces a framework), the new row gets a new `id` UUID. The stored override UUID now points at nothing. `framework_id` survives this scenario because the merge key is `(agent_definition_id, framework_id)`.

2. **ADR-003 §5 validation, when implemented, will reject row UUIDs.** The ADR says write validation rejects IDs not found in the parent definition's frameworks. When that validation ships, all existing override data stored with row UUIDs will become invalid.

3. **The drift risk note in ADR-003 ("Framework override drift: If a framework is deleted... stale references silently ignored") assumes the ID is `framework_id`.** The drift mitigation relies on the semantic ID being stable across re-imports. It does not hold if row UUIDs are stored.

**Fix:**

Change all `f.id` references in the override flow to `f.framework_id`:

```tsx
// Line 608–609
const isPinned = overrides.pinned.includes(f.framework_id);
const isExcluded = overrides.excluded.includes(f.framework_id);

// Lines 682, 697
onClick={() => void handleToggleOverride(f.framework_id, isPinned ? "clear" : "pin")}
onClick={() => void handleToggleOverride(f.framework_id, isExcluded ? "clear" : "exclude")}
```

No changes needed inside `handleToggleOverride` itself — the function is ID-agnostic, it just filters and appends whatever string is passed.

**Tests must also be updated.** The `makeFramework` helper currently sets `id: "fw-1"` (or overridden values) and `framework_id: "fw-uuid-1"` (hardcoded, never overridden). All 9 KIN-372 tests rely on the mock instance returning IDs that match `f.id` (e.g., `mockFetchInstance({ pinned: ["fw-pinned"] })` where `"fw-pinned"` is the `id` field override). After the fix, tests must use `framework_id` as the override key:

1. Update `makeFramework` to expose `framework_id` as an overridable field (not hardcoded to `"fw-uuid-1"`).
2. In each test, pass matching `framework_id` values to both `makeFramework` and `mockFetchInstance`.
   Example: `makeFramework({ id: "fw-pinned", framework_id: "fw-framework-id-pinned" })` + `mockFetchInstance({ pinned: ["fw-framework-id-pinned"] })`.

---

## What Was Resolved from R1

**C1 (R1) — Test coverage:** All 9 required test cases are present:
- Pin/Exclude buttons render for owners, not for non-owners
- Pinned badge + Unpin button; Excluded badge + strikethrough + Include button
- Click Pin → PATCH with correct payload; click Exclude → PATCH with correct payload
- Mutual exclusion: pin an excluded framework removes it from excluded; exclude a pinned framework removes it from pinned
- Unpin clears from pinned array
- PATCH failure rolls back optimistic state and shows toast

Test structure is correct. `beforeEach(() => vi.resetAllMocks())` is present. Mock routing by URL + method is clean. Assertion on `body.framework_overrides.pinned` / `.excluded` contents is precise.

**I1 (R1) — Existing test mock routing:** All new tests correctly route `/instance` and `/frameworks` calls to separate mocks. Existing tests that don't exercise pin/exclude are unaffected.

---

## What Remains Correct

**Mutual exclusion logic (lines 276–279):** Filter target from both lists first, then append based on action. Cannot end up in both arrays simultaneously. "clear" action removes from both. Logic is correct regardless of which ID field is used — it's purely string filtering.

**Optimistic update + rollback (lines 283–299):** Snapshot before mutation, optimistic apply, rollback on error. Correct pattern. The shallow copy `{ ...overrides }` is safe because the arrays are replaced (not mutated) throughout.

**`togglingId` disable logic:** Both Pin and Exclude buttons on the same row are disabled during in-flight PATCH. Other rows are unaffected. Correct.

**Visual treatment:** Color-coded active states, line-through on excluded rows, title tooltips, badge rendering — all appropriate.

**Backend response reconciliation (line 292):** `setOverrides(data.framework_overrides ?? next)` correctly prefers the server-confirmed state over the optimistic state. If the backend normalizes or drops invalid IDs, the UI will reflect that.

---

## Not Reviewed

- Backend `PATCH /api/v1/agents/:id/instance` — previously reviewed. Note: backend does not currently validate `framework_id` membership as specified in ADR-003 §5. This is a pre-existing backend gap, not introduced by this ticket. A separate hardening ticket should implement the validation once the frontend is using `framework_id` correctly.
