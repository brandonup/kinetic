# Active Memory UI — KIN-309 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Active Memory management panel (project settings), proposal review panel (project page load), and add TypeScript types. In-chat save-to-memory button is deferred — no chat UI exists yet (will be wired in Sprint 4/5 when chat UI ships).

**Architecture:** Shared `ActiveMemoryPanel` component added inline to the project settings card. Proposal review banner + panel rendered above the project list when pending proposals exist for the active project. All data via `apiFetch` against existing KIN-308 endpoints.

**Tech Stack:** React (client component), TypeScript strict, shadcn/ui primitives, `apiFetch` from `lib/api.ts`.

**Spec:** `docs/specs/active-memory-spec.md`
**Backend:** `GET/POST/PATCH/DELETE /api/v1/active-memory`, `GET /api/v1/active-memory/proposals`, `POST /api/v1/active-memory/proposals/review`

---

## Task 1: Add TypeScript types

**Files:**
- Modify: `packages/web/lib/types/models.ts`

**Steps:**

1. Append to `models.ts`:

```typescript
// Active Memory types (KIN-309)
export interface ActiveMemoryEntry {
  id: string;
  content: string;
  source_conversation_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ActiveMemoryUsage {
  current_tokens: number;
  cap_tokens: number;
}

export interface ActiveMemoryListResponse {
  entries: ActiveMemoryEntry[];
  token_usage: ActiveMemoryUsage;
}

export interface MemoryProposal {
  id: string;
  proposed_content: string;
  trigger_type: "conversation_end" | "periodic";
  conversation_id: string;
  created_at: string;
}

export interface MemoryProposalsResponse {
  proposals: MemoryProposal[];
}

export interface ProposalDecision {
  proposal_id: string;
  action: "accept" | "reject";
}

export interface ProposalReviewResponse {
  results: Array<{
    proposal_id: string;
    action: "accepted" | "rejected" | "skipped_cap_exceeded";
  }>;
  token_usage: ActiveMemoryUsage;
}
```

2. Verify TypeScript: `cd packages/web && ./node_modules/.bin/tsc --noEmit 2>&1 | head -20`

3. Commit: `git add packages/web/lib/types/models.ts && git commit -m "feat: add ActiveMemory TypeScript types"`

---

## Task 2: Create `ActiveMemoryPanel` component

**Files:**
- Create: `packages/web/components/ActiveMemoryPanel.tsx`

**Component contract:**
```typescript
interface ActiveMemoryPanelProps {
  projectId: string;
  capTokens?: number; // default 1000 for projects
}
```

**Behavior:**
- On mount: `GET /api/v1/active-memory?project_id={id}` → populate entries + token_usage
- Token bar: `current_tokens / cap_tokens`, turns red at ≥90%
- Each entry row: content text, delete button (trash icon). Click content → inline textarea edit.
- Inline edit save: `PATCH /api/v1/active-memory/{entry_id}` → on 422 `memory_full`, show inline error below the textarea ("Memory is full — remove an entry first.")
- Delete: `DELETE /api/v1/active-memory/{entry_id}` → remove from state, update token display.
- Add entry: textarea at bottom of list. "Add" button → `POST /api/v1/active-memory` → on 422 show inline error. On success, prepend to entries list.
- Character soft warning at 400+ chars: "Keep entries short for best results."
- No sorting controls — list is `created_at DESC` (server-ordered).
- Loading state: show skeleton or "Loading…" text while fetching.

**Steps:**

1. Create the component file — full implementation of the panel.

2. TypeScript check: `cd packages/web && ./node_modules/.bin/tsc --noEmit 2>&1 | head -20`

3. Commit: `git add packages/web/components/ActiveMemoryPanel.tsx && git commit -m "feat: ActiveMemoryPanel component — CRUD + token cap display"`

---

## Task 3: Add `ProposalReviewPanel` component

**Files:**
- Create: `packages/web/components/ProposalReviewPanel.tsx`

**Component contract:**
```typescript
interface ProposalReviewPanelProps {
  projectId: string;
  onDismiss: () => void;
}
```

**Behavior:**
- On mount: `GET /api/v1/active-memory/proposals?project_id={id}` → if 0 proposals, call `onDismiss()` immediately.
- Render each proposal: checkbox (toggled = accept, unchecked = reject, default = accept).
- "Accept all" / "Reject all" bulk toggles.
- "Done" button → `POST /api/v1/active-memory/proposals/review` with decisions array.
  - For skipped_cap_exceeded results: show inline note on that proposal row: "Memory full — this wasn't saved."
  - On success: call `onDismiss()`.
