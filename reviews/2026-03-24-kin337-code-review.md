# Code Review — KIN-337: Chat UI polish — model selector greyed states + agent switch markers + citations

**Date:** 2026-03-24
**Reviewer:** Gilfoyle
**Verdict:** CHANGES_REQUESTED

---

## Summary

2 Critical, 2 Important, 3 Minor findings. The citation schema is the blocking issue — `ChatCitation` and `ChatMessageRecord.citations` define a data shape that has no corresponding backing in the DB schema spec. The component tree otherwise is clean and the logic is sound, but the schema mismatch must be resolved before this ships.

---

## Findings

### [C1] CRITICAL — `ChatCitation` / `citations` field not in DB schema spec

**Files:** `lib/types/models.ts:264–268`, `components/CitationPanel.tsx:16–21`, `components/ChatMessage.tsx:19–28`

**Issue:** `ChatCitation` defines `{ chunk_id, document_title, text_preview, score }`. `ChatMessageRecord` adds a `citations: ChatCitation[]` field. Neither the `messages` table (§6) nor any other table in `db-schema-spec.md` has a `citations` column. The `retrieval_debug_logs.injected_chunks` field (§20) is the only place `{chunk_id, score, text_preview}` exists — and it does *not* include `document_title`. This creates two problems:

1. There is no column to read `citations` from. The frontend is typed against a field that doesn't exist in the DB.
2. `document_title` is not stored in `injected_chunks` per the schema spec. Either the spec is missing a join to `knowledge_base_documents`, or the field is being invented here.

**Fix required:** Either (a) add a `citations` column to the `messages` table in `db-schema-spec.md` with the correct shape (which would be a schema change that needs Gilfoyle spec sign-off), or (b) define how citations are derived at query time (join `retrieval_debug_logs.injected_chunks` → `knowledge_base_documents` to resolve `document_title`). Until the backing is defined in the spec, `ChatMessageRecord.citations` is a phantom field. This is a spec gap — do not proceed to implementation without resolution.

---

### [C2] CRITICAL — `ModelSelector` dropdown is not keyboard-accessible; missing `aria-controls` and focus trap

**File:** `components/ModelSelector.tsx:85–103, 105–165`

**Issue:** The trigger `<button>` uses `aria-expanded` correctly but is missing `aria-haspopup="listbox"` and `aria-controls` pointing to the listbox. More importantly, the dropdown has no focus trap — when opened via keyboard, Tab moves focus out of the dropdown without closing it, leaving it open in a broken state. The `role="listbox"` div also has no `tabIndex` and its `role="option"` children are `<button>` elements — this is an ARIA pattern conflict. `role="option"` elements are expected to be non-interactive children of a `listbox`; putting `role="option"` on a `<button>` is invalid HTML/ARIA. Either use the `<select>` pattern, a proper Radix `Select` component (which the stack already includes), or implement a proper `Combobox` with `role="combobox"` / `role="listbox"` / `role="option"` using `aria-activedescendant`.

**Fix options:**
- Replace with Radix `Select` (already in the shadcn/ui stack) — handles keyboard nav, focus trap, and ARIA natively.
- Or: fix `role="listbox"` → add `tabIndex={0}`, change item roles from `option` on `<button>` to wrapping with correct semantics.

---

### [I1] IMPORTANT — `ModelSelector` dropdown does not close on outside click or Escape

**File:** `components/ModelSelector.tsx:105`

**Issue:** `open` state is toggled by the trigger button only. No `useEffect` adds a document-level click listener or `keydown` handler for Escape. In production this means the dropdown stays open after the user clicks elsewhere in the UI, which is disorienting and UX-breaking.

**Fix:** Add `useEffect(() => { ... }, [open])` that attaches a `mousedown` listener on `document` to close on outside click, and a `keydown` listener to close on `Escape`. Or: resolve this by switching to Radix `Select` (see C2) which handles this natively.

---

