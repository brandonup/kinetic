# Admin Users Tab Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the Admin Users tab — list users, enable/disable with a public-agent transfer gate, and agent ownership transfer.

**Architecture:** New `admin_users.py` route file following the same pattern as `admin_models.py`. User list merges `public.users` (name, role, disabled_at) with emails from Supabase auth admin API. Disable gate checks `agent_definitions` for public agents owned by the target user before proceeding.

**Tech Stack:** FastAPI + Python 3.11, Supabase service-role client, supabase-py v2 auth admin API, Next.js 14 / shadcn/ui

---

## Key Decisions

- **`disabled_at` column:** Not in current schema spec. Add `disabled_at timestamptz DEFAULT NULL` to `public.users` (Task 1 adds migration script + updates schema spec). Disable = set to `now()`. Enable = set to `null`.
- **Email field:** `public.users` has no email — fetch via `client.auth.admin.list_users()` (service-role only), merge by user ID. If auth call fails, omit email gracefully.
- **Disable 409 response:** `{ "error": "transfer_required", "public_agent_ids": [...] }` — use `ValidationError` with custom detail, or raise `HTTPException(409, ...)` directly. Use direct `HTTPException` since this is a business rule, not a data validation error.
- **Transfer endpoint:** Updates `agent_definitions.owner_id`. Validates new owner exists in `public.users`. Does NOT check agent visibility — admin can transfer any agent.
- **No `PATCH_TARGET` cache needed** — no in-memory cache for users.

## Test Strategy

File: `tests/test_admin_users.py`

Classes:
- `TestListUsers` — returns user list with merged email; empty list; non-admin 403
- `TestDisableUser` — disables successfully (204); 409 when public agents exist; already-disabled is idempotent; non-admin 403
- `TestEnableUser` — enables successfully (200); 404 if user not found
- `TestTransferAgent` — transfers ownership; 404 if agent not found; non-admin 403

Mock pattern: `patch("app.api.routes.admin_users.get_supabase_client", return_value=mock_db)`.
For `list_users`, mock `mock_db.auth.admin.list_users.return_value` (returns list of objects with `.id`, `.email`).

---

### Task 1: Add `disabled_at` to schema + migration script

**Files:**
- Modify: `docs/db-schema-spec.md` (§1 users table — add `disabled_at` row)
- Create: `packages/api/migrations/add_disabled_at_to_users.sql`

**Steps:**

1. Add `disabled_at` row to the users table in `docs/db-schema-spec.md` §1:
   ```
   | `disabled_at` | `timestamptz` | `DEFAULT NULL` | Null = active. Set on disable. |
   ```

2. Create migration file at `packages/api/migrations/add_disabled_at_to_users.sql`:
   ```sql
   ALTER TABLE public.users ADD COLUMN IF NOT EXISTS disabled_at timestamptz DEFAULT NULL;
   ```

3. No tests needed — doc update + migration script only.

4. ⚡ ACTION REQUIRED — Brandon must run the migration:
   ```
   Run in Supabase SQL editor: packages/api/migrations/add_disabled_at_to_users.sql
   ```

---

### Task 2: Backend — admin_users routes + tests

**Files:**
- Create: `packages/api/app/api/routes/admin_users.py`
- Modify: `packages/api/app/main.py` (register router)
- Create: `packages/api/tests/test_admin_users.py`

**Step 1: Write failing tests**

```python
# tests/test_admin_users.py
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest

TEST_USER_ID = str(uuid4())
PATCH_TARGET = "app.api.routes.admin_users.get_supabase_client"

def _user_row(user_id=TEST_USER_ID, name="Alice", role="user", disabled_at=None):
    return {
        "id": user_id, "name": name, "role": role,
        "disabled_at": disabled_at,
        "created_at": "2026-01-01T00:00:00+00:00",
    }

def _auth_user(user_id=TEST_USER_ID, email="alice@example.com"):
    u = MagicMock()
    u.id = user_id
    u.email = email
    return u

class TestListUsers:
    def test_list_returns_users(self, admin_client):
        row = _user_row()
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=[row])
        mock_db.auth.admin.list_users.return_value = [_auth_user()]
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.get("/api/v1/admin/users")
        assert response.status_code == 200
        users = response.json()["users"]
        assert len(users) == 1
        assert users[0]["email"] == "alice@example.com"

    def test_list_non_admin_returns_403(self, client):
        from app.auth.deps import require_admin
        from app.core.errors import AuthorizationError
        from app.main import app
        async def _raise(): raise AuthorizationError()
        app.dependency_overrides[require_admin] = _raise
        try:
            response = client.get("/api/v1/admin/users")
        finally:
            del app.dependency_overrides[require_admin]
        assert response.status_code == 403

class TestDisableUser:
    def test_disable_returns_204(self, admin_client):
        mock_db = MagicMock()
        # Check public agents — none
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        # Update disabled_at
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[_user_row()])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.patch(f"/api/v1/admin/users/{TEST_USER_ID}/disable")
        assert response.status_code == 204

    def test_disable_409_when_public_agents_exist(self, admin_client):
        agent_id = str(uuid4())
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": agent_id}])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.patch(f"/api/v1/admin/users/{TEST_USER_ID}/disable")
        assert response.status_code == 409
        body = response.json()
        assert "public_agent_ids" in body["detail"]

class TestEnableUser:
    def test_enable_returns_200(self, admin_client):
        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[_user_row()])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.patch(f"/api/v1/admin/users/{TEST_USER_ID}/enable")
        assert response.status_code == 200

    def test_enable_not_found_returns_404(self, admin_client):
        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.patch(f"/api/v1/admin/users/{TEST_USER_ID}/enable")
        assert response.status_code == 404

class TestTransferAgent:
    def test_transfer_returns_200(self, admin_client):
        new_owner_id = str(uuid4())
        agent_id = str(uuid4())
        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": agent_id, "owner_id": new_owner_id}])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.patch(
                f"/api/v1/admin/users/{TEST_USER_ID}/transfer-agent",
                json={"agent_id": agent_id, "new_owner_id": new_owner_id},
            )
        assert response.status_code == 200

    def test_transfer_not_found_returns_404(self, admin_client):
        new_owner_id = str(uuid4())
        agent_id = str(uuid4())
        mock_db = MagicMock()
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        with patch(PATCH_TARGET, return_value=mock_db):
            response = admin_client.patch(
                f"/api/v1/admin/users/{TEST_USER_ID}/transfer-agent",
                json={"agent_id": agent_id, "new_owner_id": new_owner_id},
            )
        assert response.status_code == 404
```

