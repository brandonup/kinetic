# Code Review — KIN-337: Chat UI polish — model selector greyed states + agent switch markers + citations (Round 2)

**Date:** 2026-03-24
**Reviewer:** Gilfoyle
**Verdict:** CHANGES_REQUESTED

---

## Summary

All R1 findings (C1, C2, I1, I2) are addressed and closed. One new Important finding: the `ModelSelector` ARIA listbox implementation is missing `aria-activedescendant`, which is required by the ARIA spec for the keyboard pattern chosen. Screen readers cannot announce the currently focused option during ArrowUp/Down navigation.

---

## R1 Finding Resolution

| Finding | Status | Notes |
|---|---|---|
| C1 — `ChatCitation.document_title` / phantom `citations` field | Closed | `document_title: string | null`. JSDoc on `citations` and `agent_name` correctly identifies API-hydrated join fields. Join path documented (`retrieval_debug_logs.injected_chunks → knowledge_base_chunks → knowledge_base_documents`). `CitationPanel` handles null with `?? "Unknown document"`. |
| C2 — `role="option"` on `<button>`, missing `aria-haspopup`/`aria-controls` | Closed | `role="option"` now on `<div>` (not `<button>`). Button trigger has `aria-haspopup="listbox"`, `aria-expanded`, `aria-controls`. Options have `aria-selected` and `aria-disabled`. |
| I1 — No outside-click or Escape dismiss | Closed | `mousedown` document listener closes on outside click. `keydown` document listener closes on Escape. `handleKeyDown` also handles Escape. Both active while `open === true`. |
| I2 — `agent_name` undocumented join field | Closed | JSDoc on `agent_name` in `ChatMessageRecord` clearly states it is join-resolved via `agent_definitions`, not a column on the `messages` table. |

---

## New Finding

### [I1-R2] IMPORTANT — `ModelSelector` listbox missing `aria-activedescendant`

**File:** `components/ModelSelector.tsx:42, 165–200`

**Issue:** The keyboard navigation implementation tracks the currently focused option via React state (`focusedIndex`) and applies CSS class (`isFocused`). The `<div role="option">` elements have `tabIndex={-1}` but `focus()` is never called on them imperatively. The button trigger (`<button aria-haspopup="listbox">`) does not have `aria-activedescendant` set to the ID of the currently focused option.

Per ARIA 1.2, when implementing keyboard navigation in a `role="listbox"` widget where DOM focus remains on the composite widget (i.e., the trigger button or the listbox container), the focused option MUST be communicated to assistive technology via `aria-activedescendant`. Without it, screen readers have no signal that ArrowUp/Down changed selection — they will announce nothing when the user navigates through options.

The current implementation is:
- **Correct for sighted keyboard users** — `isFocused` CSS styling is visible.
- **Correct for mouse users** — click selection works.
- **Broken for screen reader users** — no announcement on arrow key navigation.

**Fix required:**

Option A (preferred — minimal change): Add stable `id` attributes to each option `div` (e.g., `id={`model-option-${model.id}`}`), then set `aria-activedescendant` on the listbox `div` to match the currently focused option's ID when `open && focusedIndex >= 0`.

```tsx
// On the listbox div:
aria-activedescendant={
  open && focusedIndex >= 0 && models[focusedIndex]
    ? `model-option-${models[focusedIndex].id}`
    : undefined
}

// On each option div:
id={`model-option-${model.id}`}
```

Option B: Switch to Radix `Select` (already in the shadcn/ui stack). This handles `aria-activedescendant`, focus management, and keyboard nav natively and eliminates this category of error entirely. Larger change but correct by construction.

**Note:** `aria-activedescendant` should live on the element that holds DOM focus. In this implementation, the `listbox` div receives `onKeyDown` events but the trigger `<button>` holds actual DOM focus when the dropdown is open. The cleanest fix is to move DOM focus into the listbox container on open (add `tabIndex={0}` to the listbox div and call `.focus()` on it in the open handler), then set `aria-activedescendant` on the listbox div. That makes the `handleKeyDown` on the listbox div correct.

---

## What is not being re-raised

- M1 (duplicate `Citation` / `ChatCitation` types) — Minor, not re-raised unless still present. Verified: `CitationPanel.tsx` still defines its own `Citation` interface. This remains a Minor type duplication but was a Minor in R1 and is not escalated to block R2.
- M2 (`React.ReactNode` without import in `ChatThread.tsx`) — verified: `ChatThread.tsx` uses `React.ReactNode[]` at line 27 with no React import. Still present. Minor; TS compiles (the `tsconfig` includes global types), but should be fixed. Not escalating to block.

---

## Verdict

**CHANGES_REQUESTED.** Fix `aria-activedescendant` (I1-R2) before approval. Option A is a 4-line change. Option B (Radix Select) is also acceptable and eliminates the problem class entirely.
