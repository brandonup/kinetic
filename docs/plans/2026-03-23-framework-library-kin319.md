# Framework Library — Browse/Filter/Delete (KIN-319) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement `agents.py` backend routes (KIN-287/288 rebuild), Agent Profile page stub, and Framework Library browse/filter/delete tab (KIN-319).

**Architecture:** `agents.py` follows the `companies.py` pattern (Pydantic models, `run_in_executor`, `AuthorizationError`/`NotFoundError`). Agent Profile uses Next.js dynamic route `/agents/[id]` with client-side tab switching. Framework Library tab is a separate client component fetching from the new endpoints.

**Tech Stack:** Python/FastAPI (backend), React/Next.js 14 (frontend), shadcn/ui, `apiFetch`, TypeScript strict.

**Spec refs:** `docs/specs/agents.md §10` (API contract), `docs/db-schema-spec.md §14` (frameworks table), KIN-319 ticket description.

---

## Spec-Section Coverage Matrix

| Spec §Section | Task(s) in plan | Status |
|---|---|---|
| agents.md §10 AgentDefinition endpoints | Task 1 | Covered |
| agents.md §10 AgentInstance endpoints | Task 1 | Covered |
| agents.md §10 Framework GET + DELETE | Task 2 | Covered |
| agents.md §4 Agent Profile page | Task 3 + 4 | Covered |
| KIN-319 Table view (§5) | Task 4 | Covered |
| KIN-319 Delete (§7) | Task 4 | Covered |

---

## Task 1: Rebuild `agents.py` — AgentDefinition + AgentInstance endpoints

**Files:**
- Create: `packages/api/app/api/routes/agents.py`
- Modify: `packages/api/app/main.py`
- Test: `packages/api/tests/test_agents.py`

**Schema refs:**
- `agent_definitions`: id, owner_id, name, instructions, type (`custom|thought_leader`), visibility (`private|public`), knowledge_base_id, mcp_enabled, created_at, updated_at
- `agent_instances`: id, agent_definition_id, user_id, framework_overrides (jsonb `{pinned:[], excluded:[]}`), created_at, updated_at

**Step 1: Write failing tests** (TDD — before any implementation)

Test class `TestAgentDefinitionCRUD` in `packages/api/tests/test_agents.py`:
```python
PATCH_TARGET = "app.api.routes.agents.get_supabase_client"

def _agent_row(agent_id=None, owner_id=None, visibility="private", instructions="Think deeply."):
    return {
        "id": agent_id or str(uuid4()),
        "owner_id": owner_id or str(uuid4()),
        "name": "Test Agent",
        "instructions": instructions,
        "type": "custom",
        "visibility": visibility,
        "knowledge_base_id": None,
        "mcp_enabled": False,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
```

Tests to write (all mock Supabase with `patch(PATCH_TARGET, return_value=mock_db)`):

| Test class | Tests |
|---|---|
| `TestListAgents` | `test_list_returns_owned_and_public`, `test_list_empty` |
| `TestCreateAgent` | `test_create_returns_agent`, `test_create_name_required`, `test_cannot_set_public_without_instructions` |
| `TestGetAgent` | `test_get_owned_agent`, `test_get_public_agent_by_non_owner`, `test_get_returns_404_for_private` |
| `TestUpdateAgent` | `test_patch_name`, `test_patch_visibility_public_blocked_without_instructions`, `test_patch_403_non_owner` |
| `TestDeleteAgent` | `test_delete_returns_204`, `test_delete_blocked_if_public_with_invokers`, `test_delete_403_non_owner` |
| `TestAgentInstance` | `test_get_or_create_returns_existing`, `test_get_or_create_creates_new`, `test_patch_instance_framework_overrides` |

Run: `cd packages/api && python -m pytest tests/test_agents.py -v`
Expected: All FAIL — `ModuleNotFoundError: No module named 'app.api.routes.agents'`

**Step 2: Implement `agents.py`**

Follow `companies.py` pattern exactly. Key behaviors:

```python
router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

# List: fetch owned, fetch public (visibility=public), merge, deduplicate by id
# Create: insert row, return created row; validation: cannot set visibility=public if instructions empty
# Get: fetch by id; if not owner, only return if visibility=public; else 404
# Patch: must be owner (403 if not); cannot set visibility=public if instructions is empty or None
# Delete: must be owner (403); check agent_instances for non-owner rows; if any exist and visibility=public → 400
# Get instance: SELECT → INSERT (ON CONFLICT DO NOTHING) → re-SELECT (race-safe)
# Patch instance: owner of INSTANCE (user_id match); update framework_overrides only
```

All Supabase calls: `await loop.run_in_executor(None, lambda: client.table(...).execute())`
Use `get_supabase_client()` helper (patchable) — same pattern as companies.py.

**Step 3: Register in main.py**

