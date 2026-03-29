# KIN-321: MCP Server Core Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement `POST /api/v1/mcp/context` — MCP bearer token auth, request validation, scope routing, and deterministic context assembly (Layers 1–5).

**Architecture:** Single route file with a custom MCP auth dependency (SHA-256 bearer token → mcp_tokens lookup, NOT Supabase JWT). Context assembly is pure string concatenation from DB rows — no LLM calls in this ticket. Rate limiting is a no-op stub (KIN-323 adds it).

**Tech Stack:** FastAPI, Pydantic, Supabase service-role client, Python hashlib (SHA-256), FastAPI BackgroundTasks.

**ADR:** `docs/adr-006-mcp-server.md` — all key decisions locked.

**Schema refs:** `docs/db-schema-spec.md` §1 (users), §3 (companies), §4 (projects), §8 (agent_definitions), §18 (mcp_tokens)

---

## Task 1: Add RateLimitError to errors.py

**Files:**
- Modify: `packages/api/app/core/errors.py`

**Step 1:** Add `RateLimitError` class after `MemoryCapExceededError`:

```python
class RateLimitError(AppException):
    """Raised when a user exceeds their MCP daily rate limit."""

    def __init__(
        self, message: str = "Rate limit exceeded", details: Optional[Dict[str, Any]] = None
    ):
        super().__init__("RATE_LIMIT_EXCEEDED", message, details)
```

**Step 2:** Wire it to HTTP 429 in `add_exception_handlers` — inside the `app_exception_handler`, add before the final else:

```python
elif isinstance(exc, RateLimitError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
```

**Step 3:** Run existing tests to confirm no regressions:

```bash
PYTHONPATH=/Users/brandonupchuch/son_of_anton/projects/kinetic/packages/api \
  /Users/brandonupchuch/Projects/founder_panel/backend/.venv/bin/python -m pytest \
  packages/api/tests/ -x -q 2>&1 | tail -5
```

Expected: all existing tests pass.

**Step 4:** Commit (after Task 4 — batch with route file).

---

## Task 2: Write failing tests

**Files:**
- Create: `packages/api/tests/test_mcp.py`

Write `packages/api/tests/test_mcp.py` with the test cases below. All tests use `raw_client` (no JWT override — MCP uses bearer token auth). Mock `mcp_routes.get_supabase_client` to control DB responses.

### Test class: `TestMCPTokenAuth`

```python
class TestMCPTokenAuth:
    def test_missing_authorization_header_returns_401(self, raw_client, mock_mcp_db):
        resp = raw_client.post("/api/v1/mcp/context", json={"company_id": str(uuid4())})
        assert resp.status_code == 401

    def test_invalid_bearer_token_returns_401(self, raw_client, mock_mcp_db):
        # Token not in DB
        mock_mcp_db.table.return_value.select.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value.data = None
        resp = raw_client.post(
            "/api/v1/mcp/context",
            json={"company_id": str(uuid4())},
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code == 401

    def test_revoked_token_returns_401(self, raw_client, mock_mcp_db_revoked):
        resp = raw_client.post(
            "/api/v1/mcp/context",
            json={"company_id": str(uuid4())},
            headers={"Authorization": "Bearer some-token"},
        )
        assert resp.status_code == 401

    def test_valid_token_resolves_user(self, raw_client, mock_mcp_db_valid, mock_mcp_entities):
        resp = raw_client.post(
            "/api/v1/mcp/context",
            json={"company_id": str(uuid4())},
            headers={"Authorization": "Bearer valid-token"},
        )
        assert resp.status_code == 200
```

### Test class: `TestMCPRequestValidation`

