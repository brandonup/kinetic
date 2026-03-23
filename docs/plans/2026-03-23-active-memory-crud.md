# Active Memory CRUD Implementation Plan (KIN-308)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement `active_memory_entries` CRUD + `memory_proposals` review endpoints with hard token-cap enforcement at `/api/v1/active-memory`.

**Architecture:** Single route file (`active_memory.py`) with inline token helpers. No separate service layer — the logic is simple counting + gated writes. Service-role Supabase client is used throughout (same pattern as all other routes); user ownership verified manually via `user_id` equality checks.

**Tech Stack:** FastAPI, Pydantic, Supabase (service role), `math.ceil` for token counting. No new packages.

**Spec:** `docs/specs/active-memory-spec.md` — authoritative for endpoint shapes, request/response bodies, and error formats.
**Schema:** `docs/db-schema-spec.md §16` (`active_memory_entries`) and `§17` (`memory_proposals`).

---

## Key Decisions

1. **Token counting:** `math.ceil(len(content) / 4)` — character-proxy per spec §1.2. No tiktoken.
2. **Cap exceeded → 422:** Add `MemoryCapExceededError` to `errors.py` mapping to HTTP 422. Details carry `current_tokens` and `cap_tokens`. Response shape: `{"error": {"code": "MEMORY_CAP_EXCEEDED", "message": "...", "details": {"current_tokens": N, "cap_tokens": N}}}`.
3. **Scope resolution:** Exactly one of `project_id` or `agent_instance_id` must be set. Reject both-or-neither with `ValidationError` (400).
4. **Ownership verification:** For `project_id` scope, query `projects` table with `user_id = current_user.user_id`. For `agent_instance_id` scope, query `agent_instances` with `user_id = current_user.user_id`. Unauthorized → `AuthorizationError` (403).
5. **Proposals insert is background-only** (KIN-306/307); this ticket owns list + bulk review endpoints only.
6. **Caps:** `ACTIVE_MEMORY_CAP_PROJECT = 1000`, `ACTIVE_MEMORY_CAP_AGENT = 500` (module-level constants).
7. **PATCH token recalculation:** `(total_tokens − old_entry_tokens + new_entry_tokens) > cap` → reject. Fetch existing entry first, compute delta.

---

## Task 1: Add `MemoryCapExceededError` to `errors.py`

**Files:**
- Modify: `packages/api/app/core/errors.py`

**Steps:**

1. Add the new exception class after `ValidationError`:
```python
class MemoryCapExceededError(AppException):
    """Raised when a write would exceed the active memory token cap."""
    def __init__(self, current_tokens: int, cap_tokens: int):
        super().__init__(
            "MEMORY_CAP_EXCEEDED",
            f"Memory is full ({current_tokens}/{cap_tokens} tokens). Delete an entry to make room.",
            {"current_tokens": current_tokens, "cap_tokens": cap_tokens},
        )
```

2. In `add_exception_handlers`, add the 422 mapping inside `app_exception_handler` alongside the other `isinstance` checks:
```python
elif isinstance(exc, MemoryCapExceededError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
```

3. Run existing tests to confirm nothing broke:
```bash
PYTHONPATH=packages/api /Users/brandonupchuch/Projects/founder_panel/backend/.venv/bin/python \
  -m pytest packages/api/tests/ -q
```
Expected: all previously passing tests still pass.

4. Commit: `chore: add MemoryCapExceededError (422) for active memory cap enforcement`

---

## Task 2: Write failing tests for active memory entry CRUD

**Files:**
- Create: `packages/api/tests/test_active_memory.py`

**Setup — fixtures and constants needed:**

```python
PROJECT_ID = str(uuid4())
AGENT_INSTANCE_ID = str(uuid4())
ENTRY_ID = str(uuid4())
CONVERSATION_ID = str(uuid4())
```

Each test patches `app.api.routes.active_memory.get_supabase_client` with a `MagicMock`.

**Tests to write (all pytest, use `client` fixture from conftest):**

