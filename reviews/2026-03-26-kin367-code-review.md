# Code Review — KIN-367: Agent KB tab — missing "Create Knowledge Base" CTA in empty state

**Date:** 2026-03-26
**Reviewer:** Gilfoyle
**Verdict:** APPROVED
**Critical:** 0 | **Important:** 0

---

## Files Reviewed

- `packages/web/app/(app)/agents/[id]/page.tsx` (lines 388–408, KB tab branch)
- `packages/web/app/__tests__/agents/[id]/page.test.tsx` (lines 189–223, KIN-367 tests)

---

## Implementation Verified

KB tab renders three states correctly:

1. **KB exists** (`kbId` set): renders `<KnowledgeBaseTab knowledgeBaseId={kbId} />` — correct.
2. **No KB + owner**: centered empty state with message + "Create Knowledge Base" button. `handleCreateKnowledgeBase` calls `POST /api/v1/agents/:id/knowledge-base`, sets `kbId` on success, shows confirmation toast. Error case shows destructive toast. No silent swallow.
3. **No KB + non-owner**: message only, no CTA — correct (non-owners cannot create KBs).

**Test coverage:**
- `shows Create Knowledge Base button when no KB attached and user is owner` — verified (lines 194–208)
- `hides Create Knowledge Base button for non-owner` — verified (lines 210–223)

Both tests use `kbId = null` in `mockFetchResponses` to simulate the no-KB state. Mock correctly returns 404 for the KB fetch.

---

## Notes

`handleCreateKnowledgeBase` optimistically updates `kbId` from the POST response (the newly created KB id). This means the tab immediately transitions from empty-state to `<KnowledgeBaseTab>` without a page reload. Correct UX.

The `creatingKb` loading state disables the button during the in-flight POST, preventing double-creates. Correct.

LGTM.

— Gilfoyle
