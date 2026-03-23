# Framework Library Mutations — Edit / Add / Upload (KIN-320) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add framework create, edit, and bulk JSON upload to the Agent Profile Framework Library tab.

**Architecture:** Three new backend endpoints added to `agents.py` (create, patch, upload). Frontend `FrameworkLibraryTab` extended with an inline edit/add form and a JSON upload flow with summary modal. All follows existing patterns in agents.py (run_in_executor, owner-check, AppException).

**Tech Stack:** Python/FastAPI backend, React/Next.js 14, shadcn/ui, `apiFetch`, TypeScript strict.

**Spec correction:** `confidence` is `ENUM('high', 'medium')` per `docs/db-schema-spec.md §14` — NOT a decimal. Edit form uses a `<select>` with High / Medium. Ticket description was wrong; Jared confirmed enum is correct.

---

## Spec-Section Coverage Matrix

| Spec §Section | Task(s) in plan | Status |
|---|---|---|
| §6 Edit form (name, when_to_apply, category, example_application, confidence, principles) | Task 1 + Task 4 | Covered |
| §6 Trigger embedding note on when_to_apply change | Task 4 | Covered |
| §6 Add manually (same form, empty, POST) | Task 1 + Task 4 | Covered |
| §8 JSON upload flow (file picker, loading, summary modal) | Task 2 + Task 5 | Covered |
| §8 Merge behavior (add/update/retain) + per-framework errors | Task 2 | Covered |

---

## Task 1: Backend — POST create + PATCH update framework endpoints

**Files:**
- Modify: `packages/api/app/api/routes/agents.py`
- Test: `packages/api/tests/test_agents.py` — new class `TestFrameworkMutations`

**DB schema required fields for manual create:**
- `name` (NOT NULL), `when_to_apply` (text[], NOT NULL, len >= 1), `confidence` (ENUM), `principles` (text[], NOT NULL, len >= 1), `origin` = `"manual"` (hardcoded)
- `framework_id` auto-generated if not provided: `re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')`
- Optional: `category`, `example_application`, `description`, `steps`, `related_frameworks`

**Pydantic models to add to `agents.py`:**

```python
class CreateFrameworkRequest(BaseModel):
    name: str
    when_to_apply: list[str]
    principles: list[str]
    confidence: Literal["high", "medium"]
    framework_id: Optional[str] = None  # auto-generated if omitted
    category: Optional[str] = None
    description: Optional[str] = None
    example_application: Optional[str] = None
    steps: list[str] = []
    related_frameworks: list[str] = []

class UpdateFrameworkRequest(BaseModel):
    name: Optional[str] = None
    when_to_apply: Optional[list[str]] = None
    category: Optional[str] = None
    example_application: Optional[str] = None
    confidence: Optional[Literal["high", "medium"]] = None
    principles: Optional[list[str]] = None
```

**`framework_id` slug helper (add at module level):**
```python
import re

def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "framework"
```

**POST `/api/v1/agents/{agent_id}/frameworks`**

Pattern mirrors `delete_framework`:
1. Fetch agent — 404 if not found
2. Owner check — 403 if not owner
3. Build row: `framework_id = body.framework_id or _slug(body.name)`, `origin = "manual"`, `agent_definition_id = agent_id`
4. Validate `when_to_apply` non-empty and `principles` non-empty — raise `ValidationError` if violated
5. Insert row → return `result.data[0]`; raise `ValidationError` if no data returned

**PATCH `/api/v1/agents/{agent_id}/frameworks/{framework_id}`**

1. Fetch agent — 404, owner check — 403
2. Fetch framework (`.eq("id", framework_id).eq("agent_definition_id", agent_id).single()`) — 404 if not found
3. Build `updates` dict from non-None body fields + `updated_at`
4. If `when_to_apply` in updates and `len(updates["when_to_apply"]) == 0` → raise `ValidationError`
5. Update, return `result.data[0]`; raise `NotFoundError` if no data

**Register these routes BEFORE the `DELETE /{agent_id}/frameworks/{framework_id}` route** to avoid any FastAPI ordering issues. Order: GET (list) → POST (create) → POST (upload) → PATCH (update) → DELETE.

**Step 1:** Write failing tests (class `TestFrameworkMutations`):
- `test_create_framework_200` — owner creates, returns 200
- `test_create_framework_403_non_owner` — 403 for non-owner
- `test_create_framework_400_empty_when_to_apply` — 400 validation
- `test_patch_framework_200` — owner patches name
- `test_patch_framework_403_non_owner` — 403
- `test_patch_framework_404_not_found` — 404 when framework missing

Run: `cd packages/api && python -m pytest tests/test_agents.py::TestFrameworkMutations -v`
Expected: `FAILED — ImportError / 404` (routes not added yet)