```python
class TestMCPRequestValidation:
    def test_no_scope_params_returns_400(self, raw_client, mock_mcp_db_valid):
        resp = raw_client.post(
            "/api/v1/mcp/context",
            json={},
            headers={"Authorization": "Bearer valid-token"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "MISSING_SCOPE"

    def test_invalid_uuid_returns_400(self, raw_client, mock_mcp_db_valid):
        resp = raw_client.post(
            "/api/v1/mcp/context",
            json={"company_id": "not-a-uuid"},
            headers={"Authorization": "Bearer valid-token"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_SCOPE_PARAMS"

    def test_entity_not_found_returns_404(self, raw_client, mock_mcp_db_valid, mock_mcp_entity_missing):
        resp = raw_client.post(
            "/api/v1/mcp/context",
            json={"company_id": str(uuid4())},
            headers={"Authorization": "Bearer valid-token"},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "ENTITY_NOT_FOUND"
```

### Test class: `TestMCPScopeRouting`

One test per scoping combination. All 7 combinations must be tested.

```python
class TestMCPScopeRouting:
    def test_project_only_assembles_l1_l2_l3_project(self, raw_client, mock_mcp_db_valid, mock_project_entities):
        project_id = str(uuid4())
        resp = raw_client.post(
            "/api/v1/mcp/context",
            json={"project_id": project_id},
            headers={"Authorization": "Bearer valid-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "L1" in data["layers_assembled"]
        assert "L2" in data["layers_assembled"]
        assert "L3" in data["layers_assembled"]
        assert "L5" not in data["layers_assembled"]

    def test_project_and_agent_assembles_l1_l2_l3_l5(self, ...):  # similar pattern
    def test_agent_only_assembles_l1_l2_l5(self, ...):
    def test_company_only_assembles_l1_l2_l3_company(self, ...):
    def test_project_and_company_uses_project_company(self, ...):
    def test_all_three_params_uses_project_and_agent(self, ...):
    def test_agent_and_company_assembles_l1_l2_l3_l5(self, ...):
```

### Test class: `TestMCPContextAssembly`

```python
class TestMCPContextAssembly:
    def test_response_shape(self, raw_client, mock_mcp_db_valid, mock_company_entities):
        resp = raw_client.post(
            "/api/v1/mcp/context",
            json={"company_id": str(uuid4())},
            headers={"Authorization": "Bearer valid-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "context" in data
        assert "layers_assembled" in data
        assert "token_count_estimate" in data
        assert data["sources"] == []
        assert data["framework"] is None

    def test_token_count_estimate_is_reasonable(self, raw_client, ...):
        # token_count_estimate = len(context) // 4
        ...

    def test_l4_never_in_layers_assembled(self, raw_client, ...):
        # L4 is always omitted
        ...
```

### Fixtures

Add these fixtures to `test_mcp.py` or a local `conftest`-style section at the top:

```python
MCP_USER_ID = str(uuid4())
MCP_TOKEN_ROW = {"id": str(uuid4()), "user_id": MCP_USER_ID, "revoked_at": None}
COMPANY_ROW = {"id": str(uuid4()), "user_id": MCP_USER_ID, "name": "ACME", "description": "We do things"}
PROJECT_ROW = {"id": str(uuid4()), "company_id": str(uuid4()), "user_id": MCP_USER_ID, "name": "Alpha", "instructions": "Be concise."}
AGENT_ROW = {"id": str(uuid4()), "owner_id": MCP_USER_ID, "name": "Strategist", "instructions": "Think strategically.", "visibility": "public"}
USER_ROW = {"id": MCP_USER_ID, "name": "Alice", "bio": "Builder."}

@pytest.fixture
def mock_mcp_db_valid(monkeypatch):
    """Supabase client that returns a valid non-revoked token row."""
    mock = MagicMock()
    # token lookup returns MCP_TOKEN_ROW
    mock.table.return_value.select.return_value.eq.return_value.is_.return_value.single.return_value.execute.return_value.data = MCP_TOKEN_ROW
    # patch at route module level
    monkeypatch.setattr("app.api.routes.mcp.get_supabase_client", lambda: mock)
    return mock
```

**Step 1:** Write the full `test_mcp.py` file with all test classes and fixtures.

