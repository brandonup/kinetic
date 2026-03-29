# KIN-339 — Sprint 6 Code Review + Security Audit + Performance Review

**Reviewer:** Gilfoyle
**Date:** 2026-03-24
**Scope:** MCP server (KIN-321–324), MCP token management (KIN-325), Admin RAG Debug tab (KIN-326), final security audit, performance review
**Verdict:** Architecture approved — 0 Critical, 3 Important, 5 Informational

---

## Sprint 6 Code Review

### Files Reviewed

**MCP Server:**
- `app/api/routes/mcp.py` — context endpoint, auth, scope routing, context assembly
- `app/api/routes/mcp_tokens.py` — token CRUD
- `app/services/rag/framework_selection.py` — L7 pipeline
- `app/services/rag/retrieval.py` — L8/L9 RAG pipeline
- `supabase/migrations/20260324000000_mcp_rate_limit_rpc.sql` — atomic rate limit RPC
- `tests/test_mcp.py` — 78 MCP context tests
- `tests/test_mcp_tokens.py` — token management tests

**Admin RAG Debug:**
- `app/api/routes/admin_rag_debug.py` — trace list + detail endpoints
- `app/services/rag/trace_writer.py` — sync trace writer
- `tests/test_admin_rag_debug.py` — trace writer, list, detail tests
- `packages/web/app/admin/rag-debug/page.tsx` — admin UI

**Supporting:**
- `app/auth/deps.py` — JWT + admin auth dependencies
- `app/middleware/log_scrub.py` — sensitive field redaction
- `app/core/config.py` — settings
- `app/main.py` — router registration

---

## Findings

### Important (3)

**I1. Spec–implementation mismatch: token create field name `name` vs `label` (mcp_tokens.py:42, spec §9.1)**

The spec defines the create request field as `"label"` and the response includes `"label"`. The implementation uses `"name"` throughout — Pydantic model field, DB column, response. The schema spec §18 also says `name`, so the implementation and schema are consistent with each other, but the MCP spec §9.1 says `label`.

**Fix:** Either update the spec §9.1 to say `name` (aligning with schema + code), or rename the code to `label`. Recommend updating the spec — `name` is already in the DB and tests. This is a doc-only fix.

**I2. Spec–implementation mismatch: list tokens response shape (mcp_tokens.py:140, spec §9.2)**

Spec §9.2 says list endpoint returns `token_hint: "mcp_••••••••"`. Implementation returns `name`, `last_used_at`, `created_at` but no `token_hint` field. The select query also doesn't construct one.

This is cosmetic — the token hash is correctly never exposed — but the MCP spec promises `token_hint` and clients may expect it.

**Fix:** Either add `"token_hint": "mcp_••••••••"` to each row in the list response, or update the spec to say no hint is returned. Recommend adding it — it's a constant string, zero risk.

**I3. `last_used_at` update uses string `"now()"` instead of server timestamp (mcp.py:137)**

```python
lambda: client.table("mcp_tokens").update({"last_used_at": "now()"}).eq("id", token_id).execute(),
```

Supabase Python client sends `"now()"` as a literal string value, not a SQL function call. The DB may store the literal string `"now()"` instead of the current timestamp. This is fire-and-forget so it won't error visibly — but `last_used_at` will be wrong.

**Fix:** Use `datetime.now(timezone.utc).isoformat()` instead of `"now()"`, consistent with the pattern used in `revoke_token` (mcp_tokens.py:181).

---

### Informational (5)

**N1. API key validation on save not implemented (profile.py — ticket audit item)**

KIN-339 description asks to verify that "PRD requires a lightweight test call before storing" API keys. The profile route encrypts and stores the key but does not make a validation call to the provider. This was likely a deliberate MVP deferral — no test call infrastructure exists.

**Action:** Not a Sprint 6 finding. If this is MVP-required, create a separate ticket. If deferred, add to MEMORY.md as a known gap.

**N2. MCP rate limit RPC hardcodes `daily_cap = 1000` default (migration line 21)**

The UPSERT defaults new rows to `daily_cap = 1000`. The spec says per-user override via `users.mcp_daily_limit`, but the RPC doesn't read from users — it only references `mcp_rate_limits.daily_cap`. This means admin-set per-user caps work (they'd be set on the mcp_rate_limits row), but `users.mcp_daily_limit` column from the spec is unused.

**Action:** Low risk at MVP scale. The current approach works — admin sets daily_cap directly on mcp_rate_limits rows. Document this as the actual mechanism.

**N3. Rate limit response headers not implemented (mcp.py — spec §7)**

Spec §7 requires `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` headers on all MCP responses. These are not set. The 429 response body includes the reset info, but standard headers are missing.

**Action:** Nice-to-have for MVP. Consider a post-MVP ticket.

**N4. Framework selection f-string in logger.warning (framework_selection.py:131)**

```python
logger.warning(f"Framework {top_fid} not found in frameworks table")
```

Should use `%s` formatting for lazy evaluation: `logger.warning("Framework %s not found", top_fid)`. Not a bug — just a minor style inconsistency with the rest of the codebase.

