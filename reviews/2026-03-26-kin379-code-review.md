# Code Review — KIN-379: KB page — document list with delete and delete-all UI

**Date:** 2026-03-26
**Reviewer:** Gilfoyle
**Verdict:** APPROVED

---

## Files Reviewed

- `projects/kinetic/packages/web/components/DocumentRow.tsx`
- `projects/kinetic/packages/web/components/KnowledgeBaseTab.tsx`

---

## Summary

Clean implementation. All ticket requirements met. Patterns match `FrameworkLibraryTab.tsx` (the canonical reference for inline modals and toast usage). No Critical findings, one Minor note.

---

## Checklist

| Check | Result |
|---|---|
| Fragment wrapping correct (both components) | PASS |
| Delete button disabled during extracting/chunking/embedding | PASS |
| Delete button disabled during in-flight delete | PASS |
| Confirmation dialog on delete (DocumentRow) | PASS |
| Confirmation dialog shows document title | PASS |
| onDeleted callback called on success | PASS |
| Delete All button hidden when 0 documents | PASS |
| Delete All confirmation shows document count | PASS |
| 409 handling — "still processing" toast | PASS |
| Error handling with toasts (KnowledgeBaseTab) | PASS |
| Inline error state for per-document delete errors | PASS |
| No silent error swallowing | PASS |
| Inline modal pattern matches FrameworkLibraryTab | PASS |
| useCallback dependency arrays correct | PASS |

---

## Findings

### Minor — DocumentRow: stale deleteError visible when re-opening confirmation

**File:** `DocumentRow.tsx`, line 182
**Issue:** Clicking the Delete button calls `setShowDeleteConfirm(true)` but does not clear `deleteError`. If a prior delete attempt failed, the error message is visible below the row while the new confirmation dialog is open. The error is only cleared when `handleDelete` begins executing (line 86). Low user impact — the dialog opens correctly and the next attempt will clear it — but technically stale state is visible.
**Fix (optional):** Change the button's onClick to `() => { setDeleteError(null); setShowDeleteConfirm(true); }`.
**Severity:** Minor. Not blocking.

---

## Pattern Notes

- **Inline modal vs toast split:** DocumentRow uses inline `deleteError` state (matching the existing retry error pattern in the same component). KnowledgeBaseTab uses toasts for delete-all (appropriate — modal closes before the operation resolves in the success path). Split is intentional and consistent.
- **`finally` closes dialog:** Both components close their confirmation dialogs in `finally`, not only on success. This matches FrameworkLibraryTab behavior (dialog state always cleared; errors surface via toast or inline state). Correct.
- **`ACTIVE_INGESTION_STATUSES` constant:** Defined at module scope in DocumentRow. The backend has a duplicate constant in `documents.py` and `kb_management.py` (flagged in KIN-378 review as tech debt). The frontend constant is a separate concern — correct to define it here.
