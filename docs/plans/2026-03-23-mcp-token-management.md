# MCP Token Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the full-stack MCP token management feature — backend CRUD routes + Profile page UI section — so users can generate, view, and revoke bearer tokens for Claude Desktop / Cursor.

**Architecture:** Backend adds a new FastAPI router (`mcp_tokens.py`) with three endpoints following the profile.py pattern (run_in_executor, AppException errors, no silent swallowing on writes). Frontend adds a new "MCP Tokens" section at the bottom of the existing Profile page — no new page or route needed.

**Tech Stack:** Python/FastAPI (backend), Next.js/TypeScript/React (frontend), Supabase `mcp_tokens` table (§18 db-schema-spec.md), SHA-256 token hashing (ADR-006 §1), shadcn/ui Dialog + Table components.

---

## API Contract

Token generation returns the raw token **once only** — never stored, never returned again.

**POST /api/v1/mcp/tokens**
```
Request:  { "name": "Claude Desktop" }   # max 64 chars
Response: { "id": "uuid", "name": "Claude Desktop", "token": "mcp_<64-hex>", "created_at": "iso8601" }
```

**GET /api/v1/mcp/tokens**
```
Response: { "tokens": [{ "id": "uuid", "name": "...", "last_used_at": "iso8601"|null, "created_at": "iso8601" }] }
```
Never returns `token_hash`. Omits revoked tokens (`revoked_at IS NULL` filter).

**PATCH /api/v1/mcp/tokens/{id}/revoke**
```
Response: { "id": "uuid", "revoked_at": "iso8601" }
404: token not found or not owned by user
409: token already revoked
```

**Token format:** `os.urandom(32).hex()` → 64-char hex → prefix `mcp_` for UI display. Hash: `hashlib.sha256(raw_token.encode()).hexdigest()`.

---

## Schema Cross-Reference (columns used)

`mcp_tokens`: `id`, `user_id`, `token_hash`, `name`, `last_used_at`, `revoked_at`, `created_at`
All verified against `docs/db-schema-spec.md` §18. Note: schema says "bcrypt" but ADR-006 §1 overrides to SHA-256.

---

## Task 1: Backend — mcp_tokens router

**Files:**
- Create: `packages/api/app/api/routes/mcp_tokens.py`
- Modify: `packages/api/app/main.py` (import + include_router)

**Steps:**

1. Create `mcp_tokens.py` with router prefix `/api/v1/mcp/tokens`.

2. Add Pydantic request model:
   ```python
   class CreateTokenRequest(BaseModel):
       name: str
       @field_validator("name")
       @classmethod
       def validate_name(cls, v: str) -> str:
           v = v.strip()
           if not v: raise ValueError("name is required")
           if len(v) > 64: raise ValueError("name must be ≤ 64 characters")
           return v
   ```

3. Add module-level `get_supabase_client()` helper (same pattern as profile.py line 74) — needed for test patching.

4. **POST `/`** — generate token:
   - `raw = os.urandom(32).hex()` (import `os`, `hashlib`)
   - `token_hash = hashlib.sha256(raw.encode()).hexdigest()`
   - Insert `{ user_id, token_hash, name }` into `mcp_tokens` via `run_in_executor`
   - Return `{ id, name, token: f"mcp_{raw}", created_at }`
   - On insert failure: raise `AppException` (never return None)

5. **GET `/`** — list active tokens:
   - Select `id, name, last_used_at, created_at` WHERE `user_id = current_user.user_id AND revoked_at IS NULL`
   - Return `{ "tokens": result.data }`

6. **PATCH `/{token_id}/revoke`** — revoke:
   - Fetch token: `id = token_id AND user_id = current_user.user_id`
   - If not found: raise `NotFoundError`
   - If `revoked_at` already set: raise `ConflictError` (409) — check if `ConflictError` exists in `app.core.errors`; if not, use `AppException` with `status_code=409`
   - Update `revoked_at = now()` via `run_in_executor`
   - Return `{ id, revoked_at }`

