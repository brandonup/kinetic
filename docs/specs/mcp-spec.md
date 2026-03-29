# Kinetic MCP Server — Implementation Spec

**Status:** Approved
**Author:** Jared
**Date:** 2026-03-23
**Ticket:** KIN-286
**ADR:** `docs/adr-006-mcp-server.md` (KIN-317)
**PRD ref:** `docs/prd.md` §11 (MCP Context Access)

---

## §1 Overview

Kinetic exposes its context stack via MCP so external AI clients (Claude Desktop, ChatGPT, Cursor) can consume Kinetic's layered context outside the web UI. The MCP server is read-only — it assembles and returns context; the external client handles generation.

**Single endpoint:** `POST /api/v1/mcp/context`

**Key constraints (from MEMORY.md + ADR-006):**
- Per-user bearer tokens, revocable, generated in-app
- Platform-owned keys for all pipeline calls (embedding, framework reranker) — no BYOK in MCP
- Public agents accessible to any authenticated user; private agents owner-only
- Per-user daily rate limit (default 1,000 req/day), HTTP 429 on exceed
- No AgentInstance active memory exposed (Layer 6 omitted)
- No conversation history (Layer 4 omitted) — MCP is stateless

---

## §2 Authentication

Bearer token in the `Authorization` header.

**Request:**
```
POST /api/v1/mcp/context
Authorization: Bearer mcp_a1b2c3d4e5f6...
```

**Token validation (per ADR-006 §1–2):**
1. Extract bearer token from `Authorization` header
2. Compute `SHA-256(token)` → `token_hash`
3. Query: `SELECT * FROM mcp_tokens WHERE token_hash = $1 AND revoked_at IS NULL`
4. If no match → 401
5. Extract `user_id` from matched row
6. Fire-and-forget: update `last_used_at = NOW()` on the token row

**No caching.** SHA-256 is sub-microsecond; DB lookup is a single indexed query. Caching adds revocation delay with zero measurable benefit at MVP scale.

---

## §3 Request Validation

**Request body (JSON):**
```json
{
  "query": "string — required, the user's current question/prompt",
  "project_id": "uuid — optional",
  "agent_id": "uuid — optional",
  "company_id": "uuid — optional"
}
```

**Validation rules:**
1. At least one of `project_id`, `agent_id`, `company_id` must be present → 400 `missing_scope` if none
2. UUID format validation on all provided IDs → 400 `invalid_scope_params` if malformed
3. Entity existence check (query `projects`, `agent_definitions`, `companies` tables) → 404 `entity_not_found` if missing

---

## §4 Context Assembly

### §4.1 Validation Order (ADR-006 §4)

```
1. Auth         → 401 on invalid/revoked token
2. Rate limit   → 429 if daily cap exceeded (increment counter via UPSERT)
3. Scope        → 404 entity not found (anti-enumeration: includes access denied)
4. Assemble     → build context stack, run pipeline ops, return response
```

Rate limit before scope: prevents entity enumeration at scale.

### §4.2 Scoping Table — Parameters → Layers