```
class TestListEntries:
    test_list_by_project_id          # GET returns entries + token_usage
    test_list_by_agent_instance_id   # GET with agent_instance_id param
    test_list_neither_scope_400      # GET with no params → 400
    test_list_both_scopes_400        # GET with both params → 400
    test_list_wrong_user_403         # mock ownership check returns empty → 403

class TestCreateEntry:
    test_create_project_entry_201    # POST → 201 with created entry
    test_create_empty_content_400    # POST content="" → 400
    test_create_cap_exceeded_422     # mock current_tokens near cap → 422
    test_create_exactly_at_cap_422   # total == cap+1 → 422
    test_create_exactly_at_cap_ok    # total == cap → 201

class TestUpdateEntry:
    test_update_content_200          # PATCH → 200 with updated entry
    test_update_cap_exceeded_422     # growing content exceeds cap → 422
    test_update_not_found_404        # entry doesn't belong to user → 404

class TestDeleteEntry:
    test_delete_204                  # DELETE → 204
    test_delete_not_found_404        # no matching entry → 404
```

**Run to confirm all fail:**
```bash
PYTHONPATH=packages/api /Users/brandonupchuch/Projects/founder_panel/backend/.venv/bin/python \
  -m pytest packages/api/tests/test_active_memory.py -q
```
Expected: `ImportError` or `404` failures (route not registered yet).

Commit: `test: add failing tests for active memory entry CRUD (KIN-308)`

---

## Task 3: Implement `active_memory.py` — entries CRUD

**Files:**
- Create: `packages/api/app/api/routes/active_memory.py`

**Module structure:**

```python
import asyncio, logging, math
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_validator

from app.auth.deps import CurrentUser, get_current_user
from app.core.errors import AuthorizationError, MemoryCapExceededError, NotFoundError, ValidationError
from app.db.supabase_client import get_supabase

ACTIVE_MEMORY_CAP_PROJECT = 1000
ACTIVE_MEMORY_CAP_AGENT = 500

router = APIRouter(prefix="/api/v1/active-memory", tags=["active-memory"])
```

**Token helper:**
```python
def _count_tokens(content: str) -> int:
    return math.ceil(len(content) / 4)
```

**Scope validation helper** (`project_id` XOR `agent_instance_id`):
- Returns `("project", project_id, cap)` or `("agent_instance", agent_instance_id, cap)`
- Raises `ValidationError` if both or neither are set

**Ownership verification helpers** (async, use `run_in_executor`):
- `_verify_project_ownership(project_id, user_id, client)` — query `projects` table, raise `AuthorizationError` if not found
- `_verify_agent_instance_ownership(agent_instance_id, user_id, client)` — query `agent_instances` table

**`_get_current_tokens(scope_col, scope_id, user_id, client)` helper** (async):
- Query: `active_memory_entries` WHERE `{scope_col} = scope_id AND user_id = user_id`
- Return `sum(_count_tokens(row["content"]) for row in result.data)`

**Endpoints to implement:**

`GET /api/v1/active-memory` — list entries + token_usage. See spec §4.1 for response shape.

`POST /api/v1/active-memory` — create entry. Request body: `{content, project_id?, agent_instance_id?, source_conversation_id?}`. Validate scope, verify ownership, get current tokens, check cap (`current + new > cap` → raise `MemoryCapExceededError`), insert row with `user_id` set from auth. Return 201 with row.

`PATCH /api/v1/active-memory/{entry_id}` — update content. Fetch existing entry (verify `user_id` match → 404 if not found). Compute `new_total = current_tokens - old_tokens + new_tokens`. Raise `MemoryCapExceededError` if over cap. Update row. Return 200.

`DELETE /api/v1/active-memory/{entry_id}` — delete. Verify ownership via `user_id` filter on delete query. If `result.data` is empty → `NotFoundError`. Return 204.

**Run failing tests after implementing — all should now pass:**
```bash
PYTHONPATH=packages/api /Users/brandonupchuch/Projects/founder_panel/backend/.venv/bin/python \
  -m pytest packages/api/tests/test_active_memory.py -q
```

Commit: `feat: implement active memory entry CRUD with token cap enforcement (KIN-308)`

---

## Task 4: Write and pass proposals tests + implement proposals endpoints