**Step 2:** Run to confirm all tests FAIL (route doesn't exist yet):

```bash
PYTHONPATH=/Users/brandonupchuch/son_of_anton/projects/kinetic/packages/api \
  /Users/brandonupchuch/Projects/founder_panel/backend/.venv/bin/python -m pytest \
  packages/api/tests/test_mcp.py -v 2>&1 | tail -20
```

Expected: `ERROR` or `FAILED` — 404s because route not registered.

---

## Task 3: Implement mcp.py

**Files:**
- Create: `packages/api/app/api/routes/mcp.py`

Structure:

```python
"""
MCP context endpoint — KIN-321.

POST /api/v1/mcp/context — assemble context stack for external AI clients.

Auth: SHA-256 bearer token (NOT Supabase JWT). Token looked up in mcp_tokens table.
Schema: docs/db-schema-spec.md §18 (mcp_tokens), §1 (users), §3 (companies), §4 (projects), §8 (agent_definitions)
ADR: docs/adr-006-mcp-server.md
"""
```

### 3a: Token hash helper

```python
import hashlib

def hash_mcp_token(raw_token: str) -> str:
    """SHA-256 hash for MCP bearer token lookup (ADR-006 §1)."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
```

### 3b: Supabase client helper (patchable in tests)

```python
def get_supabase_client():
    return get_supabase()
```

### 3c: MCP auth dependency

```python
async def get_mcp_user(
    request: Request,
    background_tasks: BackgroundTasks,
) -> str:
    """Resolve MCP bearer token to user_id. Raises AuthenticationError on failure."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise AuthenticationError("Missing or invalid Authorization header")

    raw_token = auth_header[len("Bearer "):]
    token_hash = hash_mcp_token(raw_token)

    loop = asyncio.get_running_loop()
    client = get_supabase_client()
    result = await loop.run_in_executor(
        None,
        lambda: client
            .table("mcp_tokens")
            .select("id, user_id")
            .eq("token_hash", token_hash)
            .is_("revoked_at", "null")
            .single()
            .execute(),
    )
    if not result.data:
        raise AuthenticationError("Invalid or revoked MCP token")

    token_id = result.data["id"]
    user_id = result.data["user_id"]

    # Fire-and-forget: update last_used_at without blocking the response
    background_tasks.add_task(_update_last_used, token_id, client)
    return user_id


def _update_last_used(token_id: str, client) -> None:
    """Background: stamp last_used_at on the MCP token row."""
    try:
        client.table("mcp_tokens").update(
            {"last_used_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", token_id).execute()
    except Exception:
        logger.warning("Failed to update mcp_token last_used_at for token_id=%s", token_id)
```

### 3d: Pydantic request model

```python
import re

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

class MCPContextRequest(BaseModel):
    project_id: Optional[str] = None
    agent_id: Optional[str] = None
    company_id: Optional[str] = None

    @model_validator(mode="after")
    def at_least_one_scope(self) -> "MCPContextRequest":
        if not any([self.project_id, self.agent_id, self.company_id]):
            raise ValueError("missing_scope")
        return self

    @model_validator(mode="after")
    def valid_uuids(self) -> "MCPContextRequest":
        for field in (self.project_id, self.agent_id, self.company_id):
            if field is not None and not UUID_RE.match(field):
                raise ValueError("invalid_scope_params")
        return self
```

Note: The Pydantic `ValidationError` raised here is caught by the generic Pydantic handler in `errors.py`. We need the endpoint to convert it to the right error codes — override the validation logic in the endpoint instead:

```python
# In the route handler, validate manually after parsing:
async def mcp_context(...):
    if not any([body.project_id, body.agent_id, body.company_id]):
        raise ValidationError("At least one of project_id, agent_id, company_id is required",
                              details={"code": "MISSING_SCOPE"})
    for field_name, val in [("project_id", body.project_id), ("agent_id", body.agent_id), ("company_id", body.company_id)]:
        if val is not None and not UUID_RE.match(val):
            raise ValidationError(f"Invalid UUID format for {field_name}",
                                  details={"code": "INVALID_SCOPE_PARAMS"})
```

Simpler: use separate Pydantic models with field validators that raise `ValidationError` directly, or validate inline in the handler. **Choose inline validation in the handler** — simpler, matches existing patterns.

Change `MCPContextRequest` to a plain Pydantic model with no validators (just Optional[str] fields). Handle all validation inside the endpoint.

### 3e: Entity existence checks

```python
async def _fetch_entity(table: str, entity_id: str, client, loop) -> Optional[dict]:
    """Fetch a row by id. Returns None if not found."""
    result = await loop.run_in_executor(
        None,
        lambda: client.table(table).select("*").eq("id", entity_id).single().execute(),
    )
    return result.data or None
```

For each requested scope param, call this and raise `NotFoundError` with `code="ENTITY_NOT_FOUND"` if None.

### 3f: Scope routing

```python
def resolve_layers(
    project_id: Optional[str],
    agent_id: Optional[str],
    company_id: Optional[str],
    project_row: Optional[dict],
) -> list[str]:
    """
    Return ordered list of layer IDs to assemble per ADR-006 §4 scoping table.
    project_row is provided when project_id is present (needed for company_id resolution).
    L4 is always omitted (no conversation_id in MCP).
    """
    layers = ["L1", "L2"]
    if project_id:
        layers.append("L3")  # project instructions
    elif company_id:
        layers.append("L3")  # company description
    if agent_id:
        layers.append("L5")
    return layers
```

### 3g: Context assembly

```python
L1_PLATFORM_DEFAULTS = (
    "You are operating within the Kinetic AI workspace. "
    "Kinetic provides structured context including user preferences, "
    "project instructions, and agent personas to ground your responses."
)

async def assemble_context(
    layers: list[str],
    user_id: str,
    project_row: Optional[dict],
    company_row: Optional[dict],
    agent_row: Optional[dict],
    client,
    loop,
) -> tuple[str, list[str]]:
    """Assemble context string from layers. Returns (context_str, layers_assembled)."""
    parts = []
    assembled = []

    if "L1" in layers:
        parts.append(f"## Platform Context\n{L1_PLATFORM_DEFAULTS}")
        assembled.append("L1")

    if "L2" in layers:
        user_result = await loop.run_in_executor(
            None,
            lambda: client.table("users").select("name, bio").eq("id", user_id).single().execute(),
        )
        if user_result.data:
            u = user_result.data
            user_ctx = f"## User\nName: {u['name']}"
            if u.get("bio"):
                user_ctx += f"\nBio: {u['bio']}"
            parts.append(user_ctx)
            assembled.append("L2")

    if "L3" in layers:
        if project_row and project_row.get("instructions"):
            parts.append(f"## Project Instructions\n{project_row['instructions']}")
            assembled.append("L3")
        elif company_row and company_row.get("description"):
            parts.append(f"## Company Context\n{company_row['description']}")
            assembled.append("L3")
        # L4 is always omitted

    if "L5" in layers and agent_row and agent_row.get("instructions"):
        parts.append(f"## Agent Instructions\n{agent_row['instructions']}")
        assembled.append("L5")

    context = "\n\n".join(parts)
    return context, assembled
```

### 3h: The endpoint

```python
router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])

@router.post("/context")
async def mcp_context(
    body: MCPContextRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> dict:
    user_id = await get_mcp_user(request, background_tasks)

    # Validate scope
    if not any([body.project_id, body.agent_id, body.company_id]):
        raise ValidationError("At least one of project_id, agent_id, company_id is required",
                              details={"code": "MISSING_SCOPE"})
    for fname, val in [("project_id", body.project_id), ("agent_id", body.agent_id), ("company_id", body.company_id)]:
        if val is not None and not UUID_RE.match(val):
            raise ValidationError(f"Invalid UUID: {fname}", details={"code": "INVALID_SCOPE_PARAMS"})

    # Rate limit: stub (KIN-323)

    loop = asyncio.get_running_loop()
    client = get_supabase_client()

    # Entity existence
    project_row = None
    company_row = None
    agent_row = None

    if body.project_id:
        project_row = await _fetch_entity("projects", body.project_id, client, loop)
        if not project_row:
            raise NotFoundError("Project not found", details={"code": "ENTITY_NOT_FOUND"})
        # Auto-resolve company_id from project
        if not body.company_id:
            body_company_id = project_row["company_id"]
        else:
            body_company_id = body.company_id

    if body.company_id or (body.project_id and not body.company_id):
        cid = body.company_id or (project_row["company_id"] if project_row else None)
        if cid:
            company_row = await _fetch_entity("companies", cid, client, loop)
            if not company_row:
                raise NotFoundError("Company not found", details={"code": "ENTITY_NOT_FOUND"})

    if body.agent_id:
        agent_row = await _fetch_entity("agent_definitions", body.agent_id, client, loop)
        if not agent_row:
            raise NotFoundError("Agent not found", details={"code": "ENTITY_NOT_FOUND"})

    # Scope routing
    layers = resolve_layers(body.project_id, body.agent_id, body.company_id, project_row)

    # Context assembly
    context, assembled = await assemble_context(layers, user_id, project_row, company_row, agent_row, client, loop)

    return {
        "context": context,
        "layers_assembled": assembled,
        "token_count_estimate": len(context) // 4,
        "sources": [],
        "framework": None,
    }
```

---

## Task 4: Register router in main.py

**Files:**
- Modify: `packages/api/app/main.py`

Add import and `app.include_router(mcp_router)` following the existing pattern.

---

## Task 5: Run tests and verify

```bash
PYTHONPATH=/Users/brandonupchuch/son_of_anton/projects/kinetic/packages/api \
  /Users/brandonupchuch/Projects/founder_panel/backend/.venv/bin/python -m pytest \
  packages/api/tests/test_mcp.py -v 2>&1 | tail -30
```

Expected: all test_mcp tests pass. Fix failures before proceeding.

Then run the full suite to confirm no regressions:

```bash
PYTHONPATH=/Users/brandonupchuch/son_of_anton/projects/kinetic/packages/api \
  /Users/brandonupchuch/Projects/founder_panel/backend/.venv/bin/python -m pytest \
  packages/api/tests/ -q 2>&1 | tail -5
```

---

## Task 6: Self-review gate + commit

**Pre-commit checklist (from bighead.md):**
1. Schema cross-reference: `mcp_tokens` (§18) — token_hash, user_id, revoked_at, last_used_at ✓; `users` (§1) — name, bio ✓; `companies` (§3) — description ✓; `projects` (§4) — instructions, company_id ✓; `agent_definitions` (§8) — instructions ✓
2. All Supabase calls in `async def` use `run_in_executor` ✓
3. `get_mcp_user` uses service role client (mcp_tokens is service-role only) ✓
4. No snake_case/camelCase crossing — Python only in this ticket ✓
5. Tests pass (count from Task 5) ✓
6. No `try/except` swallowing write operations ✓
7. All Supabase writes (last_used_at update) use service role ✓
8. No bare `await` on sync Supabase calls ✓

**Generate commit script** (sandbox blocks git index — write to project dir):

```bash
# Write to packages/api/commit_kin321.sh
MSG="feat: MCP server core — auth, scope routing, context assembly L1-L5 (KIN-321)"
git add packages/api/app/api/routes/mcp.py \
        packages/api/app/core/errors.py \
        packages/api/app/main.py \
        packages/api/tests/test_mcp.py
git commit -m "$MSG"
```

---

## Done When

- [ ] `POST /api/v1/mcp/context` returns 401 on missing/invalid/revoked token
- [ ] Returns 400 `MISSING_SCOPE` when no scope params provided
- [ ] Returns 400 `INVALID_SCOPE_PARAMS` on malformed UUIDs
- [ ] Returns 404 `ENTITY_NOT_FOUND` when project/company/agent not found
- [ ] All 7 scoping combinations produce correct `layers_assembled`
- [ ] L4 never appears in `layers_assembled`
- [ ] Response shape: `context`, `layers_assembled`, `token_count_estimate`, `sources: []`, `framework: null`
- [ ] All test_mcp.py tests pass
- [ ] No regressions in existing test suite