| Parameters provided | Company resolution | Layers assembled |
|---|---|---|
| `project_id` only | Inferred from project's parent company | L1, L2, L3, L8 |
| `agent_id` only | No company layer | L1, L5, L7, L9 |
| `project_id` + `agent_id` | Inferred from project | L1, L2, L3, L5, L7, L8, L9 |
| `company_id` only | Explicit | L1, L2 |
| `company_id` + `agent_id` | Explicit | L1, L2, L5, L7, L9 |
| `company_id` + `project_id` | Explicit (must match project's company) | L1, L2, L3, L8 |
| `company_id` + `project_id` + `agent_id` | Explicit (must match) | L1, L2, L3, L5, L7, L8, L9 |

**Layer definitions:**

| Layer | Source | Content |
|---|---|---|
| L1 | User profile | `users.name` + `users.bio` |
| L2 | Company | `companies.name` + `companies.description` |
| L3 | Project instructions | `projects.instructions` |
| L4 | _(omitted)_ | No conversation history in MCP — stateless (ADR-006 §6) |
| L5 | Agent system prompt | `agent_definitions.instructions` |
| L6 | _(omitted)_ | AgentInstance active memory is private — not exposed via MCP |
| L7 | Matched framework | 4-step selection pipeline result (see §4.4) |
| L8 | Project KB | RAG retrieval against project's knowledge base (see §4.3) |
| L9 | Agent KB | RAG retrieval against agent's knowledge base (see §4.3) |

**Notes:**
- L4 (conversation history): omitted because MCP is stateless. No `conversation_id` parameter accepted.
- L6 (agent active memory): omitted. AgentInstance data is private to the invoking user within Kinetic.

### §4.3 RAG Retrieval (L8, L9)

When a scope includes a KB (project or agent):

1. Embed `query` using platform-owned key (`PLATFORM_OPENAI_KEY`, model `text-embedding-3-large`)
2. Cosine similarity search against scoped chunk embeddings in pgvector
3. Apply MMR re-ranking (same parameters as in-app RAG pipeline)
4. Apply similarity threshold (`FRAMEWORK_MIN_SIMILARITY` — skip injection if all chunks below threshold)
5. Assemble top-K chunks as context
6. Populate `sources` array in response metadata

**L8** is scoped to project KB chunks. **L9** is scoped to agent KB chunks. Both run independently when both scopes are present.

**If no chunks meet threshold:** layer is omitted, `sources` array is empty for that scope.

### §4.4 Framework Selection (L7)

When `agent_id` is present:

1. Embed `query` using platform-owned key
2. Run 3-step framework selection pipeline (MVP — reranker deferred):
   - Step 1: Embedding similarity on per-trigger vectors
   - Step 2: Trigger-count boost (multi-trigger resonance, +0.05 per extra trigger)
   - Step 3: Confidence gate (`FRAMEWORK_MIN_SIMILARITY = 0.55`)
   - _(Step 3 from full pipeline — Haiku reranker — deferred. Add when usage data shows framework mis-selection. Approved by Brandon 2026-03-24.)_
3. If match: inject winning framework whole as L7 context
4. If no match above threshold: omit L7, set `matched_framework_id: null`

### §4.5 Platform Key Isolation (ADR-006 §5)

| MCP Pipeline Step | Key Used | Model |
|---|---|---|
| Query embedding (RAG vector search) | `PLATFORM_OPENAI_KEY` | `text-embedding-3-large` |
| Framework selection — embedding similarity | `PLATFORM_OPENAI_KEY` | `text-embedding-3-large` |
| Context assembly (string concatenation) | No LLM call | N/A |

No BYOK keys are involved in MCP. All pipeline costs are platform-subsidized.

---

## §5 Response Shape

**Success (200):**
```json
{
  "context": "string — assembled context from all resolved layers",
  "metadata": {
    "layers_assembled": ["L1", "L2", "L3", "L5", "L7", "L8", "L9"],
    "token_count_estimate": 2450,
    "matched_framework_id": "uuid | null",
    "matched_framework_name": "string | null",
    "sources": [
      {
        "document_id": "uuid",
        "document_title": "string",
        "chunk_id": "uuid",
        "snippet": "string — first 200 chars of chunk",
        "similarity_score": 0.82,
        "scope": "project | agent"
      }
    ]
  }
}
```

**`token_count_estimate`:** `ceil(len(context) / 4)` — rough char-proxy estimate.

**`sources`:** populated from L8 and L9 RAG results. Empty array if no RAG results.

---

## §6 Access Control

Access control runs after auth and rate limiting, before context assembly.

**Anti-enumeration:** All ownership failures return 404 `entity_not_found` (not 403). This prevents MCP token holders from confirming whether entity UUIDs belong to other users. Follows GitHub/Stripe convention for cross-tenant boundary enforcement.

### §6.1 Project Access

If `project_id` is present:
- Verify `projects.user_id = authenticated_user_id`
- 404 `entity_not_found` if not owner (or does not exist)

### §6.2 Agent Access

If `agent_id` is present:
- `visibility = 'public'` → any authenticated user may access
- `visibility = 'private'` → only `agent_definitions.owner_id = authenticated_user_id`
- 404 `entity_not_found` if private and not owner (or does not exist)

### §6.3 Company Access

If `company_id` is present (and not just auto-resolved from `project_id`):
- Verify `companies.user_id = authenticated_user_id`
- 404 `entity_not_found` if not owner (or does not exist)

### §6.4 Cross-scope Validation

When `company_id` + `project_id` are both provided:
- Verify `projects.company_id = company_id` → 400 `scope_mismatch` if project belongs to a different company

---

## §7 Rate Limiting

Per-user daily rate limit using Supabase row with UPSERT (ADR-006 §3).

**Default cap:** 1,000 requests per user per calendar day (UTC).

**Per-user override:** `users.mcp_daily_limit` column. NULL = use default 1,000.

**Enforcement:**
1. Check: `SELECT request_count FROM mcp_rate_limits WHERE user_id = $1 AND date = CURRENT_DATE`
2. If no row → user hasn't made requests today → proceed
3. If `request_count >= daily_cap` → return 429
4. Increment (runs on every authenticated request, before scope check):
```sql
INSERT INTO mcp_rate_limits (user_id, date, request_count)
VALUES ($1, CURRENT_DATE, 1)
ON CONFLICT (user_id, date)
DO UPDATE SET request_count = mcp_rate_limits.request_count + 1;
```

**429 response:**
```json
{
  "error": "rate_limit_exceeded",
  "limit": 1000,
  "reset_at": "2026-03-24T00:00:00Z"
}
```

**Response headers (on all MCP responses):**
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 742
X-RateLimit-Reset: 1711324800
```

**429-specific header:**
```
Retry-After: 3600
```
(`Retry-After` = seconds until next UTC midnight)

---

## §8 Error Codes

All errors follow the standard shape:
```json
{
  "error": "error_code",
  "message": "Human-readable description"
}
```

| HTTP | Error code | When |
|---|---|---|
| 400 | `missing_scope` | No `project_id`, `agent_id`, or `company_id` provided |
| 400 | `invalid_scope_params` | Malformed UUID in scope parameters |
| 400 | `scope_mismatch` | `company_id` doesn't match project's company |
| 401 | `invalid_token` | Missing, invalid, or revoked bearer token |
| 404 | `entity_not_found` | Requested entity doesn't exist or user doesn't have access (anti-enumeration) |
| 429 | `rate_limit_exceeded` | Daily request cap exceeded |
| 500 | `internal_error` | Pipeline failure (embedding, framework selection, RAG) |

---

## §9 Token Management Endpoints

Users generate, view, and revoke MCP bearer tokens from the User Profile page.

### §9.1 Generate Token

**`POST /api/v1/mcp/tokens`**

Request:
```json
{
  "label": "string — required, max 64 chars, e.g. 'Claude Desktop', 'Cursor'"
}
```

Response (201):
```json
{
  "id": "uuid",
  "token": "mcp_a1b2c3d4e5f6... — shown ONCE, never returned again",
  "label": "Claude Desktop",
  "created_at": "2026-03-23T10:00:00Z"
}
```

**Backend:**
1. Generate raw token: `mcp_` + `os.urandom(32).hex()` (64 hex chars after prefix)
2. Hash: `SHA-256(raw_token)` → store as `token_hash` in `mcp_tokens` table
3. Store label, user_id, created_at
4. Return the raw token in the response — it is never stored or retrievable after this

### §9.2 List Tokens

**`GET /api/v1/mcp/tokens`**

Response (200):
```json
{
  "tokens": [
    {
      "id": "uuid",
      "label": "Claude Desktop",
      "token_hint": "mcp_••••••••",
      "created_at": "2026-03-23T10:00:00Z",
      "last_used_at": "2026-03-23T15:30:00Z | null"
    }
  ]
}
```

**`token_hint`:** always `mcp_••••••••` — the actual token value is never returned after generation.

**`last_used_at`:** null if the token has never been used. Displayed as "Never" in the UI.

No pagination in MVP.

### §9.3 Revoke Token

**`PATCH /api/v1/mcp/tokens/{id}/revoke`**

Response (200):
```json
{
  "id": "uuid",
  "revoked_at": "2026-03-23T16:00:00Z"
}
```

**Backend:** Sets `revoked_at = NOW()` on the token row. The token is immediately invalid — the next MCP request using this token will receive 401.

**Confirm dialog copy:** "Revoke '[label]'? Any client using this token will immediately lose access."

---

## §10 Implementation Tickets

| Ticket | Scope | Sections referenced |
|---|---|---|
| KIN-321 | MCP endpoint, auth, scope routing, context assembly (L1–L5) | §2, §3, §4.1, §4.2 |
| KIN-322 | RAG pipeline (L8, L9) + framework selection (L7) | §4.3, §4.4 |
| KIN-323 | Rate limiting | §7 |
| KIN-324 | Access control | §6 |
| KIN-325 | Token management UI | §9 |