**Add to `test_active_memory.py`:**

```
class TestListProposals:
    test_list_pending_by_project     # GET /proposals?project_id= → list
    test_list_pending_by_agent       # GET /proposals?agent_instance_id=
    test_list_no_scope_400           # missing both params → 400

class TestReviewProposals:
    test_accept_proposal_inserts_entry    # accept → entry created, proposal status='approved'
    test_reject_proposal_status_rejected  # reject → proposal status='rejected', no entry
    test_accept_cap_exceeded_skipped      # accept would exceed cap → status=skipped_cap_exceeded
    test_mixed_decisions                  # one accept + one reject in same request
```

**Implement in `active_memory.py`:**

`GET /api/v1/active-memory/proposals` — list pending proposals for scope. Query `memory_proposals` WHERE `status='pending' AND user_id=? AND {scope_col}=?`. Return `{"proposals": [...]}` per spec §4.1 shape.

`POST /api/v1/active-memory/proposals/review` — bulk accept/reject. Request body: `{"decisions": [{"proposal_id": uuid, "action": "accept|reject"}]}`. Process in order:
- **accept:** token cap check → if passes: insert entry + set `status='approved'`, `reviewed_at=now()`; if cap exceeded: set result `"skipped_cap_exceeded"`.
- **reject:** set `status='rejected'`, `reviewed_at=now()`.
- Return 200 with results array + current token_usage.

Note: fetch proposal row first to get `proposed_content`, `project_id`/`agent_instance_id` for scope resolution. Verify `user_id` match on the proposal row.

**Run tests:**
```bash
PYTHONPATH=packages/api /Users/brandonupchuch/Projects/founder_panel/backend/.venv/bin/python \
  -m pytest packages/api/tests/test_active_memory.py -q
```

Commit: `feat: add active memory proposals list + bulk review endpoints (KIN-308)`

---

## Task 5: Admin endpoint, router registration, full test run

**Admin endpoint** (add to `active_memory.py`):

`GET /api/v1/admin/active-memory` — requires `require_admin` dep (import from `app.auth.deps`). Query params: `user_id` (required) + `project_id`/`agent_instance_id` (XOR). Same response shape as user list endpoint. No ownership check — admin reads any user.

**Add test:**
```
class TestAdminListEntries:
    test_admin_can_read_any_user     # admin_client fixture, user_id param
    test_non_admin_403               # client fixture (regular user) → 403
```

**Wire router into `main.py`:**
```python
from app.api.routes.active_memory import router as active_memory_router
# ...
app.include_router(active_memory_router)
```

**Full test suite:**
```bash
PYTHONPATH=packages/api /Users/brandonupchuch/Projects/founder_panel/backend/.venv/bin/python \
  -m pytest packages/api/tests/ -q
```
Expected: all tests pass. Record count for handoff comment.

Commit: `feat: add admin active memory endpoint + register router (KIN-308)`

---

## Done When

- [ ] `MemoryCapExceededError` exists in `errors.py`, maps to 422
- [ ] `GET/POST /api/v1/active-memory` — entries list + create with cap enforcement
- [ ] `PATCH/DELETE /api/v1/active-memory/{entry_id}` — update (delta cap check) + delete
- [ ] `GET /api/v1/active-memory/proposals` — list pending proposals
- [ ] `POST /api/v1/active-memory/proposals/review` — bulk accept/reject with cap gate
- [ ] `GET /api/v1/admin/active-memory` — admin read any user
- [ ] Token count method is `ceil(len(content) / 4)` — confirmed in tests
- [ ] Cap edge cases covered: exactly at cap passes, one-over-cap fails
- [ ] All tests pass; full suite count in handoff comment

---

## Test Strategy

- All tests use `client` / `admin_client` fixtures (no real DB)
- Mock `get_supabase_client` at module level: `unittest.mock.patch("app.api.routes.active_memory.get_supabase_client")`
- Token cap tests: control `current_tokens` by controlling mock return for `active_memory_entries` select query
- PATCH delta test: mock returns existing entry with known content length + existing entries total
- No integration tests for MVP
