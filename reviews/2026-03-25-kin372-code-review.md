# Code Review: KIN-372 — Framework Library Pin/Exclude UI

**Date:** 2026-03-25
**Reviewer:** Gilfoyle
**File:** `packages/web/components/FrameworkLibraryTab.tsx`
**Verdict:** CHANGES REQUESTED

---

## Summary

Frontend-only change adding pin/exclude override controls to the framework library table. The mutual exclusion logic and optimistic update pattern are both correct. TypeScript types align with existing `FrameworkOverrides` interface and backend contract. The visual treatment is clean and accessible. One Critical defect blocks approval: no tests for the new KIN-372 behavior, and the mount-time `loadOverrides` call silently breaks the entire existing test suite by introducing an unhandled `apiFetch` call that all prior mocks don't account for.

---

## Findings

### C1 — CRITICAL: Zero test coverage for KIN-372 functionality, and existing tests now broken

**File:** `packages/web/app/__tests__/components/FrameworkLibraryTab.test.tsx`

Every existing test in the file mocks `apiFetch` with a single `mockImplementation(() => mockFetchFrameworks([...]))`. The component now fires two `apiFetch` calls on mount: `GET /frameworks` and `GET /instance`. The existing mock returns a frameworks response for both calls. The instance call receives a frameworks-shaped response (`{ frameworks: [...] }`) and attempts `data.framework_overrides` — which is undefined. The fallback `?? { pinned: [], excluded: [] }` silently swallows the mismatch, so tests don't visibly fail, but no test verifies that overrides are loaded or rendered correctly.

More critically: no tests exist for any KIN-372 behavior:
- Pin button click → optimistic update → PATCH
- Exclude button click → mutual exclusion (pinned → cleared, excluded set)
- Rollback on PATCH error
- Visual badges ("Pinned" / "Excluded") render when state is active
- Disabled state while toggling
- `isOwner=false` hides Pin/Exclude (the Actions column is already hidden, so this is inherited — but still worth one explicit assertion)

The conventions file is unambiguous: "Every feature ships with tests. No exceptions." This is a blocking defect.

**Fix:** Add a `describe("KIN-372: pin/exclude overrides")` block to the existing test file. Update all existing `beforeEach` mocks to route the `/instance` GET to a separate mock response (e.g., `mockFetchInstance({ pinned: [], excluded: [] })`). Minimum required tests:

1. On mount: loads overrides from `/api/v1/agents/:id/instance`; rows with pinned/excluded IDs render badges
2. Pin click: PATCH called with `{ framework_overrides: { pinned: [id], excluded: [] } }`; "Pinned" badge appears; button label changes to "Unpin"
3. Clicking Pin on an already-excluded framework: excluded list cleared, pinned set — mutual exclusion enforced
4. Exclude click: PATCH called correctly; "Excluded" badge + opacity-50 + line-through apply
5. PATCH error: rollback restores prior state; toast fires
6. `togglingId` disables both Pin and Exclude for the toggling row only (not other rows)

---

### I1 — IMPORTANT: Existing tests silently pass but exercise incorrect mock routing after mount-call addition

**File:** `packages/web/app/__tests__/components/FrameworkLibraryTab.test.tsx`, lines 166, 185, etc.

All `mockApiFetch.mockImplementation(() => mockFetchFrameworks([...]))` setups now service both the frameworks GET and the instance GET with the same response. The instance path gets `{ frameworks: [...] }` instead of `{ framework_overrides: {...} }`. The `?? { pinned: [], excluded: [] }` fallback masks this silently. Tests pass for the wrong reason — they're not verifying that override state is cleanly absent, they're surviving a mocked response mismatch.

This is downstream of C1. Fixing C1 (adding per-call mock routing) resolves this automatically. Flagged explicitly so Dinesh doesn't miss it when updating the mock setup.

---

## What's Correct

**Mutual exclusion logic (lines 276–279):** The pattern of filtering the target ID from both lists first, then conditionally adding to the relevant list based on `action`, is correct. A framework cannot end up in both `pinned` and `excluded` simultaneously regardless of call order. The "clear" action correctly removes from both.

**Optimistic update + rollback (lines 283–299):** Snapshot taken before mutation (`const prev = { ...overrides }`), optimistic state applied before the await, rollback on any non-ok response or thrown error. The shallow copy of `overrides` is sufficient here because `pinned` and `excluded` are string arrays — no nested mutation risk.

**TypeScript types:** `FrameworkOverrides` imported from `@/lib/types/models` and used throughout. The PATCH body uses `UpdateAgentInstanceRequest`-compatible shape (`{ framework_overrides: next }`). Backend response is read via `data.framework_overrides ?? next`, which is correct — backend returns the full instance object.

**Backend contract alignment:** `GET /api/v1/agents/:id/instance` returns the full `agent_instances` row including `framework_overrides`. `PATCH /api/v1/agents/:id/instance` accepts `{ framework_overrides: FrameworkOverrides }` and returns the updated row. Frontend matches both contracts exactly.

**UX treatment:** `togglingId === f.id` disables both Pin and Exclude on the same row during in-flight requests. Color-coded active states (blue/pin, red/exclude), line-through on excluded rows, and title tooltips are all appropriate. The `colSpan` on the empty filter row correctly accounts for the Actions column visibility (`isOwner ? 6 : 5`).

---

## Not Reviewed

- Backend (KIN-288) — already shipped and reviewed separately.
