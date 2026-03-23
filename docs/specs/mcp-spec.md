# MCP Server Spec

**Status:** Spec — Sprint 4
**Author:** Jared
**Issue:** KIN-286
**Ships:** Sprint 6
**Gates:** Gilfoyle MCP ADR (Sprint 5), Big Head implementation (Sprint 6)

---

## 1. Overview

The Kinetic MCP server exposes assembled context to external clients (Claude Desktop, Cursor, etc.). It does **not** run generation — the external client drives the LLM call. Kinetic assembles and returns context only.

Each request authenticates via a bearer token, declares a scope (project, agent, and/or company), and receives an assembled context string plus structured metadata.

---

## 2. Authentication

### 2.1 Token model

- **Per-user bearer tokens.** Each user can generate multiple tokens — one per external client integration.
- **Storage:** `mcp_tokens` table. Fields: `id`, `user_id`, `label` (user-assigned), `token_hash` (SHA-256), `created_at`, `last_used_at`, `revoked_at` (null = active).
- **Validation:** On each request, hash the incoming token and look up `mcp_tokens` where `token_hash = hash AND revoked_at IS NULL`. Resolve to `user_id`. Reject with 401 if not found or revoked.
- **Token format:** 32-byte random value, base64url-encoded. Prefix `mcp_` for recognisability. Example: `mcp_<base64url(32 bytes)>`.

### 2.2 Token lifecycle

| Event | Behaviour |
|-------|-----------|
| Generate | Shown to user once in plaintext. Immediately masked (shown as `mcp_••••••••`) after copy/dismiss. |
| List | Label, created date, last used date. Token value never shown again. |
| Revoke | Sets `revoked_at = now()`. Immediate effect — next request with that token gets 401. |
| Rotation | No automatic rotation in MVP. User manually revokes and generates a replacement. |

### 2.3 HTTP header

```
Authorization: Bearer mcp_<token>
```

---

## 3. API Endpoint

```
POST /api/v1/mcp/context
```

### 3.1 Request body

```json
{
  "query": "string (required) — the user's prompt, used for RAG embedding",
  "project_id": "uuid (optional)",
  "agent_id": "uuid (optional)",
  "company_id": "uuid (optional)"
}
```

At least one of `project_id`, `agent_id`, or `company_id` must be present. If none are provided, return 400.

### 3.2 Response body (200 OK)

```json
{
  "context": "string — assembled context, ready to prepend to the external LLM prompt",
  "metadata": {
    "layers_assembled": ["L1", "L3", "L4", "L8"],
    "sources": [
      {
        "document_id": "uuid",
        "document_title": "string",
        "chunk_index": 0,
        "similarity_score": 0.87
      }
    ],
    "matched_framework_id": "uuid | null",
    "matched_framework_name": "string | null",
    "token_count_estimate": 4200
  }
}
```

---

## 4. Scoping

### 4.1 Parameters

| Param | Type | Description |
|-------|------|-------------|
| `project_id` | UUID | Scopes to a specific project. User must own the project. |
| `agent_id` | UUID | Scopes to an agent. User must own it (private) or it must be public. |
| `company_id` | UUID | Scopes to company-level context. User must be a member of the company. |

All three are optional and combinable. If `project_id` is provided, its owning company is resolved automatically — `company_id` is redundant but accepted.

### 4.2 Scoping table — context layers per combination