7. Register router in `main.py`:
   ```python
   from app.api.routes.mcp_tokens import router as mcp_tokens_router
   app.include_router(mcp_tokens_router)
   ```

---

## Task 2: Backend Tests

**Files:**
- Create: `packages/api/tests/test_mcp_tokens.py`

**Test class structure** (unique class names — no shadowing):

```python
class TestMcpTokenCreate:
class TestMcpTokenList:
class TestMcpTokenRevoke:
```

**TestMcpTokenCreate tests:**
- `test_create_token_returns_raw_token_once` — mock insert returns row, assert response has `token` starting with `mcp_`, has `id`, `name`, `created_at`
- `test_create_token_stores_hash_not_plaintext` — capture the insert payload; assert `token_hash` != response `token`; assert `token_hash == sha256(raw).hexdigest()`
- `test_create_token_name_required` — empty name → 422
- `test_create_token_name_max_64_chars` — 65-char name → 422
- `test_create_token_name_whitespace_stripped` — `"  Claude Desktop  "` → name stored as `"Claude Desktop"`
- `test_create_token_requires_auth` — no auth header → 401 (use `raw_client`)

**TestMcpTokenList tests:**
- `test_list_tokens_returns_active_only` — mock returns 2 rows, assert response has 2 tokens with correct fields
- `test_list_tokens_excludes_token_hash` — assert no `token_hash` key in any token row
- `test_list_tokens_last_used_at_null_for_unused` — row has `last_used_at: null`, assert it's null in response

