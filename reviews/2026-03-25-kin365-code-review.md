# KIN-365 — Agents List Page + Create Agent Flow — Code Review

**Reviewer:** Gilfoyle
**Date:** 2026-03-25
**Verdict:** Changes requested. 0 Critical, 3 Important.

---

## Constraints Checked (from KIN-364 review)

- [x] `useAgents` hook in `lib/hooks/useAgents.ts` — confirmed
- [x] Agent split by `owner_id` client-side — confirmed
- [x] Create flow is a modal, not a route — confirmed
- [x] `instructions` defaults to `""` on `CreateAgentRequest` — confirmed (line 48, agents.py)
- [x] Empty states match spec — confirmed (text matches KIN-364 review §4)
- [x] Empty string `instructions` sent from modal — confirmed (page.tsx line 92)

---

## Architecture

Clean. Hook separation is correct, reuse-ready for the future agent selector (spec §5). Modal-not-route is right. TypeScript types are strict — no `any` in the implementation files. `parseApiError` is used for 422 errors. `void` is used properly on floating promises. Named exports used throughout.

---

## Findings

### I1 — Loading flash between profile fetch and agent fetch [Important]

**File:** `packages/web/app/(app)/agents/page.tsx` lines 246–268

**Problem:** `isLoading = profileLoading || loading`. When the profile fetch completes, `setProfileLoading(false)` fires and `setCurrentUserId(id)` fires in the same `finally` block. React batches these but the subsequent render has `profileLoading=false` and `loading=false` — so `isLoading=false` for one tick before `useAgents`' effect fires `setLoading(true)`. During that tick, the content block renders with empty `myAgents` and `publicAgents` arrays, showing both empty-state messages briefly before the agents fetch starts.

**Fix:** Initialize `loading` in `useAgents` to `true` when `currentUserId` is not null, or guard the content block to require data to have been fetched at least once before showing empty states. Simplest fix: change `const [loading, setLoading] = useState(false)` to `const [loading, setLoading] = useState(currentUserId !== null)` in `useAgents.ts`. This means loading starts `true` when a userId is already known (the hook was initialized with one), and `false` when it isn't (null case, no fetch will run).

---

### I2 — Profile fetch failure silently shows empty states [Important]

**File:** `packages/web/app/(app)/agents/page.tsx` lines 253–258

**Problem:** If the profile fetch fails (network error, 401, 500), the `catch` block logs the error but `currentUserId` stays `null` and `profileLoading` goes `false` in `finally`. Result: `useAgents(null)` never fetches, `loading` stays `false`, `error` stays `null`, `isLoading = false`. The content block renders showing "You haven't created any agents yet." and "No public agents available yet." — the user has no idea there was a failure. This violates the conventions error-handling rule: silent swallows must not mask state-changing or data-loading failures from the user.

Note: conventions.md permits read-path fail-open when documented. But here the silent failure isn't fail-open — the user cannot retry. There is no fallback. This is a user-visible dead state.

**Fix:** Add a `profileError` state. If the profile fetch fails, show an error message (similar to the agent fetch error with a "Try again" link that re-fetches the profile). At minimum, set a `profileError` boolean and render the same destructive error banner.

```tsx
const [profileError, setProfileError] = useState(false);

// in catch block:
console.error("[AgentsPage] profile fetch failed:", err);
setProfileError(true);

// in render, before the agents sections:
{profileError && !profileLoading && (
  <div className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3">
    <p className="text-sm text-destructive">Failed to load your profile. Agents cannot be displayed.</p>
    <button onClick={() => /* re-fetch profile */ } ...>Try again</button>
  </div>
)}
```

---

### I3 — No test for greyed-out agent state (spec §5) [Important]

**File:** `packages/web/app/__tests__/agents/page.test.tsx`

**Problem:** Spec §5 explicitly requires that agents without valid `instructions` are "shown greyed out and cannot be invoked." `AgentCard` implements this correctly (`opacity-60` class + "No instructions" badge when `instructions.trim().length === 0`). However, `page.test.tsx` has zero test coverage for this behavior. If someone removes the `!hasInstructions` guard in `AgentCard`, nothing catches it.

**Fix:** Add a test:

```tsx
it("shows greyed-out badge for agent with empty instructions", async () => {
  const draftAgent = makeAgent({ name: "Draft Bot", instructions: "" });
  mockProfileAndAgents([draftAgent]);

  render(<AgentsPage />);

  await waitFor(() => {
    expect(screen.getByText("Draft Bot")).toBeInTheDocument();
  });
  expect(screen.getByText(/no instructions/i)).toBeInTheDocument();
});
```

---

## Error Handling Audit

| Location | Write op? | Silent swallow? | Verdict |
|---|---|---|---|
| `useAgents` — HTTP non-ok | Read | No — sets `error` state + logs | Pass |
| `useAgents` — catch | Read | No — sets `error` state + logs | Pass |
| `CreateAgentModal` — HTTP non-ok | Write | No — sets `fieldError` | Pass |
| `CreateAgentModal` — catch | Write | No — sets `fieldError` + logs | Pass |
| `AgentsPage` — profile fetch HTTP non-ok | Read | **Yes — no error state set** | **Fail (I2)** |
| `AgentsPage` — profile fetch catch | Read | **Yes — no error state set** | **Fail (I2)** |

---

## TypeScript Audit

No `any` without comment. Strict types throughout. `AgentType` and `AgentVisibility` union types used for the form state — no raw strings. `UserProfile` imported for the profile response typing. Clean.

---

## API Backend (lines 46–52, agents.py)

`CreateAgentRequest.instructions` changed from required `str` to `str = ""` — correct per KIN-364 constraint §3. The visibility=public rejection guard for empty instructions is in the route handler (not the Pydantic model) — confirmed by the test at line 130 (`test_create_rejects_public_without_instructions`). Two new tests added: `test_create_allows_empty_instructions_for_private` and `test_create_allows_empty_instructions_explicitly`. Both are correct and sufficient. API changes approved.

---

## Test Coverage

| Area | Tests | Verdict |
|---|---|---|
| `useAgents` hook | 6 tests — fetch, split, null no-op, HTTP error, network error, refetch | Pass |
| `AgentsPage` — render | header, empty My Agents, empty Public Agents, agent cards, public agent card | Pass |
| `AgentsPage` — nav | card click → push to `/agents/:id` | Pass |
| `AgentsPage` — create modal | open, submit, name-empty validation, 422 error, empty instructions sent | Pass |
| `AgentsPage` — error/loading | agent fetch failure + retry button | Pass |
| `AgentCard` greyed-out state | **Missing** | **Fail (I3)** |
| Profile fetch failure | **Missing** | **Fail (I2 follow-on)** |

---

## Verdict

**Changes requested.** 0 Critical, 3 Important. All three items are fixable in a single pass — no architecture changes required.

Fix order:
1. I2 — add `profileError` state and error banner (prevents silent dead-state)
2. I1 — initialize `loading` to `currentUserId !== null` in `useAgents` (prevents empty-state flash)
3. I3 — add greyed-out state test in `page.test.tsx`