```python
from app.api.routes.agents import router as agents_router
# ...
app.include_router(agents_router)
```

**Step 4: Run tests**

Run: `cd packages/api && python -m pytest tests/test_agents.py -v`
Expected: All pass.

**Step 5: Run full suite**

Run: `cd packages/api && python -m pytest tests/ -x -q 2>&1 | tail -5`
Expected: No regressions.

**Step 6: Commit script**

Write to `/private/tmp/claude-501/commit-kin287-rebuild.sh`:
```bash
#!/bin/bash
cd /Users/brandonupchuch/son_of_anton/projects/kinetic
git add packages/api/app/api/routes/agents.py
git add packages/api/app/main.py
git add packages/api/tests/test_agents.py
git commit -m "feat: KIN-287/288 rebuild — agents CRUD + instance endpoints"
```

---

## Task 2: Framework GET + DELETE endpoints

**Files:**
- Modify: `packages/api/app/api/routes/agents.py`
- Test: `packages/api/tests/test_agents.py` — new class `TestFrameworkEndpoints`

**Schema ref — `frameworks` table:**
- `id` (uuid PK), `agent_definition_id` (uuid FK), `framework_id` (text, semantic), `name` (text), `description` (text), `category` (text), `when_to_apply` (text[]), `confidence` (`high|medium`), `origin` (`extracted|manual`), `principles` (text[]), `steps` (text[]), `example_application` (text), `related_frameworks` (text[]), `source_posts` (jsonb), `created_at`, `updated_at`

**Step 1: Write failing tests**

```python
class TestFrameworkEndpoints:
    def test_list_frameworks_returns_list(self, client): ...
    def test_list_frameworks_403_private_non_owner(self, client): ...
    def test_delete_framework_204(self, client): ...
    def test_delete_framework_403_non_owner(self, client): ...
    def test_delete_framework_404_not_found(self, client): ...
```

**Step 2: Implement GET `/agents/:id/frameworks`**

Access: owner OR any user if agent is public. Verify agent exists + accessible first.
```python
@router.get("/{agent_id}/frameworks")
async def list_frameworks(agent_id: str, current_user: CurrentUser = Depends(get_current_user)):
    # 1. Fetch agent — 404 if not found
    # 2. Check access: owner or public (else 403)
    # 3. Fetch frameworks WHERE agent_definition_id = agent_id ORDER BY created_at ASC
    # 4. Return {"frameworks": result.data or []}
```

**Step 3: Implement DELETE `/agents/:id/frameworks/:framework_id`**

```python
@router.delete("/{agent_id}/frameworks/{framework_id}", status_code=204)
async def delete_framework(agent_id: str, framework_id: str, ...):
    # 1. Fetch agent — 404 if not found
    # 2. Must be owner (403 if not)
    # 3. DELETE WHERE id = framework_id AND agent_definition_id = agent_id
    # 4. If not result.data → 404
```

**Step 4: Run tests**

Run: `cd packages/api && python -m pytest tests/test_agents.py -v`
Expected: All pass.

**Step 5: Commit script**

Append to existing commit script or write `/private/tmp/claude-501/commit-kin319-backend.sh`.

---

## Task 3: Agent + Framework TypeScript types

**Files:**
- Modify: `packages/web/lib/types/models.ts`

**Step 1: Add types** — append to models.ts:

```typescript
// Agent types (KIN-287/319)
export type AgentType = "custom" | "thought_leader";
export type AgentVisibility = "private" | "public";

export interface FrameworkOverrides {
  pinned: string[];
  excluded: string[];
}

export interface AgentDefinition {
  id: string;
  owner_id: string;
  name: string;
  instructions: string;
  type: AgentType;
  visibility: AgentVisibility;
  knowledge_base_id: string | null;
  mcp_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface AgentInstance {
  id: string;
  agent_definition_id: string;
  user_id: string;
  framework_overrides: FrameworkOverrides;
  created_at: string;
  updated_at: string;
}

export interface Framework {
  id: string;
  agent_definition_id: string;
  framework_id: string;
  name: string;
  description: string | null;
  category: string | null;
  when_to_apply: string[];
  confidence: "high" | "medium";
  origin: "extracted" | "manual";
  principles: string[];
  steps: string[];
  example_application: string | null;
  related_frameworks: string[];
  source_posts: Record<string, unknown>[] | null;
  created_at: string;
  updated_at: string;
}

export interface FrameworkListResponse {
  frameworks: Framework[];
}

export interface CreateAgentRequest {
  name: string;
  instructions: string;
  type: AgentType;
  visibility: AgentVisibility;
  mcp_enabled: boolean;
}

export interface UpdateAgentInstanceRequest {
  framework_overrides: FrameworkOverrides;
}
```

**Step 2: TypeScript check**

