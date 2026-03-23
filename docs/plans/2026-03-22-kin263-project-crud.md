# KIN-263: Project CRUD Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build Project CRUD API endpoints and a full projects settings page with inline create/edit/delete and company reassignment.

**Architecture:** FastAPI backend following exact same patterns as `companies.py` (run_in_executor, local `get_supabase_client()` wrapper). Key difference: company ownership is verified via a 403 (`AuthorizationError`) before any project write. `user_id` is denormalized from auth on insert. GET list returns `{"projects": [...]}` shape per spec. Frontend fetches companies independently (same default-to-first pattern as AppSidebar).

**Tech Stack:** FastAPI, Supabase Python client (sync, run_in_executor), pydantic BaseModel + field_validator, Next.js 14 App Router, shadcn/ui, Tailwind, TypeScript strict.

**Spec ref:** `docs/specs/kin-257-projects-conversations-spec.md` §Part 1 (authoritative — reference it, don't re-read this plan for details)

---

### Task 1: Backend — `projects.py` routes + tests

**Files:**
- Create: `packages/api/app/api/routes/projects.py`
- Test: `packages/api/tests/test_projects.py`

**Pydantic models:**

```python
class CreateProjectRequest(BaseModel):
    name: str
    company_id: str
    instructions: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name must not be empty")
        return v

class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    company_id: Optional[str] = None
    instructions: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("name must not be empty")
        return v
```

**Company ownership helper (module-level, async):**

```python
async def _verify_company_ownership(company_id: str, user_id: str, client) -> None:
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("companies")
            .select("id")
            .eq("id", company_id)
            .eq("user_id", user_id)
            .single()
            .execute(),
    )
    if not result.data:
        raise AuthorizationError("Company does not belong to the requesting user")
```

**Routes — exact behavior:**

`POST /api/v1/projects` → status_code=201. Call `_verify_company_ownership`. Insert `{user_id, company_id, name, instructions}`. Raise `ValidationError` if `not result.data`.

`GET /api/v1/projects` → Query param `company_id: Optional[str] = None`. If company_id provided, call `_verify_company_ownership`. Select all projects `.eq("user_id", ...)` + optional `.eq("company_id", ...)`, `.order("updated_at", desc=True)`. Return `{"projects": result.data or []}`.

`GET /api/v1/projects/{project_id}` → `.eq("id").eq("user_id").single()`. Raise `NotFoundError` if `not result.data`.

`PATCH /api/v1/projects/{project_id}` → If `company_id` in body, call `_verify_company_ownership` first. Build updates dict (name, company_id, instructions from non-None fields + `updated_at = datetime.now(timezone.utc).isoformat()`). `.update(updates).eq("id").eq("user_id")`. Raise `NotFoundError` if `not result.data`.

`DELETE /api/v1/projects/{project_id}` → status_code=204. `.delete().eq("id").eq("user_id")`. Raise `NotFoundError` if `not result.data`.

**Step 1: Write tests first**

Test class structure:
```python
PATCH_TARGET = "app.api.routes.projects.get_supabase_client"
TEST_PROJECT_ID = str(uuid4())
TEST_COMPANY_ID = str(uuid4())

def _project_row(...) -> dict: ...  # helper

class TestCreateProject:
    # test_create_returns_201 — mock: select (company check) returns data, insert returns [row] → assert 201
    # test_create_name_only — instructions=None → 201
    # test_create_missing_name — no name field → 422
    # test_create_empty_name — name="" → 422
    # test_create_company_not_owned — select returns data=None → 403
    # test_create_db_failure — insert returns [] → 400

class TestListProjects:
    # test_list_returns_projects_shape — {"projects": [...]}
    # test_list_empty — {"projects": []}
    # test_list_with_company_filter — passes company_id query param
    # test_list_company_filter_not_owned — company check fails → 403

class TestGetProject:
    # test_get_returns_project
    # test_get_404

class TestUpdateProject:
    # test_patch_name
    # test_patch_with_company_change — company check + update both succeed
    # test_patch_company_not_owned → 403
    # test_patch_not_found → 404
    # test_patch_empty_name → 422

class TestDeleteProject:
    # test_delete_204
    # test_delete_404
```

Mock setup for tests with company ownership check (select chain) + project insert:
```python
mock_db = MagicMock()
# Company check uses select.eq.eq.single.execute
mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(data={"id": TEST_COMPANY_ID})
# Project insert uses insert.execute
mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[row])
```

**Step 2: Run tests** — expect ImportError (module doesn't exist)
```bash
cd packages/api && python -m pytest tests/test_projects.py -v 2>&1 | head -20
```

**Step 3: Implement `projects.py`** — imports: `asyncio`, `logging`, `datetime`, `timezone`, `Optional`, `APIRouter`, `Depends`, `Query`, `BaseModel`, `field_validator`, `CurrentUser`, `get_current_user`, `AuthorizationError`, `NotFoundError`, `ValidationError`, `get_supabase`.

**Step 4: Run tests — expect all pass**
```bash
cd packages/api && python -m pytest tests/test_projects.py -v
```

**Step 5: Commit**
```bash
git add packages/api/app/api/routes/projects.py packages/api/tests/test_projects.py
git commit -m "feat(api): add Project CRUD endpoints (KIN-263)"
```

---

### Task 2: Wire router into `main.py`

**Files:**
- Modify: `packages/api/app/main.py`

Add after companies_router:
```python
from app.api.routes.projects import router as projects_router
app.include_router(projects_router)
```

**Step 1: Add import + include_router**

**Step 2: Run full test suite**
```bash
cd packages/api && python -m pytest tests/ -v 2>&1 | tail -5
```
Expected: all pass, no regressions.

**Step 3: Commit**
```bash
git add packages/api/app/main.py
git commit -m "feat(api): register projects router (KIN-263)"
```

---

### Task 3: Frontend types

**Files:**
- Modify: `packages/web/lib/types/models.ts`

Add after `Company`:
```typescript
export interface Project {
  id: string;
  company_id: string;
  user_id: string;
  name: string;
  instructions: string | null;
  created_at: string;
  updated_at: string;
}
```

**Step 1: Add interface**

**Step 2: TypeScript check**
```bash
cd packages/web && ./node_modules/.bin/tsc --noEmit --incremental false 2>&1 | head -20
```
Expected: no output.

**Step 3: Commit**
```bash
git add packages/web/lib/types/models.ts
git commit -m "feat(web): add Project type (KIN-263)"
```

---

### Task 4: Projects page

**Files:**
- Modify: `packages/web/app/(app)/projects/page.tsx`

`"use client"` page. Full replacement of the stub.

**State:**
```typescript
const [companies, setCompanies] = useState<Company[]>([]);
const [projects, setProjects] = useState<Project[]>([]);
const [loaded, setLoaded] = useState(false);
const [filterCompanyId, setFilterCompanyId] = useState<string | null>(null);
// Create form
const [creating, setCreating] = useState(false);
const [newName, setNewName] = useState("");
const [newInstructions, setNewInstructions] = useState("");
const [savingNew, setSavingNew] = useState(false);
// Inline settings
const [settingsId, setSettingsId] = useState<string | null>(null);
const [editName, setEditName] = useState("");
const [editInstructions, setEditInstructions] = useState("");
const [editCompanyId, setEditCompanyId] = useState("");
const [pendingCompanyName, setPendingCompanyName] = useState<string | null>(null);
const [savingEdit, setSavingEdit] = useState(false);
// Delete confirm
const [deletingId, setDeletingId] = useState<string | null>(null);
const [confirmingDelete, setConfirmingDelete] = useState(false);
```

**Load on mount:** `Promise.all([GET /api/v1/companies, GET /api/v1/projects])` → set state. If company list non-empty, default `filterCompanyId` to first company.

**Filtered project list:** `projects.filter(p => filterCompanyId ? p.company_id === filterCompanyId : true)`

**Create:** Auto-assigned company = `filterCompanyId ?? companies[0]?.id`. POST body: `{name, company_id, instructions: || null}`. On success: prepend to projects, reset form.

**Company filter tabs:** Row of company name buttons above list. Active = highlighted. "All" tab shows all projects. Selecting a tab sets `filterCompanyId`.

**Settings panel (inline):**
- Click "Settings" → `setSettingsId(id)`, populate edit fields from project row
- `editCompanyId` starts as current `company_id`
- On company dropdown change: look up new company name, set `pendingCompanyName`
- If `pendingCompanyName` is set, show notice: `"All conversations and memory in this project will move to ${pendingCompanyName}."`
- Instructions textarea: show `{editInstructions.length}` char count. If `>= 2000`, show advisory message below textarea.
- Save → PATCH. On success: update project in list, clear settings.

**Delete confirm:** Same pattern as companies page. Warning: `"This will also delete all conversations in this project."`

**Instructions advisory (applies to both create and edit forms):**
```tsx
{instructions.length >= 2000 && (
  <p className="text-xs text-amber-600 dark:text-amber-400">
    Instructions are getting long — keep them focused for best results.
  </p>
)}
```

**Company label on project row:** Look up `companies.find(c => c.id === project.company_id)?.name ?? "Unknown"`.

**Step 1: Implement the page**

**Step 2: TypeScript check**
```bash
cd packages/web && ./node_modules/.bin/tsc --noEmit --incremental false 2>&1 | head -20
```

**Step 3: Commit**
```bash
git add packages/web/app/(app)/projects/page.tsx
git commit -m "feat(web): add Project CRUD settings page (KIN-263)"
```

---

## Done-When

- [ ] All 5 `/api/v1/projects` endpoints return correct status codes (201/200/204/404/403/422)
- [ ] POST returns 403 when company_id not owned by user
- [ ] GET list returns `{"projects": [...]}` shape
- [ ] GET list with `?company_id=` filter returns 403 if company not owned
- [ ] DELETE returns 404 when project not owned
- [ ] All `test_projects.py` tests pass
- [ ] Full test suite passes: `python -m pytest tests/ -v`
- [ ] TypeScript clean: `tsc --noEmit --incremental false` no output
- [ ] Projects page: create with auto-assigned company, inline settings, delete confirm
- [ ] Company reassignment shows transfer notice
- [ ] Instructions advisory fires at 2000+ chars