| `project_id` | `agent_id` | `company_id` | Layers assembled | Notes |
|:---:|:---:|:---:|---|---|
| ✓ | — | — | L1, L2, L3 (project instructions), L4 (conv history stub), L8 (project KB RAG) | Standard project context |
| ✓ | ✓ | — | L1, L2, L3, L5 (agent system prompt), L7 (framework selection), L8 (project KB RAG), L9 (agent KB RAG) | Full project+agent context. L6 excluded (see §5). |
| — | ✓ | — | L1, L2, L5, L7, L9 | Agent context only, no project scope |
| — | — | ✓ | L1, L2, L3 (company instructions) | Company-level context only |
| ✓ | — | ✓ | Same as `project_id` only — company is resolved from project | `company_id` redundant; accepted without error |
| ✓ | ✓ | ✓ | Same as `project_id` + `agent_id` | `company_id` redundant; accepted without error |
| — | ✓ | ✓ | L1, L2, L3 (company instructions), L5, L7, L9 | Company + agent context |
| — | — | — | **400 Bad Request** | At least one scope param required |

**Layer key** (Sprint 3/4 definitions):

| Layer | Name | Description |
|-------|------|-------------|
| L1 | Platform defaults | Global system instructions |
| L2 | User preferences | BYOK config, display prefs |
| L3 | Scope instructions | Project instructions or company instructions depending on scope |
| L4 | Conversation history stub | Not meaningful in MCP context; omitted if no `conversation_id` |
| L5 | Agent system prompt | `agent_definitions.instructions` |
| L6 | AgentInstance active memory | **Excluded from MCP** (see §5) |
| L7 | Framework selection result | Best-matching framework, injected whole |
| L8 | Project KB RAG | Top-k chunks from project knowledge base |
| L9 | Agent KB RAG | Top-k chunks from agent knowledge base |

### 4.3 RAG pipeline (L8, L9)

When L8 or L9 applies:

1. Embed `query` using the platform embedding key (not BYOK — MCP requests use the platform key regardless of user BYOK settings).
2. Run cosine similarity search against the relevant KB vector store.
3. Apply MMR re-ranking and similarity threshold (same params as in-app RAG — ref `docs/rag-architecture.md`).
4. Inject top-k chunks into context. Include citations in metadata `sources` array.

### 4.4 Framework selection pipeline (L7)

When `agent_id` is present:

1. Embed `query` using the platform embedding key.
2. Run the 4-step framework selection pipeline (ref `docs/adr-005-agents-framework-selection.md`).
3. Inject the winning framework whole as L7.
4. Return `matched_framework_id` and `matched_framework_name` in metadata.
5. If no framework matches above threshold, L7 is omitted and `matched_framework_id` is null.

---

## 5. What MCP Exposes vs. Excludes

| | Exposed | Reason |
|---|---|---|
| L5 — Agent system prompt | ✓ | Core agent context; needed by external clients |
| L7 — Framework selection result | ✓ | Matching framework is the primary value-add |
| L8 — Project KB RAG | ✓ | KB context is the key retrieval output |
| L9 — Agent KB RAG | ✓ | Agent KB context is the key retrieval output |
| L6 — AgentInstance active memory | **Excluded** | Active memory is per-session state; leaking it to external clients creates privacy and consistency issues. Excluded in MVP. Re-evaluate in post-MVP. |
| Thought Stream | **Excluded** | Not in MVP |
| Personal user data | **Excluded** | Beyond what's required for context assembly |
| Raw DB records | **Excluded** | Only assembled context string is returned |

---

## 6. Access Control

### 6.1 Project access

User must be the owner of the project (`projects.user_id = authenticated_user_id`). Return 403 if not.

### 6.2 Agent access

- **Public agents** (`agent_definitions.visibility = 'public'`): accessible to any authenticated user.
- **Private agents** (`agent_definitions.visibility = 'private'`): owner only (`agent_definitions.user_id = authenticated_user_id`). Return 403 if not.

### 6.3 Company access

User must be a member of the company (record in `company_members` or equivalent). Return 403 if not.

---

## 7. Rate Limiting

- **Default cap:** 1,000 requests per user per calendar day (UTC).
- **Admin-configurable:** per-user override storable in `users.mcp_daily_limit`. Null = default.
- **Enforcement:** checked on each request before processing.
- **Exceeded:** HTTP 429 with response headers:

