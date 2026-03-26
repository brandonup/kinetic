# KIN-370: Project KB — Document Upload UI — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Write tests proving the Project KB section works end-to-end — renders the shared upload component, handles the no-KB case, validates file type/size, and completes the upload flow.

**Architecture:** The implementation is already complete. `projects/page.tsx` already uses `KnowledgeBaseTab` (the shared component from KIN-368), handles the no-KB case with a Create KB button, and delegates all upload/validation logic to `KnowledgeBaseTab`. Two test suites are needed: (1) `KnowledgeBaseTab` unit tests covering the component's own behavior, and (2) `ProjectsPage` KB section integration tests covering the page-level wiring.

**Tech Stack:** Vitest, `@testing-library/react`, `@testing-library/user-event`, `jsdom`. Run via `./node_modules/.bin/vitest run` from `packages/web/`.

---

## Context: What Already Exists

- `packages/web/components/KnowledgeBaseTab.tsx` — shared upload component. Upload goes to `POST /api/v1/documents/upload` (not `/knowledge-bases/:id/documents`). Validates MIME type + extension + size client-side before submitting.
- `packages/web/app/(app)/projects/page.tsx` — Project page. Opens settings panel per project. Lazy-loads KB on `startSettings()`. Shows `KnowledgeBaseTab` when `kbId` exists; shows "Create Knowledge Base" button when not.
- Test pattern: see `app/__tests__/components/DocumentRow.test.tsx` and `app/__tests__/agents/[id]/page.test.tsx`. Mock `apiFetch` at module level before importing the component.
- Baseline: **144 tests passing, 1 skipped**.

---

## Task 1: KnowledgeBaseTab — Component Tests

**File to create:** `packages/web/app/__tests__/components/KnowledgeBaseTab.test.tsx`

**Mocks needed:**
- `@/lib/api` → `{ apiFetch: vi.fn(), parseApiError: vi.fn() }`
- `@/components/DocumentRow` → stub `() => <div data-testid="document-row">{props.title}</div>`
- `@/lib/hooks/useDocumentStatus` → not needed (DocumentRow is stubbed)

**Setup helper:** `mockFetchOk(body)` and `mockFetchErr(status, detail)` — same pattern as `DocumentRow.test.tsx`.

**Default fetch sequence for most tests:** First call = documents list (`{ documents: [] }`), second call = folders list (`{ folders: [] }`).

### Step 1: Write the file with these test cases

**Test 1 — renders with no documents:**
- `apiFetch` returns empty documents + empty folders.
- Assert: "No documents uploaded yet." is visible; "Upload documents" button is present.

**Test 2 — renders document rows when documents exist:**
- `apiFetch` returns `{ documents: [{ id: "doc-1", title: "report.pdf", file_type: "application/pdf", status: "completed", folder_id: null, tags: [], file_size_bytes: 1024, created_at: "..." }] }` for docs, empty folders.
- Assert: stub `data-testid="document-row"` appears; `"1 document"` count text is visible.

**Test 3 — file type validation error (unsupported type):**
- Render with `knowledgeBaseId="kb-1"`.
- Simulate selecting a `.exe` file: `new File(["x"], "virus.exe", { type: "application/octet-stream" })`.
- Click "Upload documents" button to open file input (use `fireEvent.change` on the hidden input directly).
- Assert: error text matching `/unsupported file type/i` appears; `apiFetch` is NOT called with `POST`.

**Test 4 — file size validation error (over 25 MB):**
- Simulate selecting a file with `size > 25 * 1024 * 1024`.
- Since `File` constructor doesn't set size from content, use `Object.defineProperty(file, "size", { value: 26 * 1024 * 1024 })`.
- Assert: error text matching `/file too large/i` appears; no upload call made.

**Test 5 — successful upload flow:**
- `apiFetch` mock: docs/folders fetch returns empty; upload POST returns `{ id: "doc-new", status: "pending" }`; then docs refetch returns the new doc.
- Simulate selecting a valid PDF file (`type: "application/pdf"`).
- Assert: `apiFetch` called with `POST` to `/api/v1/documents/upload`; after upload, `apiFetch` called again for the docs list (refetch).

**Test 6 — renders null knowledgeBaseId gracefully:**
- Render `<KnowledgeBaseTab knowledgeBaseId={null} />`.
- Assert: "No Knowledge Base attached" text visible; "Upload documents" button is NOT present.