- No hard close until user clicks Done (to prevent accidental loss of review).

**Steps:**

1. Create the component file.

2. TypeScript check: `cd packages/web && ./node_modules/.bin/tsc --noEmit 2>&1 | head -20`

3. Commit: `git add packages/web/components/ProposalReviewPanel.tsx && git commit -m "feat: ProposalReviewPanel component — bulk accept/reject proposals"`

---

## Task 4: Wire into project settings page

**Files:**
- Modify: `packages/web/app/(app)/projects/page.tsx`

**Changes:**

1. Import `ActiveMemoryPanel` and `ProposalReviewPanel`.

2. Add state:
   ```typescript
   const [reviewingMemoryProjectId, setReviewingMemoryProjectId] = useState<string | null>(null);
   const [proposalChecked, setProposalChecked] = useState<Set<string>>(new Set());
   ```

3. In the `isSettings` panel for each project, add an `ActiveMemoryPanel` section below Instructions:
   ```tsx
   <Separator className="my-2" />
   <div className="space-y-1.5">
     <Label>Active Memory</Label>
     <p className="text-xs text-muted-foreground">
       Facts and preferences from past conversations — injected into every AI session.
     </p>
     <ActiveMemoryPanel projectId={project.id} />
   </div>
   ```

4. On initial load (`loadAll`): after projects load, for each project check proposals. Simplest approach: check proposals lazily when the user opens settings for a project — add a `useEffect` that fires when `settingsId` changes and fetches proposals for that project. If any pending proposals exist, show a banner inside the settings panel: "You have {N} memory suggestions. [Review →]" → opens `ProposalReviewPanel` in a modal/overlay.

5. Alternatively (simpler, per spec §3.2): check proposals when settings panel opens. Inside `startSettings`, after setting state, fetch proposals for that project and set a `pendingProposalCount` state. Show the banner inline in the settings panel.

**Implementation approach (simpler — no modal):**
- Add state: `const [pendingProposalCount, setPendingProposalCount] = useState(0)`
- Add state: `const [showProposalReview, setShowProposalReview] = useState(false)`
- In `startSettings`: fetch `GET /api/v1/active-memory/proposals?project_id={id}` and set `pendingProposalCount`.
- In the settings panel, above Active Memory Panel: if `pendingProposalCount > 0 && !showProposalReview`, show:
  ```tsx
  <div className="rounded-md bg-muted/60 border border-border px-3 py-2 flex items-center justify-between">
    <p className="text-xs text-muted-foreground">
      {pendingProposalCount} memory suggestion{pendingProposalCount !== 1 ? "s" : ""} from recent conversations.
    </p>
    <Button size="sm" variant="outline" onClick={() => setShowProposalReview(true)}>Review</Button>
  </div>
  ```
- If `showProposalReview`, render `<ProposalReviewPanel projectId={project.id} onDismiss={() => { setShowProposalReview(false); setPendingProposalCount(0); }} />` in place of the banner.

6. TypeScript check: `cd packages/web && ./node_modules/.bin/tsc --noEmit 2>&1 | head -20`

7. Commit: `git add packages/web/app/(app)/projects/page.tsx && git commit -m "feat: wire ActiveMemoryPanel and ProposalReview into project settings"`

---

## Task 5: Verify and clean up

**Steps:**

1. Run full TypeScript check: `cd packages/web && ./node_modules/.bin/tsc --noEmit`

2. Run API backend tests to confirm no regressions: `cd packages/api && python -m pytest tests/ -x -q 2>&1 | tail -10`

3. Invoke `verification-before-completion` before declaring done.

4. Commit any remaining changes.

---

## Done-when checklist (from KIN-309)

- [x] Memory panel lists entries with edit/delete/add — **Task 2**
- [x] Token cap display updates live — **Task 2**
- [ ] ~~Save-to-memory action in chat works~~ — **DEFERRED: no chat UI (Sprint 4/5)**
- [x] Proposal review panel surfaces and processes approvals — **Tasks 3 + 4**
- [x] Token cap error shown inline (not as a toast) — **Task 2**
- [ ] Accessibility review — **post-implementation (Gilfoyle review covers)**
- [x] Tests pass — **Task 5**

## Deferred note

`In-Chat: User-Initiated "Save to memory"` (spec §2 Trigger 1) — the chat/conversation UI does not exist yet (Sprint 4). The memory panel's "Add entry" input covers the manual-save use case. The chat button will be wired when `packages/web/app/(app)/projects/[id]/page.tsx` (or equivalent chat page) is built. No work needed here.