Run: `cd packages/web && ./node_modules/.bin/tsc --noEmit --incremental false 2>&1 | head -10`
Expected: no output (0 errors)

**Step 3: Commit** — write script.

---

## Task 4: Agent Profile page + Framework Library tab

**Files:**
- Create: `packages/web/app/(app)/agents/[id]/page.tsx`
- Create: `packages/web/components/FrameworkLibraryTab.tsx`

**Step 1: Agent Profile page** (`agents/[id]/page.tsx`)

```tsx
"use client";
// Tabs: Instructions | Knowledge Base | Framework Library | Settings
// On mount: GET /api/v1/agents/:id → set agent state
// Tab state: useState<"instructions" | "kb" | "frameworks" | "settings">
// Instructions tab: show agent.name + agent.instructions (read-only textarea)
// KB tab: <p>Coming soon.</p>
// Frameworks tab: <FrameworkLibraryTab agentId={params.id} isOwner={agent.owner_id === currentUserId} />
// Settings tab: <p>Coming soon.</p>
// 404 state: "Agent not found."
// Loading state: "Loading…"
// Need currentUserId: fetch from GET /api/v1/users/me or use auth context
```

**Note on owner check:** If no auth context hook exists, do a client-side check by comparing `agent.owner_id` with current user. The profile page (`profile/page.tsx`) shows the pattern — look at how it fetches the current user.

**Step 2: FrameworkLibraryTab component** (`components/FrameworkLibraryTab.tsx`)

Props:
```typescript
interface FrameworkLibraryTabProps {
  agentId: string;
  isOwner: boolean;
}
```

State:
- `frameworks: Framework[]`, `loading: boolean`
- `search: string`, `categoryFilter: string`
- `deletingId: string | null`, `confirmDeleteId: string | null`

Behavior:
1. On mount: `GET /api/v1/agents/:id/frameworks` → set frameworks
2. Computed: `filteredFrameworks` = filter by search (name) + categoryFilter
3. `distinctCategories` = `[...new Set(frameworks.map(f => f.category).filter(Boolean))]`
4. Table rows: Name, Category badge, Confidence badge (`high`=green/`medium`=yellow), Trigger count (`f.when_to_apply.length`), Origin badge, Actions column
5. Delete: click "Delete" → set `confirmDeleteId` → show dialog with copy from KIN-319 ticket → confirm → `DELETE /api/v1/agents/:id/frameworks/:framework_id` → 204 → remove from state → toast "Framework deleted"
6. Error on delete: toast "Failed to delete framework", row remains

**Empty state:**
```tsx
<p>No frameworks yet. Upload a JSON file or add one manually.</p>
<Button>Upload JSON</Button> {/* stub — wired in KIN-320 */}
<Button>Add manually</Button> {/* stub — wired in KIN-320 */}
```

**Delete dialog copy** (exact from KIN-319 ticket):
> "Delete **{name}**? This will remove the framework and its trigger vectors. This cannot be undone."

Use `shadcn/ui` `AlertDialog` component (same pattern used in projects/page.tsx for project delete).

**Step 3: TypeScript check**

Run: `cd packages/web && ./node_modules/.bin/tsc --noEmit --incremental false 2>&1 | head -10`
Expected: no output

**Step 4: Run full API test suite**

Run: `cd packages/api && python -m pytest tests/ -x -q 2>&1 | tail -5`
Expected: all pass, no regressions

**Step 5: Commit script**

Write `/private/tmp/claude-501/commit-kin319.sh`:
```bash
#!/bin/bash
cd /Users/brandonupchuch/son_of_anton/projects/kinetic
git add packages/web/lib/types/models.ts
git add "packages/web/app/(app)/agents/[id]/page.tsx"
git add packages/web/components/FrameworkLibraryTab.tsx
git commit -m "feat: KIN-319 Framework Library browse/filter/delete + Agent Profile page stub"
```

---

## Task 5: Verification + Gilfoyle review

**Step 1:** `verification-before-completion` — confirm TypeScript clean + all API tests passing.

**Step 2:** Move KIN-319 to Code Review in Linear.

**Step 3:** Spawn Gilfoyle review per `dinesh.md` § Automated Review Loop. Files to review:
- `packages/api/app/api/routes/agents.py`
- `packages/api/tests/test_agents.py`
- `packages/web/lib/types/models.ts`
- `packages/web/app/(app)/agents/[id]/page.tsx`
- `packages/web/components/FrameworkLibraryTab.tsx`

---

## Done-when (KIN-319)

- [ ] Framework Library tab renders table with search + category filter
- [ ] Empty state shown when no frameworks
- [ ] Delete confirm dialog matches spec copy exactly
- [ ] Optimistic row removal on 204
- [ ] Toast on success + error
- [ ] API tests pass (agents.py fully tested)
- [ ] TypeScript clean
- [ ] Gilfoyle review: APPROVED
