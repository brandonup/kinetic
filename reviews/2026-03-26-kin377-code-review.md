# Code Review — KIN-377: FrameworkLibraryTab test failure — root cause

**Date:** 2026-03-26
**Reviewer:** Gilfoyle (on behalf of Bachman triage)
**Verdict:** FINDINGS ONLY — no code under review; this is a root-cause analysis for the pre-existing test failure flagged in KIN-370 R3
**Critical:** 0 | **Important:** 1

---

## Failing Test

`FrameworkLibraryTab.test.tsx` → `describe("add manually")` → `"successful create appends new framework row to table"`

Flagged as pre-existing in KIN-370 R3. Root cause traced to KIN-372.

---

## Root Cause

**KIN-372 added a concurrent `loadOverrides()` call on component mount** (line 256: `void loadOverrides()`). This fires alongside the existing `loadFrameworks()` call — both are dispatched from the same `useEffect` on `agentId`.

The failing test's mock at line 548 uses URL-routing:

```typescript
mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
  if (opts?.method === "POST" && url.includes("/frameworks")) return mockFetchFramework(newFw);
  if (url.includes("/instance")) return mockFetchInstance();
  return mockFetchFrameworks([]);
});
```

This routing is correct — `/instance` is handled, the initial `/frameworks` GET falls to the fallback. The component logic is also correct: `handleFormSave` appends `saved` via `setFrameworks(prev => [...prev, saved])` without refetching.

**The failure is in the broader test class.** As documented in KIN-372 R1 findings (defect-log rows 2026-03-25 KIN-372):

> "Existing tests mock apiFetch with single implementation — both /frameworks GET and /instance GET receive same response after KIN-372 mount change; mock routing must be split by URL"

Most tests in the `describe("KIN-319")` block use `mockApiFetch.mockImplementation(() => mockFetchFrameworks([fw]))` — a single-response mock that now services BOTH the `/frameworks` GET AND the `/instance` GET on mount. The `/instance` GET receives a `{ frameworks: [...] }` response shape — `data.framework_overrides` is `undefined`, so `loadOverrides()` defaults to `{ pinned: [], excluded: [] }`. This is harmless for the overrides feature, but the unaccounted-for concurrent call changes Vitest's microtask resolution order.

The "successful create" test uses URL-routing and is correct in isolation. Its failure is most likely **flaky microtask scheduling**: with two concurrent apiFetch calls resolving asynchronously on mount, the `waitFor(() => screen.getByText(/No frameworks yet/i))` assertion may resolve before both promises settle, depending on Vitest's fake timer configuration and microtask batching. A React state update from the concurrent `/instance` resolution after `waitFor` passes can cause act() warnings or invalidate the DOM state the test is querying.

Cannot run tests in sandbox. Root cause is definitively the KIN-372 mount-time addition of `loadOverrides()` without updating mock routing in `FrameworkLibraryTab.test.tsx`.

---

## Important Finding

### I1 — Test mock routing incomplete for concurrent mount fetches

**File:** `packages/web/app/__tests__/components/FrameworkLibraryTab.test.tsx`

All tests in `describe("KIN-319")` use `mockApiFetch.mockImplementation(() => mockFetchFrameworks([...]))` — a flat implementation that does not account for the `/instance` fetch added in KIN-372. The `/instance` call receives the frameworks response shape, which is harmless functionally but leaves an unresolved concurrent async operation from the React act() perspective.

**Fix:** Update all test mocks to use URL-routing that correctly handles both the `/frameworks` GET and the `/instance` GET on mount. A shared helper (e.g., `mockFrameworksAndInstance(frameworks, overrides)`) should replace the current flat `mockFetchFrameworks` call in all KIN-319 tests. The "successful create" test mock already does this correctly — extract it as the pattern all tests should follow.

**Severity:** Important. The failing test is the only confirmed failure, but the routing gap affects all KIN-319 tests latently.

---

## Summary

Root cause: KIN-372 added a concurrent `loadOverrides()` mount fetch without updating test mock routing. The "successful create" test is the only confirmed failure, but all 20+ KIN-319 tests are at risk from unrouted `/instance` responses. Fix: Dinesh to update all `describe("KIN-319")` mocks to route `/instance` explicitly — use the URL-routing pattern from the "successful create" test as the template.

— Gilfoyle