```
HTTP/1.1 429 Too Many Requests
Retry-After: <seconds until next UTC midnight>
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 0
X-RateLimit-Reset: <Unix timestamp of next UTC midnight>
```

Body:

```json
{
  "error": "rate_limit_exceeded",
  "limit": 1000,
  "reset_at": "2026-03-24T00:00:00Z"
}
```

---

## 8. Error Responses

All errors return JSON bodies.

| Status | `error` value | Condition |
|--------|---------------|-----------|
| 400 | `missing_scope` | No scope param provided |
| 400 | `invalid_scope_params` | Unrecognised UUID format or unknown entity type |
| 401 | `invalid_token` | Token not found or revoked |
| 403 | `access_denied` | Authenticated user does not have access to the requested entity |
| 404 | `entity_not_found` | `project_id`, `agent_id`, or `company_id` does not exist |
| 429 | `rate_limit_exceeded` | Daily cap reached |
| 500 | `internal_error` | Unexpected server error |

Error body shape:

```json
{
  "error": "error_value",
  "message": "Human-readable description"
}
```

---

## 9. MCP Token Management UI

Located at: **User Profile → MCP Tokens section**

### 9.1 Generate token

1. User clicks **"Generate new token"**.
2. User enters a label (e.g. "Claude Desktop", "Cursor"). Required, max 64 chars.
3. Token is generated and displayed **once** in a modal with a copy button.
4. Modal copy prompt: *"Copy this token now. You won't be able to see it again."*
5. After dismissal, token is shown in the list as `mcp_••••••••` (masked).

### 9.2 Token list

Columns: **Label**, **Created**, **Last used**, **Actions**

- Label: user-assigned string
- Created: formatted date
- Last used: formatted date, or "Never" if unused
- Actions: **Revoke** button per row

No pagination in MVP (users unlikely to have more than ~5 tokens).

### 9.3 Revoke

- Revoke button triggers a confirmation dialog: *"Revoke '[label]'? Any client using this token will immediately lose access."*
- On confirm: `PATCH /api/v1/mcp/tokens/{id}/revoke` → sets `revoked_at`.
- Token disappears from the list immediately (optimistic UI update).

---

## 10. API Endpoints Summary

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/mcp/context` | Assemble and return context for the given scope + query |
| `POST` | `/api/v1/mcp/tokens` | Generate a new MCP token |
| `GET` | `/api/v1/mcp/tokens` | List active tokens for the authenticated user |
| `PATCH` | `/api/v1/mcp/tokens/{id}/revoke` | Revoke a specific token |

All token management endpoints use standard JWT auth (not MCP bearer token). The `/mcp/context` endpoint uses MCP bearer token auth.

---

## 11. DB Schema Reference

### `mcp_tokens` table (from `docs/db-schema-spec.md`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `user_id` | UUID FK → users | |
| `label` | text | User-assigned name, max 64 chars |
| `token_hash` | text | SHA-256 of the raw token. Unique. |
| `created_at` | timestamptz | |
| `last_used_at` | timestamptz \| null | Updated on each successful use |
| `revoked_at` | timestamptz \| null | null = active |

Index: `token_hash` (unique), `user_id`.

---

## 12. MCP Connector Per-Agent (ref: `docs/specs/agents.md` §9)

Each `AgentDefinition` has an optional `mcp_url` field — the URL of an external MCP server that the agent can connect to as a **client** (separate from Kinetic's own MCP server which Kinetic operates as a **server**).

The MCP spec in this document covers only the **Kinetic-as-MCP-server** surface. The agent-as-MCP-client integration (using `mcp_url`) is out of scope for this spec and is handled in `docs/specs/agents.md` §9.

---

## Done when

- [x] Spec written and saved to `docs/specs/mcp-spec.md`
- [x] Scoping table complete (all valid param combinations documented in §4.2)
- [x] Spec unblocks Gilfoyle MCP ADR (Sprint 5)
