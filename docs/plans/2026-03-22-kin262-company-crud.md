# KIN-262: Company CRUD + Active Company Switcher Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build Company CRUD API endpoints and a wired company switcher in the nav with a company list/settings page.

**Architecture:** FastAPI backend with 5 REST endpoints following the exact same patterns as `profile.py` (run_in_executor, local `get_supabase_client()` wrapper for testability, AppException subclasses). Frontend uses local React state for the active company (defaults to most-recently-updated); no DB persistence of active selection in MVP.

**Tech Stack:** FastAPI, Supabase Python client (sync, run_in_executor), pydantic BaseModel + field_validator, Next.js 14 App Router, shadcn/ui, Tailwind, TypeScript strict.

---

### Task 1: Backend — `companies.py` routes

**Files:**
- Create: `packages/api/app/api/routes/companies.py`
- Test: `packages/api/tests/test_companies.py`

All patterns mirror `profile.py` exactly. Key differences:
- Router prefix: `/api/v1/companies`
- Table: `companies`
- Ownership check: `.eq("user_id", current_user.user_id)` on every query

**Pydantic models:**
```python
class CreateCompanyRequest(BaseModel):
    name: str
    description: Optional[str] = None

    @field_validator("description")
    @classmethod
    def description_max_length(cls, v):
        if v is not None and len(v) > 1000:
            raise ValueError("Description must not exceed 1000 characters")
        return v

class UpdateCompanyRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

    @field_validator("description")
    @classmethod
    def description_max_length(cls, v):
        if v is not None and len(v) > 1000:
            raise ValueError("Description must not exceed 1000 characters")
        return v
```

**Routes:**

`POST /api/v1/companies` — insert row with `user_id=current_user.user_id`, return inserted row. Raise `ValidationError` if `result.data` is empty.

`GET /api/v1/companies` — select `id, user_id, name, description, created_at, updated_at` where `user_id = current_user.user_id`, order by `updated_at desc`. Return `result.data or []`.

`GET /api/v1/companies/{company_id}` — select single, `.eq("id", company_id).eq("user_id", current_user.user_id).single()`. Raise `NotFoundError` if `not result.data`.

`PATCH /api/v1/companies/{company_id}` — build `updates` dict from non-None fields only, add `updated_at: datetime.utcnow().isoformat()`. `.update(updates).eq("id", company_id).eq("user_id", current_user.user_id)`. Raise `NotFoundError` if `not result.data`.

`DELETE /api/v1/companies/{company_id}` — status_code=204, `.delete().eq("id", company_id).eq("user_id", current_user.user_id)`. Raise `NotFoundError` if `not result.data`.

**Step 1: Write tests first**

```python
# tests/test_companies.py — test class structure
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest

TEST_USER_ID = "..."  # import from conftest or redefine
TEST_COMPANY_ID = str(uuid4())
PATCH_TARGET = "app.api.routes.companies.get_supabase_client"

class TestCreateCompany:
    def test_create_returns_company(self, client): ...
    def test_create_rejects_name_missing(self, client): ...  # 422
    def test_create_rejects_description_over_1000(self, client): ...  # 422

class TestListCompanies:
    def test_list_returns_companies(self, client): ...
    def test_list_returns_empty_when_none(self, client): ...

class TestGetCompany:
    def test_get_returns_company(self, client): ...
    def test_get_404_when_not_owned(self, client): ...

class TestUpdateCompany:
    def test_patch_updates_name(self, client): ...
    def test_patch_404_when_not_found(self, client): ...
    def test_patch_rejects_description_over_1000(self, client): ...  # 422

class TestDeleteCompany:
    def test_delete_returns_204(self, client): ...
    def test_delete_404_when_not_found(self, client): ...
```

