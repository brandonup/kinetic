# Code Review — KIN-309 Active Memory UI
**Date:** 2026-03-23
**Reviewer:** Gilfoyle
**Status:** Approved (after fixes applied)

## Strengths
- Well-structured types match the spec and domain model
- Token cap display with red threshold, tabular-nums alignment is clean
- Inline CRUD pattern handles state isolation correctly; operations don't interfere
- Proposal review flow: defaults to accept, bulk toggles, cap-exceeded inline feedback
- Error handling is explicit — 422 gets specific message, network errors shown to user
- Token refetch after mutations uses server data (avoids client-side drift)

## Issues Found and Fixed

### Important — Fixed before commit

1. **ProposalReviewPanel: early `onDismiss()` call in load effect (race condition)**
   - Calling `onDismiss()` from within a useEffect created a state-update cycle with the parent
   - Fixed: removed `onDismiss()` from load effect; render-time `if (proposals.length === 0) return null` handles the empty case
   - Also removed `onDismiss` from the `useCallback` dependency array (was a stale-closure risk)

2. **ActiveMemoryPanel: stale closure in `deleteEntry` token estimation**
   - `entries.find(...)` was called after `setEntries` — while not immediately broken, captured content after the state-update intent
   - Fixed: captured `deletedContent` before `setEntries` call for clarity and correctness

3. **projects/page.tsx: `onDismiss` reset proposal count to 0**
   - If proposals were skipped due to cap, count reset to 0 meant the banner wouldn't re-appear on next settings open within the same session
   - Fixed: `onDismiss` now re-fetches proposal count from server; skipped proposals correctly cause banner to re-appear

### Minor — Accepted, not fixed
- Checkbox custom inline style (`hsl(var(--primary))`) — acceptable; Checkbox component from shadcn may not be installed
- `CHAR_SOFT_WARN = 400` hardcoded — acceptable for now; product can adjust in a future pass
- Verbose inline SVG for trash icon — readability-only concern

## Assessment
All Important issues resolved. TypeScript clean post-fixes. Ready to commit.