### Step 2: Run tests to verify they all pass

```bash
cd packages/web && ./node_modules/.bin/vitest run app/__tests__/components/KnowledgeBaseTab.test.tsx
```

Expected: 6 passed.

---

## Task 2: ProjectsPage — KB Section Tests

**File to create:** `packages/web/app/__tests__/projects/page.test.tsx`

**Mocks needed:**
- `@/lib/api` → `{ apiFetch: vi.fn(), parseApiError: vi.fn() }`
- `@/components/ui/use-toast` → `{ useToast: () => ({ toast: vi.fn() }) }`
- `@/components/KnowledgeBaseTab` → stub `({ knowledgeBaseId }) => <div data-testid="kb-tab">{knowledgeBaseId}</div>`
- `@/components/ActiveMemoryPanel` → stub `() => <div data-testid="am-panel" />`
- `@/components/ProposalReviewPanel` → stub `() => <div data-testid="proposal-panel" />`

**Default fetch sequence:** `GET /api/v1/companies` returns `[{ id: "co-1", name: "Acme" }]`; `GET /api/v1/projects` returns `{ projects: [{ id: "proj-1", name: "Alpha", company_id: "co-1", instructions: null }] }`.

**When Settings opens**, `apiFetch` is also called for:
- `GET /api/v1/active-memory/proposals?project_id=proj-1` → `{ proposals: [] }`
- `GET /api/v1/projects/proj-1/knowledge-base` → either `{ id: "kb-1" }` or 404

### Step 1: Write the file with these test cases

**Test 1 — KB section shows KnowledgeBaseTab when KB exists:**
- Mock: KB fetch returns `{ id: "kb-1" }`.
- Click "Settings" on Alpha.
- Wait for "Knowledge Base" label to appear.
- Assert: `data-testid="kb-tab"` is in the DOM (i.e., `KnowledgeBaseTab` was rendered).

**Test 2 — KB section shows Create KB button when no KB:**
- Mock: KB fetch returns `{ ok: false, status: 404 }`.
- Click "Settings" on Alpha.
- Wait for "Knowledge Base" label.
- Assert: "Create Knowledge Base" button is visible; `data-testid="kb-tab"` is NOT in DOM.

**Test 3 — Create KB button calls POST and then shows KnowledgeBaseTab:**
- Mock: KB fetch returns 404 initially; `POST /api/v1/projects/proj-1/knowledge-base` returns `{ id: "kb-new" }`.
- Open Settings, click "Create Knowledge Base".
- Assert: `apiFetch` called with `POST` matching `projects/proj-1/knowledge-base`; after call, `data-testid="kb-tab"` appears.

**Test 4 — KB section shows loading state briefly:**
- Mock: KB fetch is a promise that never resolves for this test, or resolves after a tick.
- Open Settings, immediately assert "Loading…" text is visible (before KB fetch resolves).
- (Optional — skip if timing is flaky in jsdom; mark with `// timing-sensitive`)

### Step 2: Run tests to verify they all pass

```bash
cd packages/web && ./node_modules/.bin/vitest run "app/__tests__/projects/page.test.tsx"
```

Expected: 3–4 passed.

---

## Task 3: Full Suite Verification

### Step 1: Run the full test suite

```bash
cd packages/web && ./node_modules/.bin/vitest run
```

Expected: **153+ passed** (144 baseline + 6 KnowledgeBaseTab + 3–4 ProjectsPage), 1 skipped. Zero failures.

### Step 2: Commit

Generate commit script at `/private/tmp/claude-501/commit_kin370.sh` — sandbox blocks git index directly.

```
feat: add KIN-370 tests — Project KB upload UI (KnowledgeBaseTab + ProjectsPage KB section)
```

Files to stage:
- `packages/web/app/__tests__/components/KnowledgeBaseTab.test.tsx`
- `packages/web/app/__tests__/projects/page.test.tsx`

---

## Done When

- `KnowledgeBaseTab.test.tsx` exists with 6 tests covering: renders, document rows, file type rejection, size rejection, upload flow, null KB.
- `projects/page.test.tsx` KB section tests cover: shows tab when KB exists, shows create button when no KB, create call wires KB.
- Full suite passes with zero new failures.
- KIN-370 moved to Code Review with comment listing test count and files.
