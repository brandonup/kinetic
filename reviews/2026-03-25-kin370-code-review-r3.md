# Code Review — KIN-370 Round 3: Frontend Tests
**Date:** 2026-03-25
**Reviewer:** Gilfoyle
**Ticket:** KIN-370 — [Dinesh] Project KB — document upload UI
**Files reviewed:**
- `packages/web/app/__tests__/components/KnowledgeBaseTab.test.tsx`
- `packages/web/app/__tests__/projects/page.test.tsx`

---

## Context

R1 and R2 covered the backend API endpoints and Python tests. R3 covers the new frontend test suites written in this session. Both files are new; there is no prior frontend test coverage for KnowledgeBaseTab or the Projects page KB section.

---

## Findings

**None.**

---

## Verification

Fresh test run confirmed: `./node_modules/.bin/vitest run app/__tests__/components/KnowledgeBaseTab.test.tsx app/__tests__/projects/page.test.tsx` → **9 passed, 0 failed**.

The pre-existing `FrameworkLibraryTab.test.tsx` failure (`successful create appends new framework row to table`) is unrelated — both `FrameworkLibraryTab.tsx` and its test appear in `git diff --name-only` as pre-modified before this session. Not a regression from KIN-370.

---

## Coverage Assessment

### KnowledgeBaseTab.test.tsx (6 tests)

| Test | Path covered |
|---|---|
| null KB renders message, no upload button | `knowledgeBaseId === null` early return |
| empty documents state + upload button | Happy path, no docs |
| document rows render | Happy path, with docs |
| unsupported file type → error, no POST | Client-side MIME type validation |
| file too large → error, no POST | Client-side size validation (25 MB) |
| valid upload → POST called, FormData contains `knowledge_base_id` | Upload flow, correct payload |

All material client-side validation paths are covered. The `knowledge_base_id` FormData assertion is particularly valuable — it pins the integration contract between the frontend and the backend upload endpoint.

### projects/page.test.tsx (3 tests)

| Test | Path covered |
|---|---|
| KB exists → KnowledgeBaseTab renders with correct `knowledgeBaseId` | Happy path wiring |
| No KB (404) → Create KB button shown, KnowledgeBaseTab absent | Empty state |
| Create KB clicked → POST called, KnowledgeBaseTab appears with new ID | Create flow end-to-end |

Correct isolation strategy: `KnowledgeBaseTab` is stubbed in these tests so the page-level wiring logic is tested independently from the component's internal behavior. The `data-kb-id` attribute assertion on the stub is a clean way to verify prop threading without DOM coupling.

---

## What's Good

- **Mock isolation is correct.** `DocumentRow` stubbed in `KnowledgeBaseTab.test.tsx` to avoid nested `useDocumentStatus` polling timers. `KnowledgeBaseTab`, `ActiveMemoryPanel`, and `ProposalReviewPanel` all stubbed in `projects/page.test.tsx` — each test file owns exactly what it tests.
- **`mockEmptyKb` pattern is solid.** Sets a fallback `mockImplementation` then overrides with `mockReturnValueOnce` for ordered calls — correct for the parallel `Promise.all([docsRes, foldersRes])` in `fetchData`.
- **No false positives.** Both validation tests verify that `apiFetch` was NOT called with the upload endpoint after rejection — catches the failure mode where validation runs but upload proceeds anyway.
- **FormData payload assertion** at line 222–223 of `KnowledgeBaseTab.test.tsx` verifies `knowledge_base_id` is sent — this is the field that routes the document to the correct KB on the backend. Pinning this in a test prevents silent breakage if the field name changes.
- **`beforeEach(() => vi.clearAllMocks())`** in every describe block — no mock state leaks between tests.
- **File naming follows conventions.** `KnowledgeBaseTab.test.tsx` in `components/`, `page.test.tsx` in `projects/` — consistent with the existing test structure.

---

## Verdict

**APPROVED.** 9 tests, 0 failures. Coverage is complete for all spec-required paths: file type validation, size validation, upload flow, null KB state, no-KB create flow, KB wiring. No issues.