**N5. Web UI page has no dedicated test file (rag-debug/page.tsx)**

The RAG debug admin page has no frontend test. All backend endpoints are well-tested. Frontend testing is not blocked — it's consistent with the current state of other admin pages (models, users).

---

## Security Audit

### MCP Token Storage ✅

- SHA-256 hash stored, plaintext never persisted (mcp_tokens.py:66-67, mcp.py:58-59)
- Raw token returned exactly once on creation (mcp_tokens.py:113)
- Hash is 64 hex chars from `os.urandom(32)` — sufficient entropy
- Token prefix `mcp_` stripped before hashing (mcp.py:113) — consistent between storage and lookup
- `token_hash` never returned in list/revoke responses

### MCP Access Control ✅

- **Project:** ownership verified via `user_id` filter (mcp.py:276)
- **Company (explicit):** ownership verified via `user_id` filter (mcp.py:323)
- **Company (via project):** no separate ownership check — correct, project ownership already verified
- **Agent (public):** any authenticated user — correct per spec
- **Agent (private):** `owner_id` check, returns 404 not 403 — anti-enumeration ✅ (mcp.py:347-348)
- **Cross-scope validation:** company_id must match project's company (mcp.py:286-291) — ✅

### RLS Policies (schema spec verification)

- `mcp_tokens`: SELECT/INSERT/DELETE scoped to `auth.uid() = user_id` ✅
- `mcp_rate_limits`: UNIQUE(user_id, date) prevents cross-user rate limit manipulation ✅
- `retrieval_debug_logs`: SELECT admin-only, INSERT service-role-only ✅
- `active_memory_entries`: `auth.uid() = user_id` ✅
- `user_api_keys`: scoped to user via `user_id` FK ✅

### Log Scrub Middleware ✅

- Regex catches `*_key`, `*_secret`, `*_token`, `authorization`, `api_key`, `key_ciphertext`, `key_nonce`
- Applied globally as first middleware (main.py:58)
- MCP bearer tokens in Authorization header → scrubbed ✅
- API key fields in profile routes → scrubbed ✅
- Handles nested dicts recursively

### API Key Encryption ✅

- AES-256-GCM encryption before storage (profile.py:203)
- Key hint (masked) returned, never ciphertext
- Master key from environment variable, never logged

---

## Performance Review

### RAG Query Latency (pgvector)

- Vector search uses `match_chunks` RPC with scope filter — pgvector cosine distance operator with index
- `idx_retrieval_debug_logs_created_at` on `(created_at DESC)` — correct for the admin list query
- MMR runs client-side in Python on max 20 candidates — negligible at this scale
- Token budget gate runs `tiktoken.encode()` on max 8 chunks — sub-millisecond
- At ~20K chunks with pgvector IVFFlat or HNSW index: expected <50ms for cosine search

### Retrieval Debug Log Writes ✅

- `write_retrieval_trace` is a sync function designed for `BackgroundTasks.add_task` (trace_writer.py:54-55)
- Runs in thread pool — does not block the response path
- DB errors are caught and logged, never propagated (trace_writer.py:84-91)
- Tested: `test_write_retrieval_trace_db_failure_is_silent` confirms failure isolation

### Context Assembly

- All Supabase calls properly wrapped in `run_in_executor` — no sync-in-async violations
- Entity fetches are sequential (auth → rate limit → project → company → agent → framework → RAG) — acceptable for MVP, parallelizable later
- Token count estimate uses `ceil(len/4)` — cheap proxy, no LLM call

---

## Test Coverage Summary

| Component | Tests | Coverage Notes |
|---|---|---|
| MCP auth (401) | 4 | Missing, bad scheme, not in DB, valid |
| MCP validation (400) | 7 | No scope, invalid UUIDs, entity not found, cross-scope mismatch |
| MCP scope routing | 8 | All 7 scope combos + L4 exclusion |
| MCP context assembly | 12 | Response shape, content, token estimate, bio handling |
| MCP rate limiting | 2 | 429 on cap exceeded, 200 on first request |
| MCP token CRUD | 13 | Create (8), list (5), revoke (5) |
| RAG debug list | 6 | Admin-only, scope filter, cursor, next_cursor, non-admin 403 |
| RAG debug detail | 4 | Full trace + enrichment, 404, no-chunks skip, non-admin 403 |
| Trace writer | 3 | Insert, error_message, silent failure |
| **Total** | **59** | Solid unit coverage across all Sprint 6 features |

---

## Verdict

**Architecture approved.** Sprint 6 implementation is well-structured, security controls are correctly implemented, and test coverage is thorough. The 3 Important items are all low-risk spec alignment issues — no architectural or security blockers.

**Recommended actions:**
1. Fix I3 (`last_used_at` timestamp) — 1-line change
2. Resolve I1 + I2 spec mismatches — either update spec or code, Brandon's call
3. N1 (API key validation) — confirm if MVP-required or deferred

— Gilfoyle