**Step 2:** Implement `CreateFrameworkRequest`, `UpdateFrameworkRequest`, `_slug()`, `POST /frameworks`, `PATCH /frameworks/{framework_id}` in `agents.py`.

**Step 3:** Run tests.
Expected: All 6 pass.

**Step 4:** Run full suite: `python -m pytest tests/ -x -q 2>&1 | tail -5`
Expected: all pass, no regressions.

**Step 5:** Commit script → `/private/tmp/claude-501/commit-kin320-task1.sh`

---

## Task 2: Backend — POST `/upload` bulk import endpoint

**Files:**
- Modify: `packages/api/app/api/routes/agents.py`
- Test: `packages/api/tests/test_agents.py` — append to `TestFrameworkMutations`

**Request model:**
```python
class UploadFrameworksRequest(BaseModel):
    frameworks: list[dict]  # raw dicts — validated individually per-item
```

**Response shape:**
```python
{"added": int, "updated": int, "retained": int, "failed": [{"framework_id": str, "error": str}]}
```

**Route:** `POST /api/v1/agents/{agent_id}/frameworks/upload`
Register this BEFORE `PATCH /frameworks/{framework_id}` to prevent `"upload"` matching as a `framework_id`.

**Algorithm:**
1. Fetch agent — 404 if not found; owner check — 403
2. Fetch all existing frameworks for agent (by `framework_id` text) → build dict `{framework_id: row}`
3. For each item in `body.frameworks`:
   - Validate required fields: `name`, `when_to_apply` (list, len ≥ 1), `confidence` in `{"high","medium"}`, `principles` (list, len ≥ 1)
   - If invalid: append `{framework_id: item.get("framework_id","?"), error: reason}` to failed list, continue
   - If `framework_id` exists in current set → UPDATE (upsert); increment `updated`
   - Else → INSERT; increment `added`
4. `retained` = len(existing) - updated
5. Return summary dict (never raise for per-item failures — collect them)

**Tests to add to `TestFrameworkMutations`:**
- `test_upload_add_and_update` — 1 new, 1 existing → `{added:1, updated:1, retained:0, failed:[]}`
- `test_upload_validation_failure_skipped` — item missing `when_to_apply` → in `failed` list, others proceed
- `test_upload_403_non_owner`

**Step 1:** Write failing tests. Run. Expected: fail (route missing).
**Step 2:** Implement route.
**Step 3:** Run tests. Expected: pass.
**Step 4:** Full suite. Expected: no regressions.
**Step 5:** Commit script.

---

## Task 3: TypeScript types

**Files:**
- Modify: `packages/web/lib/types/models.ts`

**Append after `UpdateAgentInstanceRequest`:**

```typescript
// Framework mutation types (KIN-320)
export interface CreateFrameworkRequest {
  name: string;
  when_to_apply: string[];
  principles: string[];
  confidence: "high" | "medium";
  framework_id?: string;
  category?: string;
  description?: string;
  example_application?: string;
  steps?: string[];
  related_frameworks?: string[];
}

export interface UpdateFrameworkRequest {
  name?: string;
  when_to_apply?: string[];
  category?: string;
  example_application?: string;
  confidence?: "high" | "medium";
  principles?: string[];
}

export interface UploadFrameworksResponse {
  added: number;
  updated: number;
  retained: number;
  failed: Array<{ framework_id: string; error: string }>;
}
```

**Step 1:** Add types.
**Step 2:** TypeScript check: `cd packages/web && ./node_modules/.bin/tsc --noEmit --incremental false 2>&1 | head -10`
Expected: no output.

---

## Task 4: Frontend — edit/add form in FrameworkLibraryTab

**Files:**
- Modify: `packages/web/components/FrameworkLibraryTab.tsx`

**State to add:**
```typescript
const [editTarget, setEditTarget] = useState<Framework | null>(null);   // null = add mode
const [showForm, setShowForm] = useState(false);
const [formSaving, setFormSaving] = useState(false);
```

**Inline `FrameworkForm` component** (inside the same file, not exported):

Props: `{ initial: Partial<Framework> | null, onSave: (f: Framework) => void, onCancel: () => void, saving: boolean }`

Fields (all managed with `useState`):
- `name` — `<Input>` required
- `when_to_apply` — array. Render list of `<Input>` fields with remove button per phrase + "Add trigger" button
- `principles` — same list pattern as when_to_apply, label "Principles"
- `category` — `<Input>` optional
- `example_application` — `<textarea>` optional (use `className="..."` matching Input style)
- `confidence` — `<select>` with options `high` / `medium`

When_to_apply change note: track `whenToApplyChanged = initialWhenToApply !== currentWhenToApply`. Show inline `<p>` "Trigger embeddings will be updated in the background." if editing (not adding) and changed.