### [I2] IMPORTANT — `ChatMessageRecord` in `models.ts` uses `agent_name` but `messages` table has no such column

**Files:** `lib/types/models.ts:256`, `components/ChatMessage.tsx:24`

**Issue:** `ChatMessageRecord.agent_name: string | null` — the `messages` table (§6) has `agent_definition_id` but no `agent_name` column. `agent_name` must be resolved by joining to `agent_definitions`. This is correct behavior (it should be a join result), but it must be declared explicitly: `agent_name` is a computed/joined field, not a DB column, and should be annotated as such in the type or comment. Without this clarity, the next implementer will look for `agent_name` in the `messages` table and not find it, then invent it as a column.

**Fix:** Add a comment to `ChatMessageRecord` noting that `agent_name` is resolved via join on `agent_definitions.name` at the API layer, not stored in the `messages` table. This is a documentation fix but it's Important because ambiguity here will cause a schema mismatch defect in the conversation-fetch API implementation.

---

### [M1] Minor — `CitationPanel.tsx` defines `Citation` interface separately from `ChatCitation` in `models.ts`

**Files:** `components/CitationPanel.tsx:16–21`, `lib/types/models.ts:264–268`

**Issue:** `Citation` and `ChatCitation` are structurally identical (`chunk_id`, `document_title`, `text_preview`, `score`). Two definitions of the same shape will drift. `ChatMessage.tsx` imports `Citation` from `CitationPanel` and uses it in `ChatMessageData` — `models.ts` exports `ChatCitation` separately. Pick one canonical type and re-export.

**Fix:** Delete `Citation` from `CitationPanel.tsx`. Import `ChatCitation` from `@/lib/types/models` and use it in both `CitationPanel` and `ChatMessage`.

---

### [M2] Minor — `ChatThread.tsx` uses `React.ReactNode[]` without importing `React`

**File:** `components/ChatThread.tsx:27`

**Issue:** `const elements: React.ReactNode[] = []` — `React` is referenced but not imported. In Next.js 14 (App Router) with the `react/react-in-jsx-scope` rule off, JSX works fine without the import, but type-referencing `React.ReactNode` explicitly still requires the import or substituting `import type { ReactNode } from "react"`.

**Fix:** Add `import type { ReactNode } from "react"` and change the type annotation to `ReactNode[]`.

---

### [M3] Minor — `AgentSwitchMarker` is missing `"use client"` directive but is imported client-side

**File:** `components/AgentSwitchMarker.tsx:1`

**Issue:** The file has `"use client"` at line 1 — this is actually present and correct. *(No defect — marking as checked.)*

*(Self-corrected during review — not a finding.)*

---

## Positive observations

- **Agent switch logic in `ChatThread`** is correct: `prevAgentId` initialized to `undefined` so the first assistant message never triggers a marker. The `undefined ≠ null` distinction is intentional and correct.
- **Disabled model behavior** in `ModelSelector` is correctly doubled: `disabled` attribute on the button AND `onClick` guard with `if (hasKey)` — redundant but correct for defense.
- **Test coverage** is strong for the features implemented. All critical paths (empty state, agent switch, citation expand/collapse, disabled model) are exercised.
- **`aria-expanded`** and `aria-label` usage is correct on `CitationPanel` toggle and `AgentSwitchMarker`.
- **`toLocaleTimeString`** without locale arg is intentional (browser locale) — acceptable for MVP.

---

## Schema cross-reference summary

| Field | DB column? | Match? |
|---|---|---|
| `messages.agent_definition_id` | Yes (§6) | Match |
| `messages.model` | Yes (§6) | Match |
| `messages.token_count` | Yes (§6) | Match |
| `messages.sequence` | Yes (§6) | Match |
| `messages.agent_name` | No — join field | Must be documented (I2) |
| `messages.citations` | No column exists | CRITICAL gap (C1) |
| `retrieval_debug_logs.injected_chunks` shape: `{chunk_id, score, text_preview}` | Yes (§20) | `document_title` absent in spec (C1) |
