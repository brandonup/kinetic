# Code Review: KIN-375 — Profile page — move Auto-fill section under Bio

**Date:** 2026-03-26
**Reviewer:** Gilfoyle
**Ticket:** KIN-375
**Verdict:** APPROVED (0 Critical, 0 Important)

---

## Summary

Pure section reorder in `packages/web/app/(app)/profile/page.tsx`. The Auto-fill from Document section was moved from between Default Model and MCP Tokens to directly after the Identity (Name + Bio) section.

## Section Order (verified)

1. Identity (Name + Bio)
2. `<Separator />`
3. Auto-fill from Document
4. `<Separator />`
5. API Keys
6. `<Separator />`
7. Default Model
8. `<Separator />`
9. MCP Tokens

All five sections present exactly once. Each bounded by `<Separator />`. No logic changes, no state changes, no handler changes. No accidental deletion or duplication.

## Minor Note (non-blocking)

The file header comment (lines 1-15) still lists the old section numbering with Linked Upload as item 4 between Default Model and MCP Tokens. Cosmetic only — does not affect runtime behavior.

## Verdict

LGTM. Clean section move matching done-when criteria.

— Gilfoyle
