# Code Review — KIN-365: Agent list page (R2)

**Date:** 2026-03-26
**Reviewer:** Gilfoyle
**Verdict:** APPROVED
**Critical:** 0 | **Important:** 0

---

## R1 Finding Resolution

All three R1 findings are resolved.

### I1 — Loading flash (RESOLVED)

`useAgents.ts` line 34:

```typescript
const [loading, setLoading] = useState(currentUserId !== null);
```

`loading` initializes to `true` when a userId is available, preventing the empty-state flash between profile fetch completing and agents fetch starting. When `currentUserId` is `null` (profile not yet loaded), `loading` is `false` — correct, because the agents fetch will not fire until the profile resolves and provides a userId. The flash path is closed.

### I2 — Profile fetch failure silent (RESOLVED)

`agents/page.tsx` implements `profileError` state with a "Failed to load your profile" message and "Try again" button (`fetchProfile` wrapped in `useCallback`, called from useEffect). On profile fetch failure, the page shows the error state and suppresses all agent content (no empty state rendered). Verified by test at lines 390–407 of `page.test.tsx`:

- `"shows profile error state when profile fetch fails"` — asserts error message and "Try again" text appear, asserts empty-state copy is absent. Correct.

### I3 — Greyed-out badge test missing (RESOLVED)

`page.test.tsx` lines 378–388:

```typescript
it("shows greyed-out badge for agent with empty instructions", async () => {
  const draftAgent = makeAgent({ name: "Draft Bot", instructions: "" });
  ...
  expect(screen.getByText(/no instructions/i)).toBeInTheDocument();
});
```

Test exists and covers the badge render for agents with empty instructions. Correct.

---

## KIN-381 Scope Included

The page includes KIN-381 additions (AgentCard with Chat/Settings/Delete actions, DeleteAgentDialog, search filter) that were not part of the original KIN-365 scope. These are also covered by tests:

- `"navigates to agent settings when Settings button is clicked"` — `agent-settings-[id]` data-testid nav
- `"navigates to agent chat when Chat button is clicked"` — `agent-chat-[id]` data-testid nav
- `"shows delete button only for owned agents"` — non-owner agents have no delete button
- `"opens delete confirmation dialog and deletes agent"` — full DELETE + refetch cycle tested
- `"filters agents by search query"` — search filters both sections correctly

All patterns follow established conventions. Delete is owner-gated, confirmation dialog present, DELETE fires refetch. LGTM.

---

## Summary

All R1 findings resolved: loading flash eliminated via `useState` initialization, profile error surfaces explicitly with retry, greyed-out badge test added. The KIN-381 additions are clean and well-tested. APPROVED.

— Gilfoyle