**Step 2: Run tests** — expect `ImportError` (module doesn't exist yet)
```bash
cd packages/api && python -m pytest tests/test_companies.py -v 2>&1 | head -30
```

**Step 3: Implement `companies.py`** — follow `profile.py` structure exactly. Import: `asyncio`, `logging`, `datetime`, `Optional`, `APIRouter`, `Depends`, `BaseModel`, `field_validator`, `CurrentUser`, `get_current_user`, `NotFoundError`, `ValidationError`, `get_supabase`.

**Step 4: Run tests — expect all pass**
```bash
cd packages/api && python -m pytest tests/test_companies.py -v
```

**Step 5: Commit**
```bash
git add packages/api/app/api/routes/companies.py packages/api/tests/test_companies.py
git commit -m "feat(api): add Company CRUD endpoints (KIN-262)"
```

---

### Task 2: Wire router into `main.py`

**Files:**
- Modify: `packages/api/app/main.py`

Add after the existing profile router import/include:
```python
from app.api.routes.companies import router as companies_router
# ...
app.include_router(companies_router)
```

**Step 1: Add import + include_router**

**Step 2: Run full test suite to confirm no regressions**
```bash
cd packages/api && python -m pytest tests/ -v 2>&1 | tail -20
```

**Step 3: Commit**
```bash
git add packages/api/app/main.py
git commit -m "feat(api): register companies router (KIN-262)"
```

---

### Task 3: Frontend types

**Files:**
- Modify: `packages/web/lib/types/models.ts`

Add:
```typescript
export interface Company {
  id: string;
  user_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}
```

**Step 1: Add the interface**

**Step 2: TypeScript check**
```bash
cd packages/web && npx tsc --noEmit --incremental false 2>&1 | head -20
```
Expected: no output (clean)

**Step 3: Commit**
```bash
git add packages/web/lib/types/models.ts
git commit -m "feat(web): add Company type (KIN-262)"
```

---

### Task 4: Companies page

**Files:**
- Create: `packages/web/app/(app)/companies/page.tsx`

`"use client"` page. Sections: **Company List** (inline edit + delete per row), **Create Company** (inline form at bottom).

**State:**
```typescript
const [companies, setCompanies] = useState<Company[]>([]);
const [loaded, setLoaded] = useState(false);
// Create form
const [creating, setCreating] = useState(false);
const [newName, setNewName] = useState("");
const [newDesc, setNewDesc] = useState("");
const [saving, setSaving] = useState(false);
// Inline edit
const [editingId, setEditingId] = useState<string | null>(null);
const [editName, setEditName] = useState("");
const [editDesc, setEditDesc] = useState("");
// Delete confirm
const [deletingId, setDeletingId] = useState<string | null>(null);
```

**Load on mount:** `GET /api/v1/companies` → `setCompanies`

**Create:** `POST /api/v1/companies` with `{ name: newName, description: newDesc || null }` → prepend to list, reset form.

**Edit (inline):** Click "Edit" → set `editingId`, populate `editName`/`editDesc`. Save → `PATCH /api/v1/companies/{id}` → update in list.

**Delete confirm dialog:** Click "Delete" → `setDeletingId(id)`. Show `<dialog>` or inline confirm block with cascade warning: *"Deleting this company will permanently remove all its projects, conversations, and data. This cannot be undone."* Confirm → `DELETE /api/v1/companies/{id}` → remove from list, `setDeletingId(null)`.

**Linked Upload stub:** Same pattern as profile page — `<Button disabled={companies.length === 0}>Upload document</Button>` wrapped in Tooltip if no companies.

**Layout:** `max-w-2xl mx-auto p-8 space-y-8` matching profile page. Use `Separator`, `Label`, `Input`, `Textarea`, `Button` from shadcn/ui. Description char counter (same pattern as bio: `{desc.length} / 1000`, red if >1000).

**Step 1: Implement the page**

**Step 2: TypeScript check**
```bash
cd packages/web && npx tsc --noEmit --incremental false 2>&1 | head -20
```

**Step 3: Commit**
```bash
git add packages/web/app/(app)/companies/page.tsx
git commit -m "feat(web): add Company CRUD settings page (KIN-262)"
```

---

### Task 5: Wire AppSidebar — company switcher + nav item

**Files:**
- Modify: `packages/web/components/AppSidebar.tsx`

**What changes:**
1. Add `"Companies"` nav item: `{ label: "Companies", href: "/companies", icon: Building2 }` — import `Building2` from `lucide-react`.
2. Replace the static company-switcher `<div>` with a wired version:
   - Load companies on mount via `apiFetch("/api/v1/companies")`
   - Track `activeCompany` in local state — default to `companies[0]` (list is already ordered by `updated_at DESC`)
   - Show active company name (or `"— select company —"` if none loaded)
   - On click: toggle an inline dropdown list of all companies
   - Selecting a company: `setActiveCompany(company)`, close dropdown
   - Use `useRef` for outside-click dismissal of dropdown
   - The dropdown renders absolutely below the switcher div

**Switcher shape (keep existing classes/testid, add state):**
```tsx
// state
const [companies, setCompanies] = useState<Company[]>([]);
const [activeCompany, setActiveCompany] = useState<Company | null>(null);
const [open, setOpen] = useState(false);
const switcherRef = useRef<HTMLDivElement>(null);

// load
useEffect(() => { void loadCompanies(); }, []);
async function loadCompanies() {
  const res = await apiFetch("/api/v1/companies");
  if (res.ok) {
    const data: Company[] = await res.json();
    setCompanies(data);
    if (data.length > 0) setActiveCompany(data[0]);
  }
}

// outside click dismiss
useEffect(() => {
  function handleClick(e: MouseEvent) {
    if (switcherRef.current && !switcherRef.current.contains(e.target as Node)) {
      setOpen(false);
    }
  }
  document.addEventListener("mousedown", handleClick);
  return () => document.removeEventListener("mousedown", handleClick);
}, []);
```

Dropdown: absolutely positioned below the switcher, `z-50`, border, bg, rounded, shadow. Each row: `cursor-pointer px-4 py-2 hover:bg-muted/60 text-sm`. Active row gets `font-medium text-foreground`, others `text-muted-foreground`.

**Step 1: Implement changes**

**Step 2: TypeScript check**
```bash
cd packages/web && npx tsc --noEmit --incremental false 2>&1 | head -20
```

**Step 3: Commit**
```bash
git add packages/web/components/AppSidebar.tsx
git commit -m "feat(web): wire company switcher and add Companies nav item (KIN-262)"
```

---

## Done-When

- [ ] All 5 `/api/v1/companies` endpoints return correct status codes (201/200/204/404/422)
- [ ] Description validation rejects >1000 chars with 422
- [ ] DELETE returns 404 when company not owned by user
- [ ] All `test_companies.py` tests pass
- [ ] Full test suite passes: `python -m pytest tests/ -v`
- [ ] TypeScript clean: `tsc --noEmit --incremental false` produces no output
- [ ] Companies page: list, create, inline edit, delete confirm with cascade warning
- [ ] AppSidebar: switcher loads companies, shows active, dropdown selects
- [ ] "Companies" nav item appears and routes to `/companies`