**Save handler:**
- Add: `POST /api/v1/agents/${agentId}/frameworks` with `CreateFrameworkRequest` body
- Edit: `PATCH /api/v1/agents/${agentId}/frameworks/${editTarget.id}` with `UpdateFrameworkRequest` body
- On success: if add → `setFrameworks(prev => [...prev, newRow])`; if edit → update row in place
- Toast: "Framework saved" / "Failed to save framework"
- On done: `setShowForm(false); setEditTarget(null)`

**Wire into FrameworkLibraryTab:**
- "Add framework" button in controls bar (only shown when `isOwner`)
- "Edit" button per row in Actions column (alongside existing "Delete"), only when `isOwner`
- Render `<FrameworkForm>` in an inline modal (same pattern as delete confirm modal already in file) when `showForm === true`

**Empty state CTA buttons:** Enable "Add manually" button (currently `disabled`) to call `setShowForm(true); setEditTarget(null)`.

**Step 1:** Add state, `FrameworkForm` component, wire Edit button and Add button.
**Step 2:** TypeScript check. Expected: clean.
**Step 3:** Commit script.

---

## Task 5: Frontend — JSON upload flow + summary modal

**Files:**
- Modify: `packages/web/components/FrameworkLibraryTab.tsx`

**State to add:**
```typescript
const [uploadLoading, setUploadLoading] = useState(false);
const [uploadSummary, setUploadSummary] = useState<UploadFrameworksResponse | null>(null);
```

**Hidden file input ref:**
```typescript
const fileInputRef = useRef<HTMLInputElement>(null);
```

**Upload handler:**
```typescript
async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
  const file = e.target.files?.[0];
  if (!file) return;
  setUploadLoading(true);
  try {
    const text = await file.text();
    const parsed = JSON.parse(text) as unknown;
    const frameworks = Array.isArray(parsed) ? parsed : (parsed as { frameworks: unknown[] }).frameworks;
    const res = await apiFetch(`/api/v1/agents/${agentId}/frameworks/upload`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frameworks }),
    });
    if (res.ok) {
      const summary: UploadFrameworksResponse = await res.json();
      setUploadSummary(summary);
      void loadFrameworks(); // refresh table
    } else {
      toast({ title: "Upload failed", variant: "destructive" });
    }
  } catch {
    toast({ title: "Invalid JSON file", variant: "destructive" });
  } finally {
    setUploadLoading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }
}
```

**"Upload JSON" button** (controls bar, `isOwner` only):
```tsx
<Button variant="outline" size="sm" disabled={uploadLoading}
  onClick={() => fileInputRef.current?.click()}>
  {uploadLoading ? "Validating…" : "Upload JSON"}
</Button>
<input ref={fileInputRef} type="file" accept=".json" className="hidden"
  onChange={(e) => void handleUpload(e)} />
```

**Summary modal** (inline, same pattern as delete modal):
```
Import Summary
{added} frameworks added
{updated} frameworks updated
{retained} frameworks retained
{failed.length} failed
[Errors list if any]
[OK button → setUploadSummary(null)]
```

**Enable "Upload JSON" CTA in empty state** (currently `disabled`).

**Step 1:** Add upload state, file input ref, handler, button, summary modal.
**Step 2:** TypeScript check. Expected: clean.
**Step 3:** Commit script.

---

## Task 6: Verification + Gilfoyle review

**Step 1:** Run `verification-before-completion`:
- `cd packages/api && python -m pytest tests/ -x -q 2>&1 | tail -5` — all pass
- `cd packages/web && ./node_modules/.bin/tsc --noEmit --incremental false 2>&1 | head -10` — no output
- Cross-reference all table/column names against `docs/db-schema-spec.md §14`
- Confirm `POST /frameworks/upload` registered before `PATCH /frameworks/{framework_id}`

**Step 2:** Spawn Gilfoyle review per `dinesh.md § Automated Review Loop`.

Files to review:
- `packages/api/app/api/routes/agents.py` (new endpoints)
- `packages/api/tests/test_agents.py` (new test class)
- `packages/web/lib/types/models.ts` (new types)
- `packages/web/components/FrameworkLibraryTab.tsx` (edit form + upload)

**Step 3:** Write final commit script to `/private/tmp/claude-501/commit-kin320.sh`.

---

## Done-when (KIN-320)

- [ ] Edit form saves correctly (name, when_to_apply, principles, category, example_application, confidence)
- [ ] `confidence` is `high|medium` dropdown (not numeric %)
- [ ] Trigger embedding note shown when `when_to_apply` changes in edit mode
- [ ] JSON upload summary modal shows counts + error details
- [ ] Table refreshes after upload
- [ ] "Add framework" flow creates new row with `origin = "manual"`
- [ ] API tests pass (3 new create/patch/upload test cases)
- [ ] TypeScript clean
- [ ] Gilfoyle: APPROVED
