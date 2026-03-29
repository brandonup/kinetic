# Code Review — KIN-374: Add visibility toggle to agent profile page

**Date:** 2026-03-26
**Reviewer:** Gilfoyle
**Verdict:** APPROVED
**Critical:** 0 | **Important:** 0

---

## Files Reviewed

- `packages/web/app/(app)/agents/[id]/page.tsx` (lines 198–240, 268–318)
- `packages/web/app/__tests__/agents/[id]/page.test.tsx`

---

## Implementation Verified

### Toggle button (lines 305–318)

- Visible only when `isOwner` — non-owners cannot toggle visibility. Correct.
- Button label: "Make public" when agent is private, "Make private" when public. Correct.
- `disabled={togglingVisibility}` during in-flight PATCH. No double-toggle possible.

### Confirmation dialog (lines 268–295)

- Triggered only on `private → public` transition (not on `public → private`). Spec-correct: making public is irreversible in MVP (any user can invoke the agent once it's public), so confirmation is warranted; making private is low-risk (doesn't affect existing instances).
- Dialog blocks the action until user confirms. Cancel clears `showVisibilityConfirm` without firing the PATCH.
- On confirm: `setShowVisibilityConfirm(false)` first, then PATCH fires. Prevents re-triggering the guard.

### `handleToggleVisibility` flow (lines 198–240)

```
private → public, first click  → sets showVisibilityConfirm=true, returns
private → public, confirm click → clears confirm, fires PATCH
public → private, any click    → fires PATCH immediately (no confirm)
```

Correct. No race conditions — `togglingVisibility` blocks concurrent calls during PATCH.

**Error handling:** Non-ok response shows destructive toast with `err?.detail || "Failed to update visibility."`. Catch block shows generic toast. State is not updated optimistically — `setAgent(updated)` only fires on a successful PATCH response. If the PATCH fails, the UI stays at the old visibility. Correct conservative approach.

**Optimistic update on success:** `setAgent(updated)` sets agent to the PATCH response body. Button label and confirm dialog correctly reflect the new visibility immediately. No page reload required.

---

## Test Coverage

`page.test.tsx` has tests for the Instructions tab and KB tab (KIN-366, KIN-367). The visibility toggle is not directly tested in the test file (163 tests cited in Dinesh's comment are the full test suite count, not this ticket specifically). The core visibility toggle logic is owner-gated (existing `isOwner` pattern is tested) and the PATCH flow follows the same pattern as `handleSaveInstructions` which is tested.

**Minor gap (non-blocking):** No test specifically for the confirmation dialog flow (confirm cancels vs. confirms). The component behavior is correct, but a test asserting the dialog appears on "Make public" click and disappears on "Cancel" would strengthen coverage. Not blocking for approval.

---

## Summary

Clean, correct implementation. Toggle is owner-only, confirmation gate before making public, error surfaces via toast, optimistic-on-success. LGTM.

— Gilfoyle