**Step 2:** Run tests — expect all FAIL (routes don't exist yet):
```bash
cd packages/api && python -m pytest tests/test_admin_users.py -v
```
Expected: `404` or import errors.

**Step 3: Implement `app/api/routes/admin_users.py`**

Endpoints follow `admin_models.py` pattern exactly. Key implementation notes:

- `GET /api/v1/admin/users`: Query `public.users` ordered by `created_at DESC`. Call `client.auth.admin.list_users()` for emails. Build email lookup dict `{id: email}`, merge into each row. Return `{"users": [...]}`.
- `PATCH /{id}/disable`: Query `agent_definitions` WHERE `owner_id=id AND visibility='public'`. If `result.data` is non-empty, raise `HTTPException(status_code=409, detail={"error": "transfer_required", "public_agent_ids": [row["id"] for row in result.data]})`. Else update `users` SET `disabled_at=now()`. Return 204.
- `PATCH /{id}/enable`: Update `users` SET `disabled_at=None`. If no data returned, raise `NotFoundError`. Return updated row (200).
- `PATCH /{id}/transfer-agent`: Update `agent_definitions` SET `owner_id=new_owner_id` WHERE `id=agent_id`. If no data returned, raise `NotFoundError`. Return updated row (200).

All endpoints: `Depends(require_admin)`. Use `get_supabase_client()` wrapper. All DB calls in `run_in_executor`.

**Step 4:** Register router in `main.py`:
```python
from app.api.routes.admin_users import router as admin_users_router
app.include_router(admin_users_router)
```

**Step 5:** Run tests — expect all PASS:
```bash
python -m pytest tests/test_admin_users.py -v
```

**Step 6:** Run full suite:
```bash
python -m pytest tests/ -v
```
Expected: all pass.

---

### Task 3: Frontend — Admin Users page

**Files:**
- Modify: `packages/web/app/admin/users/page.tsx` (replace stub)
- Modify: `packages/web/lib/types/models.ts` (add `AdminUser` type)

**Step 1: Add `AdminUser` type to `lib/types/models.ts`:**
```typescript
export interface AdminUser {
  id: string;
  email: string;
  name: string;
  role: "admin" | "user";
  disabled_at: string | null;
  created_at: string;
}
```

**Step 2: Implement `app/admin/users/page.tsx`**

UI sections (follow `admin_models.tsx` patterns):
- User table rows: email, name, role badge (`admin` = amber, `user` = default), status badge (`Active`/`Disabled`), created date, actions
- **Disable action:** `PATCH /{id}/disable`. On 409, show inline modal/panel listing `public_agent_ids` with "Transfer to…" select (list of other users) + "Set to private" toggle per agent. Resolve all → re-attempt disable.
- **Enable action:** `PATCH /{id}/enable`. Instant, no confirmation.
- No "Add user" form — users are created via auth trigger.

Transfer modal state: `transferTarget: AdminUser | null`, `publicAgents: string[]`, `agentResolutions: Record<string, { action: "transfer" | "private", newOwnerId?: string }>`

On transfer resolution: for each agent in `publicAgents`:
- If action = `"transfer"`: call `PATCH /{userId}/transfer-agent` with `{ agent_id, new_owner_id }`
- If action = `"private"`: will be a future endpoint (for MVP, omit "set to private" since no agent PATCH endpoint exists yet — just show "Transfer to" dropdown only)

⚠️ **MVP simplification:** The "Set to private" toggle references an Agent PATCH endpoint that doesn't exist yet (Sprint 4). For MVP, the transfer modal only shows "Transfer to…" dropdown. Comment the toggle as `// TODO Sprint 4: add "set to private" option when PATCH /api/v1/agents/{id} exists`.

**Step 3:** TypeScript check:
```bash
cd packages/web && ./node_modules/.bin/tsc --noEmit --incremental false
```
Expected: 0 errors.

---

## Done-When

- `GET /api/v1/admin/users` returns list with email, name, role, disabled_at
- Disable blocked (409) when user owns public agents
- Enable/disable work end-to-end
- Transfer-agent updates ownership
- All Dinesh test suite passes (118+ tests)
- TypeScript clean
- Frontend renders user list with enable/disable actions