**TestMcpTokenRevoke tests:**
- `test_revoke_token_success` — mock fetch returns active token, mock update returns revoked row, assert 200 + `revoked_at` present
- `test_revoke_token_not_found` — mock fetch returns empty, assert 404
- `test_revoke_token_already_revoked` — mock fetch returns token with `revoked_at` set, assert 409
- `test_revoke_token_wrong_user` — fetch includes `user_id` filter; mock returns empty (other user's token not returned), assert 404

**Mocking pattern** (follow profile.py tests — patch `get_supabase_client` at module level):
```python
with patch("app.api.routes.mcp_tokens.get_supabase_client") as mock_fn:
    mock_client = MagicMock()
    mock_fn.return_value = mock_client
    mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{...}])
```

**Run tests:**
```bash
cd packages/api && python -m pytest tests/test_mcp_tokens.py -v
```
Expected: all pass before moving to frontend.

---

## Task 3: Frontend Types

**Files:**
- Modify: `packages/web/lib/types/models.ts`

Add after existing types:

```typescript
// MCP token types (KIN-325)
export interface McpToken {
  id: string;
  name: string;
  last_used_at: string | null;
  created_at: string;
}

export interface McpTokenListResponse {
  tokens: McpToken[];
}

export interface CreateMcpTokenResponse {
  id: string;
  name: string;
  token: string;  // raw token — shown once only
  created_at: string;
}
```

---

## Task 4: Frontend — MCP Tokens section

**Files:**
- Modify: `packages/web/app/(app)/profile/page.tsx`

**State to add** (alongside existing state at top of `ProfilePage`):
```typescript
const [mcpTokens, setMcpTokens] = useState<McpToken[]>([]);
const [showGenerateForm, setShowGenerateForm] = useState(false);
const [generateLabel, setGenerateLabel] = useState("");
const [generatingToken, setGeneratingToken] = useState(false);
const [newToken, setNewToken] = useState<CreateMcpTokenResponse | null>(null);
const [revokeConfirmId, setRevokeConfirmId] = useState<string | null>(null);
const [revokingId, setRevokingId] = useState<string | null>(null);
```

**Load in `loadAll()`:** Add `apiFetch("/api/v1/mcp/tokens")` to the `Promise.all` call. On success: `setMcpTokens(data.tokens)`.

**Three functions to add:**
- `async function generateToken()` — POST, on success set `newToken`, append to `mcpTokens`, reset form
- `async function revokeToken(id: string)` — PATCH, optimistic removal from `mcpTokens`
- `function formatLastUsed(ts: string | null)` — returns `"Never"` if null, else relative format (use `new Date(ts).toLocaleDateString()`)

**UI section** — add after the Linked Upload `<Separator />`:

```tsx
<Separator />

{/* ── MCP Tokens ── */}
<section className="space-y-4">
  <div className="flex items-center justify-between">
    <div>
      <h2 className="text-base font-medium text-foreground">MCP Tokens</h2>
      <p className="text-sm text-muted-foreground mt-0.5">
        Bearer tokens for connecting Claude Desktop, Cursor, and other MCP clients.
      </p>
    </div>
    <Button variant="outline" size="sm" onClick={() => setShowGenerateForm(true)}>
      Generate new token
    </Button>
  </div>

  {/* Generate form — inline, shown when showGenerateForm */}
  {showGenerateForm && (/* label input + Generate/Cancel buttons */)}

  {/* Token table */}
  {mcpTokens.length > 0 && (/* table: Label | Created | Last used | Revoke */)}

  {mcpTokens.length === 0 && !showGenerateForm && (
    <p className="text-sm text-muted-foreground">No tokens yet.</p>
  )}
</section>

{/* One-time token modal — controlled by newToken state */}
{newToken && (
  <Dialog open onOpenChange={() => setNewToken(null)}>
    {/* Warning + token display + copy button */}
    {/* "Copy this token now. You won't be able to see it again." */}
  </Dialog>
)}

{/* Revoke confirm dialog — controlled by revokeConfirmId */}
{revokeConfirmId && (
  <Dialog open onOpenChange={() => setRevokeConfirmId(null)}>
    {/* "Revoke '[label]'? Any client using this token will immediately lose access." */}
    {/* Cancel | Revoke buttons */}
  </Dialog>
)}
```

**Imports to add:** `Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter` from `@/components/ui/dialog`.

**Copy button** — use `navigator.clipboard.writeText(newToken.token)` with a `copied` state toggle for feedback.

**TypeScript:** Add `McpToken, McpTokenListResponse, CreateMcpTokenResponse` to the import from `@/lib/types/models`.

---

## Task 5: Frontend Tests

**Files:**
- Create: `packages/web/app/__tests__/components/McpTokensSection.test.tsx`

**Test cases:**
- `renders empty state when no tokens`
- `renders token list with label, created date, last used`
- `shows Never for null last_used_at`
- `generate form appears on button click, hides on cancel`
- `generate token calls POST and shows one-time modal`
- `modal contains copy button and warning text`
- `dismissing modal clears newToken state (token gone from view)`
- `revoke button opens confirm dialog with token name`
- `confirming revoke calls PATCH and removes token from list`

Follow the pattern from `FrameworkLibraryTab.test.tsx` for mocking `apiFetch`.

**Run:**
```bash
cd packages/web && ./node_modules/.bin/vitest run app/__tests__/components/McpTokensSection.test.tsx
```

---

## Done When

- [ ] `POST /api/v1/mcp/tokens` creates token, returns raw value once, stores SHA-256 hash
- [ ] `GET /api/v1/mcp/tokens` lists active tokens, never exposes hash
- [ ] `PATCH /api/v1/mcp/tokens/{id}/revoke` revokes token, returns 404/409 correctly
- [ ] All backend tests pass
- [ ] Profile page shows MCP Tokens section with generate + list + revoke
- [ ] One-time token modal with copy button works
- [ ] Token masked in list after modal dismissal
- [ ] Revoke confirm dialog with optimistic removal works
- [ ] Frontend tests pass
- [ ] TypeScript clean (`./node_modules/.bin/tsc --noEmit`)

---

## Pre-Gilfoyle Self-Review Checklist

1. All `mcp_tokens` column names match `db-schema-spec.md §18` exactly
2. All Supabase calls in async routes use `run_in_executor`
3. No `try/except` returning `None`/`[]` on write operations
4. All Supabase writes scoped by `user_id`
5. Python→TypeScript field mapping correct (`last_used_at` snake_case on API, `lastUsedAt` NOT used — manual mapping in UI if needed)
6. Test count confirmed before handoff comment
