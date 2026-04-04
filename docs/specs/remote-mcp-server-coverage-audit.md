# Remote MCP Server — Coverage Audit

**Date:** 2026-03-29
**Author:** Jared
**Purpose:** Map every discrete behavior from the spec, PRD, crypto spike, and ADR to an implementation ticket. Flag any gaps before ticket creation.

**Sources:**
- `docs/specs/remote-mcp-server-spec.md` (Approved)
- `docs/specs/remote-mcp-server-prd.md` (Draft)
- `docs/spike-crypto-port-deno.md` (Complete)
- `docs/adr-008-remote-mcp-edge-function.md` (Proposed)

**Decision updates (from PRD session, not yet in spec):**
- Slugs are **globally unique** (`UNIQUE(slug)`), not per-owner
- Public agents are accessible via MCP (resolve_agent matches own OR public)
- Agent creation returns "name taken" if slug exists
- Cost documentation deferred

---

## Spec Step 1: Scaffold

| # | Behavior | Ticket |
|---|----------|--------|
| 1.1 | `supabase/functions/kinetic-mcp/` directory exists | T3 |
| 1.2 | `index.ts` — Hono app + MCP server + route handler | T2 |
| 1.3 | `deno.json` — import map (supabase-js, mcp sdk, hono) | T3 |
| 1.4 | `auth.ts` — token validation + rate limiting | T1 |
| 1.5 | `crypto.ts` — HKDF + AES-GCM decryption | T1 |
| 1.6 | `embedding.ts` — OpenAI embedding helper | T1 |
| 1.7 | `tools.ts` — 5 tool implementations | T2 |
| 1.8 | `prompts.ts` — dynamic prompt registration | T2 |

## Spec Step 2: Auth

| # | Behavior | Ticket |
|---|----------|--------|
| 2.1 | Extract token from `Authorization: Bearer mcp_<token>` header | T1 |
| 2.2 | Extract token from `?key=` query param (fallback) | T1 |
| 2.3 | Header takes precedence if both present | T1 |
| 2.4 | Strip `mcp_` prefix from token | T1 |
| 2.5 | SHA-256 hash via `crypto.subtle.digest` | T1 |
| 2.6 | Look up hash in `mcp_tokens` WHERE `revoked_at IS NULL` | T1 |
| 2.7 | Return `user_id` from matched token | T1 |
| 2.8 | Fire-and-forget update to `last_used_at` | T1 |
| 2.9 | Call `mcp_check_and_increment_rate_limit` RPC with `p_date = new Date().toISOString().split('T')[0]` | T1 |
| 2.10 | Fail-open on rate limit RPC error (don't block MCP if RPC is down) | T1 |
| 2.11 | Reject revoked tokens | T1 |
| 2.12 | Reject invalid/unknown tokens | T1 |

## Spec Step 3: Crypto

| # | Behavior | Ticket |
|---|----------|--------|
| 3.1 | Load master key from `API_KEY_ENCRYPTION_KEY` env var (base64-encoded 32 bytes) | T1 |
| 3.2 | Validate master key is exactly 32 bytes after decode | T1 |
| 3.3 | HKDF-SHA256: salt = `new Uint8Array(32)` (32 zero bytes, NOT empty buffer) | T1 |
| 3.4 | HKDF-SHA256: info = `user_id` encoded as UTF-8 | T1 |
| 3.5 | HKDF-SHA256: output = 32 bytes (256-bit derived key) | T1 |
| 3.6 | AES-256-GCM: 12-byte nonce | T1 |
| 3.7 | AES-256-GCM: no AAD (additionalData omitted) | T1 |
| 3.8 | Parse Supabase bytea format: handle `\x`-prefixed hex → binary | T1 |
| 3.9 | Parse plain hex as fallback (safety measure per crypto spike) | T1 |
| 3.10 | AES-GCM tag is appended to ciphertext — no splitting needed (per crypto spike) | T1 |

## Spec Step 4: Embedding

| # | Behavior | Ticket |
|---|----------|--------|
| 4.1 | Decrypt user's OpenAI key from `user_api_keys` table using crypto module | T1 |
| 4.2 | Call OpenAI `POST /v1/embeddings` with model `text-embedding-3-large` | T1 |
| 4.3 | Return embedding as `number[]` (3072 dimensions) | T1 |
| 4.4 | RPCs expect `extensions.vector(3072)`, not `public.vector` — verify JSON array cast | T1 |
| 4.5 | If user has no OpenAI key: return `"Error: No OpenAI API key configured — add one in Kinetic settings to use this tool"` | T1 |

## Spec Step 5: Prompts

| # | Behavior | Ticket |
|---|----------|--------|
| 5.1 | Query user's own `agent_instances` JOIN `agent_definitions` | T2 |
| 5.2 | Also include public agents (`visibility = 'public'`) from other users | T2 |
| 5.3 | Prompt name = agent slug (e.g., "nate") | T2 |
| 5.4 | Prompt description = agent's description or first line of instructions | T2 |
| 5.5 | Prompt body = orchestration instructions (call all 4 tools, adopt persona, use frameworks/KB as internal reasoning) | T2 |
| 5.6 | Port orchestration logic from the `/nate` skill pattern | T2 |
| 5.7 | Prompts generated per-request based on authenticated user | T2 |
| 5.8 | New agent created in Kinetic → appears in MCP on next request (no reconfiguration) | T2 |

## Spec Step 6: Tools — `resolve_agent`

| # | Behavior | Ticket |
|---|----------|--------|
| 6.1 | Shared `resolve_agent(user_id, slug)` helper used by all agent-accepting tools | T2 |
| 6.2 | Query `agent_definitions` WHERE `slug = slug` — globally unique, one result | T2 |
| 6.3 | Verify resolved agent is owned by user OR `visibility = 'public'` | T2 |
| 6.4 | If agent is private and not owned by user: return error | T2 |
| 6.5 | If no slug match: return `"Error: Agent '<slug>' not found for this user"` | T2 |
| 6.6 | Query `agent_instances` WHERE `agent_definition_id` AND `user_id` → get `instance_id` | T2 |
| 6.7 | If no instance exists: auto-create one (`INSERT INTO agent_instances`) | T2 |
| 6.8 | Return `{ definition_id, instance_id, name, instructions }` | T2 |

## Spec Step 6: Tools — Tool Definitions

| # | Behavior | Ticket |
|---|----------|--------|
| 6.9 | `list_kinetic_agents`: query user's own agents + public agents, return name + slug + description | T2 |
| 6.10 | `list_kinetic_agents`: include ownership indicator (own vs public) | T2 |
| 6.11 | `list_kinetic_agents`: empty agent list → return empty list (not error) | T2 |
| 6.12 | `get_agent_persona`: resolve via `resolve_agent`, return `instructions` | T2 |
| 6.13 | `get_agent_persona`: empty/null instructions → return empty string (not error) | T2 |
| 6.14 | `get_active_memory`: resolve via `resolve_agent`, use `instance_id` (NOT `definition_id`) | T2 |
| 6.15 | `get_active_memory`: query `active_memory_entries` WHERE `agent_instance_id` AND `user_id` | T2 |
| 6.16 | `get_active_memory`: no memory entries → return empty list (not error) | T2 |
| 6.17 | `select_framework`: resolve, check for `frameworks` rows | T2 |
| 6.18 | `select_framework`: no frameworks → return informational message, not error | T2 |
| 6.19 | `select_framework`: frameworks exist → embed query, call `match_framework_triggers` RPC scoped to `definition_id` | T2 |
| 6.20 | `select_framework`: multi-trigger boost applied | T2 |
| 6.21 | `select_framework`: confidence gate at 0.55 | T2 |
| 6.22 | `search_knowledge_base`: resolve, check for KB (`knowledge_bases` WHERE `agent_definition_id`) | T2 |
| 6.23 | `search_knowledge_base`: no KB → return informational message, not error | T2 |
| 6.24 | `search_knowledge_base`: KB exists → embed query, call `match_chunks` RPC | T2 |
| 6.25 | `search_knowledge_base`: filter threshold 0.3, top 8 results | T2 |

## Spec Step 6: Tools — Error Convention

| # | Behavior | Ticket |
|---|----------|--------|
| 6.26 | All errors returned as plain text `"Error: <description>"` | T2 |
| 6.27 | No JSON error objects, no HTTP status codes in MCP response | T2 |
| 6.28 | Errors are for failures (auth, missing agent, missing BYOK key), not for missing optional resources | T2 |

## Spec Step 7: Entry Point

| # | Behavior | Ticket |
|---|----------|--------|
| 7.1 | Create Hono app | T2 |
| 7.2 | Per-request flow: authenticate → create McpServer → register tools + prompts → handle transport | T2 |
| 7.3 | Streamable HTTP transport: POST for requests, GET for server events | T2 |
| 7.4 | Fully stateless — new McpServer per request, no notifications/subscriptions | T2 |

## Spec Step 8: Deployment

| # | Behavior | Ticket |
|---|----------|--------|
| 8.1 | Set `API_KEY_ENCRYPTION_KEY` secret via `supabase secrets set` | T3 |
| 8.2 | Deploy with `supabase functions deploy kinetic-mcp --no-verify-jwt` | T3 |
| 8.3 | `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` auto-injected (no manual config) | T3 |

## Spec Step 9: Slug Migration

| # | Behavior | Ticket |
|---|----------|--------|
| 9.1 | Migration: `ALTER TABLE agent_definitions ADD COLUMN slug text NOT NULL DEFAULT ''` | T3 |
| 9.2 | Constraint: `UNIQUE (slug)` — globally unique | T3 |
| 9.3 | Backfill: lowercase name | T3 |
| 9.4 | Backfill: replace spaces and special chars with hyphens, strip leading/trailing hyphens | T3 |
| 9.5 | Backfill: deduplicate collisions globally by appending `-2`, `-3`, etc. | T3 |
| 9.6 | Backfill: handle edge case — empty/special-char-only names produce valid slugs | T3 |
| 9.7 | Agent creation API: check slug uniqueness before INSERT, return "name taken" if exists | T3 |
| 9.8 | Update `db-schema-spec.md §8` with slug column + `uq_agent_definitions_slug` index | T3 |
| 9.9 | Application code sets slug on agent creation (lowercase, hyphenated) | T3 |

## Spec Step 10: User Setup

| # | Behavior | Ticket |
|---|----------|--------|
| 10.1 | Token generation via existing Kinetic UI flow | T2 |
| 10.2 | Connection URL format: `https://<PROJECT_REF>.supabase.co/functions/v1/kinetic-mcp?key=mcp_<token>` | T2 |
| 10.3 | Claude Desktop: Settings → Connectors → Add custom connector → paste URL | T2 |
| 10.4 | Claude Code: `claude mcp add --transport http` → paste URL | T2 |

---

## Crypto Spike Additions (not in spec, from `spike-crypto-port-deno.md`)

| # | Behavior | Ticket |
|---|----------|--------|
| CS.1 | Run `generate_test_vectors.py` (Python) to produce deterministic test values | T1 |
| CS.2 | Run `validate_test_vectors.ts` (Deno) to confirm bit-exact match | T1 |
| CS.3 | Test: derived key hex matches Python output exactly | T1 |
| CS.4 | Test: `decryptApiKey()` returns original plaintext exactly | T1 |
| CS.5 | Test: `byteaToUint8Array("\\xaabb...")` parses correctly | T1 |
| CS.6 | If test vectors fail: fall back to proxying decryption through FastAPI (see spike §Recommendation fallback) | T1 |
| CS.7 | `deriveKey` vs `deriveBits` — use `deriveBits` for exportable key comparison in tests, `deriveKey` for production decrypt | T1 |
| CS.8 | Create test vector scripts at `supabase/functions/kinetic-mcp/test-vectors/` | T1 |

---

## ADR-008 Additions (not in spec)

| # | Behavior | Ticket |
|---|----------|--------|
| ADR.1 | Embedding cost documentation for users (~$0.01/day) | **Deferred** |
| ADR.2 | Review trigger: if cold starts exceed 5s → evaluate alternatives | N/A (monitoring) |

---

## Edge Cases

| # | Case | Expected Behavior | Ticket |
|---|------|-------------------|--------|
| E.1 | Agent has no KB | `search_knowledge_base` returns informational message, LLM omits KB layer | T2 |
| E.2 | Agent has no framework library | `select_framework` returns informational message, LLM omits framework layer | T2 |
| E.3 | Agent has no instructions (empty system prompt) | `get_agent_persona` returns empty string | T2 |
| E.4 | Agent instance doesn't exist (never invoked) | `resolve_agent` auto-creates instance | T2 |
| E.5 | User has no BYOK OpenAI key | Embedding tools return clear error; non-embedding tools work normally | T1/T2 |
| E.6 | User has no agents | `list_kinetic_agents` returns empty list; no MCP prompts registered | T2 |
| E.7 | Agent instance exists, no memory entries | `get_active_memory` returns empty list | T2 |
| E.8 | Two users try to create agent with same slug | Second user gets "name taken" error | T3 |
| E.9 | Slug from name with only special chars (e.g., "!!!") | Backfill produces valid slug or assigns fallback (e.g., `agent-1`) | T3 |
| E.10 | Token in URL query param | Works but logged in server access logs | T1 |
| E.11 | Both header and query param token provided | Header takes precedence | T1 |
| E.12 | Revoked token | Auth fails, returns error | T1 |
| E.13 | Rate limit exceeded | RPC enforced, request rejected | T1 |
| E.14 | Rate limit RPC itself errors | Fail-open — request proceeds | T1 |
| E.15 | HKDF salt mismatch (Deno vs Python) | Test vectors catch pre-integration; fallback to FastAPI proxy | T1 |
| E.16 | `extensions.vector(3072)` vs `public.vector` | Must use `extensions.vector`; verify JSON array cast in Deno | T1 |
| E.17 | Cold start latency | 2-3s on first request after ~5 min idle; acceptable | N/A |
| E.18 | Public agent invoked by non-owner | `resolve_agent` resolves it; auto-creates `agent_instance` for invoking user; memory isolated per instance | T2 |
| E.19 | `list_kinetic_agents` includes public agents | Returns both own + public, with ownership indicator | T2 |
| E.20 | BYOK key decryption succeeds but OpenAI API rejects key | Return `"Error: OpenAI API error — <message>"` | T1 |
| E.21 | `match_chunks` / `match_framework_triggers` returns empty (below threshold) | Return empty results; distinct from "no KB/frameworks configured" (which returns informational message before calling RPC) | T2 |
| E.22 | Very long agent name → very long slug | Truncate slug to reasonable length (e.g., 60 chars) before uniqueness check | T3 |

---

## Verification Mapping

| # | Verification Step (from spec §Verification) | Ticket |
|---|----------------------------------------------|--------|
| V.1 | Crypto cross-check: encrypt with Python, decrypt with TypeScript — must match | T1 |
| V.2 | Auth: MCP token accepted, invalid/revoked tokens rejected | T1 |
| V.3 | Prompts: connect from Claude Desktop, agent names appear as MCP prompts | T2 |
| V.4 | Tools: test each tool with known agent — persona, memory, frameworks, KB all return | T2 |
| V.5 | Rate limiting: RPC called and enforced | T1 |
| V.6 | Multi-client: test in Claude Desktop (Connectors) AND Claude Code (`claude mcp add --transport http`) | T2 |

---

## Proposed Tickets

### T1: Auth + Crypto + Embedding

**Scope:** Spec Steps 2, 3, 4 + crypto spike test vectors
**Depends on:** Nothing (foundation)
**Estimate:** 2 (full day)

**Done-when:**
1. `auth.ts` extracts token from `Authorization: Bearer mcp_<token>` header (preferred) or `?key=` query param; header takes precedence (2.1–2.3)
2. Token stripped of `mcp_` prefix, SHA-256 hashed (2.4–2.5)
3. Hash looked up in `mcp_tokens` WHERE `revoked_at IS NULL`; returns `user_id` (2.6–2.7)
4. `last_used_at` updated fire-and-forget (2.8)
5. `mcp_check_and_increment_rate_limit` RPC called with `p_date`; fail-open on error (2.9–2.10)
6. Invalid/revoked tokens rejected with error (2.11–2.12)
7. `crypto.ts` loads master key from env var, validates 32 bytes (3.1–3.2)
8. HKDF-SHA256 with salt = 32 zero bytes, info = user_id UTF-8, output = 32 bytes (3.3–3.5)
9. AES-256-GCM with 12-byte nonce, no AAD (3.6–3.7)
10. Bytea parsing handles `\x`-prefixed hex and plain hex (3.8–3.9)
11. AES-GCM tag appended to ciphertext — no splitting (3.10)
12. `embedding.ts` decrypts user's OpenAI key from `user_api_keys` (4.1)
13. Calls OpenAI embeddings API with `text-embedding-3-large`, returns `number[]` (4.2–4.3)
14. JSON array casts correctly to `extensions.vector(3072)` via `supabase.rpc()` (4.4)
15. No OpenAI key → clear error message (4.5)
16. Cross-language test vectors: Python generates, Deno validates, derived key + decryption match exactly (CS.1–CS.5)
17. Test vector scripts at `kinetic-mcp/test-vectors/` (CS.8)
18. If vectors fail: documented fallback path to FastAPI proxy (CS.6)
19. OpenAI API error (bad key, rate limit) returns clear error (E.20)

**Note:** The `last_used_at` fire-and-forget update must actually complete in the Edge Function runtime. Test that the timestamp updates in the DB — don't assume dangling promises run.

**Verification:** V.1 (crypto cross-check), V.2 (auth), V.5 (rate limiting)

---

### T2: Tools + Prompts + Entry Point

**Scope:** Spec Steps 5, 6, 7, 8 + all resolve_agent behaviors + edge cases + deployment
**Depends on:** T1, T3
**Estimate:** 2 (full day)

**Done-when:**
1. `resolve_agent(user_id, slug)` queries `agent_definitions` by slug (globally unique) (6.1–6.2)
2. Resolved agent verified: owned by user OR `visibility = 'public'` (6.3)
3. Private agent not owned by user → error (6.4)
4. No slug match → error with slug name (6.5)
5. Query `agent_instances` for user + definition; auto-create if missing (6.6–6.7)
6. Returns `{ definition_id, instance_id, name, instructions }` (6.8)
7. `list_kinetic_agents` returns own agents + public agents with name, slug, description, ownership indicator (6.9–6.11)
8. `get_agent_persona` returns instructions; empty instructions → empty string (6.12–6.13)
9. `get_active_memory` uses `instance_id`, queries `active_memory_entries` by `agent_instance_id` (6.14–6.16)
10. `select_framework` checks for frameworks; none → informational message; exists → embed + RPC + multi-trigger boost + 0.55 gate (6.17–6.21)
11. `search_knowledge_base` checks for KB; none → informational message; exists → embed + `match_chunks` RPC with `scope_column = 'agent_definition_id'`, `scope_value = definition_id`, `match_count = 20` + 0.3 threshold + top 8 (6.22–6.25, S.3)
12. All errors as plain text `"Error: <description>"`; no JSON error objects (6.26–6.28)
13. Prompts include user's own agents + public agents (5.1–5.2)
14. Prompt name = slug, description = agent description, body = generic orchestration template (see spec Step 5) (5.3–5.6)
15. Prompts generated per-request; new agent appears on next request (5.7–5.8)
16. Hono app with per-request McpServer, streamable HTTP transport, fully stateless (7.1–7.4)
17. Public agent invoked by non-owner: instance auto-created, memory isolated (E.18)
18. RPC returns empty results (below threshold) → empty results, distinct from "no resource configured" (E.21)
19. User has no agents → empty list, no prompts (E.6)
20. Verify `match_chunks` RPC filters out chunks where `knowledge_base_documents.deleted_at IS NOT NULL`. If not, either: (a) add a `deleted_at IS NULL` join filter to the RPC, or (b) post-filter results in application code.
21. `API_KEY_ENCRYPTION_KEY` secret set via `supabase secrets set` (8.1)
22. Deploy with `supabase functions deploy kinetic-mcp --no-verify-jwt` (8.2)
23. `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` auto-injected confirmed (8.3)

**Note:** Test Edge Function locally with `supabase functions serve` before deploying.

**Verification:** V.3 (prompts), V.4 (tools), V.5 (rate limiting), V.6 (multi-client)

---

### T3: Slug Migration + Scaffold + RPC Verification

**Scope:** Spec Steps 1, 9 + db-schema-spec update + RPC migration verification
**Depends on:** Nothing (can parallel with T1)
**Estimate:** 1 (half day)

**Done-when:**
1. `supabase/functions/kinetic-mcp/` directory created (1.1)
2. `deno.json` with import map for supabase-js, mcp sdk, hono (1.3)
3. Migration: `ALTER TABLE agent_definitions ADD COLUMN slug text NOT NULL DEFAULT ''` (9.1)
4. Constraint: `UNIQUE (slug)` — globally unique (9.2)
5. Backfill: lowercase, hyphens, strip edges (9.3–9.4)
6. Backfill: global deduplication with `-2`, `-3` suffix (9.5)
7. Backfill: empty/special-char-only names → valid fallback slug (9.6)
8. Backfill: long names truncated to reasonable length (E.22)
9. Agent creation API: check slug uniqueness, return "name taken" if exists (9.7)
10. Application code sets slug on agent creation (9.9)
11. `db-schema-spec.md §8` updated with slug column + `uq_agent_definitions_slug` index (9.8)
12. Verify `match_chunks` RPC exists on target Supabase project. If not, create a migration at `packages/api/supabase/migrations/YYYYMMDD000000_match_chunks_rpc.sql` using the signature from `db-schema-spec.md`.
13. Verify `match_framework_triggers` RPC exists on target Supabase project. If not, create a migration at `packages/api/supabase/migrations/YYYYMMDD000000_match_framework_triggers_rpc.sql` using the signature from `db-schema-spec.md`.

**Verification:** Slug migration applies cleanly, slug resolution works, both RPCs exist and return results

---

## Gaps (from initial audit)

All 9 gaps from the initial audit have been resolved — spec, PRD, and db-schema-spec updated in-place.

| # | Item | Status |
|---|------|--------|
| G.1–G.9 | Globally unique slug + public agent changes | **Resolved** — spec, PRD, db-schema-spec all updated |

---

## Gate 2 — Schema Cross-Reference

Verified every table, column, FK, and RPC referenced in the spec against `db-schema-spec.md` and migration files.

### Tables Verified

| Table | Columns Referenced in Spec | Schema Match? | Notes |
|-------|---------------------------|---------------|-------|
| `mcp_tokens` | `token_hash`, `revoked_at`, `last_used_at`, `user_id` | **Partial** | `token_hash` described as "bcrypt hash" in schema but implementation uses SHA-256. Schema description is wrong — not a functional issue (column is `text` type, stores whatever hash you put in). **Flag for schema doc fix.** |
| `user_api_keys` | `user_id`, `provider`, `key_ciphertext` (bytea), `key_nonce` (bytea) | **Pass** | |
| `agent_definitions` | `id`, `owner_id`, `slug`, `name`, `instructions`, `visibility` | **Pass** | Slug column added this session. |
| `agent_instances` | `id`, `user_id`, `agent_definition_id` | **Pass** | `UNIQUE(user_id, agent_definition_id)` confirmed. |
| `active_memory_entries` | `agent_instance_id`, `user_id` | **Pass** | Polymorphic: `agent_instance_id` (not `agent_definition_id`). Spec correctly uses instance_id. |
| `knowledge_bases` | `agent_definition_id` | **Pass** | Polymorphic: `project_id XOR agent_definition_id`. |
| `frameworks` | `agent_definition_id` | **Pass** | |
| `framework_trigger_embeddings` | `embedding` (vector) | **Pass** | `extensions.vector(3072)` confirmed. |
| `knowledge_base_chunks` | `embedding` (vector) | **Pass** | `extensions.vector(3072)` confirmed. |
| `mcp_rate_limits` | `user_id`, `date`, `request_count`, `daily_cap` | **Pass** | |

### RPCs Verified

| RPC | Spec Reference | Migration Signature | Match? | Notes |
|-----|---------------|---------------------|--------|-------|
| `match_framework_triggers` | `definition_id`, embed query | `(query_embedding extensions.vector(3072), p_agent_id uuid, match_count integer)` | **Pass** | Spec's `definition_id` maps to `p_agent_id`. |
| `match_chunks` | `definition_id`, embed query | `(query_embedding extensions.vector(3072), scope_column text, scope_value text, match_count integer)` | **Spec gap** | Spec doesn't mention `scope_column` / `scope_value` params. Implementer must know to pass `'agent_definition_id'` as `scope_column` and the UUID as `scope_value`. **Add to T2 done-when.** |
| `mcp_check_and_increment_rate_limit` | `p_user_id`, `p_date` | `(p_user_id uuid, p_date date) RETURNS TABLE(allowed boolean, request_count int, daily_cap int)` | **Pass** | Returns `allowed` boolean — spec says "fail-open on error" which is correct. **Note: RPC not documented in db-schema-spec.md RPC section.** Flag for schema doc fix. |

### Schema Issues Found

| # | Issue | Severity | Action |
|---|-------|----------|--------|
| S.1 | `mcp_tokens.token_hash` described as "bcrypt hash" in db-schema-spec.md — actual implementation is SHA-256 | Low | Fix description in schema doc (not blocking) |
| S.2 | `mcp_check_and_increment_rate_limit` RPC not in db-schema-spec.md RPC Functions section | Low | Add to schema doc (not blocking) |
| S.3 | `match_chunks` RPC uses `scope_column` / `scope_value` dynamic params — not mentioned in spec's `search_knowledge_base` tool definition | Medium | **Add to T2 done-when:** pass `'agent_definition_id'` as `scope_column`, definition UUID as `scope_value` |

**Gate 2 verdict: PASS with 1 medium issue (S.3 → added to T2)**

---

## Gate 3 — ACL Annotation Per Endpoint

Every MCP tool and the auth layer, annotated with access control.

| Surface | Who Can Call | Ownership Check | Error Response |
|---------|-------------|-----------------|----------------|
| MCP endpoint (POST/GET) | Any holder of a valid, non-revoked `mcp_tokens` entry | Token hash → `user_id` lookup | MCP auth error (no user_id resolved) |
| `resolve_agent` (internal helper) | N/A (called by tools) | Slug → global lookup → verify `owner_id = user_id` OR `visibility = 'public'` | `"Error: Agent '<slug>' not found for this user"` — always "not found", never "forbidden" (prevents slug enumeration) |
| `list_kinetic_agents` | Authenticated user | Returns filtered set: own agents (`user_id` match) + public agents (`visibility = 'public'`) | N/A (filtered, not errored) |
| `get_agent_persona` | Authenticated user | Via `resolve_agent` | `"Error: Agent not found"` |
| `get_active_memory` | Authenticated user | Via `resolve_agent` → instance scoped to `user_id` | `"Error: Agent not found"` |
| `select_framework` | Authenticated user | Via `resolve_agent` → frameworks scoped to `definition_id` | `"Error: Agent not found"` |
| `search_knowledge_base` | Authenticated user | Via `resolve_agent` → KB scoped to `definition_id` | `"Error: Agent not found"` |
| `agent_instance` auto-creation | Authenticated user invoking public agent | `user_id` from auth; `definition_id` from resolved public agent | N/A (transparent to user) |

**Key ACL rules:**
1. **Service role key bypasses RLS.** Every query MUST include `user_id` or `owner_id` filter in application code. `resolve_agent` centralizes this.
2. **Private agents from other users → "not found"**, not "forbidden". No information leakage about slug existence.
3. **Public agents → readable by anyone**, but `agent_instance` + `active_memory_entries` are scoped to the invoking user. User A's memory for a public agent is invisible to User B.

**Gate 3 verdict: PASS**

---

## Gate 7 — Known Gotchas Mapping

Mapped Dinesh's gotchas from `agents/dinesh.md` § Known Gotchas against this feature's scope.

| Gotcha | Applies? | Ticket | Note to Add |
|--------|----------|--------|-------------|
| `bytea` columns return bytes — use `.hex()` / `bytes.fromhex()` at boundary | **Yes** | T1 | `user_api_keys.key_ciphertext` and `key_nonce` are bytea. Deno equivalent: `byteaToUint8Array` handles `\x`-prefixed hex. Already in done-when (3.8–3.9). **Add gotcha callout on ticket.** |
| Supabase TypeScript generation lags behind migrations | **Yes** | T3 | New `slug` column won't be in Supabase-generated types immediately. **Add note: cast or extend types manually until codegen catches up.** |
| `run_in_executor` calls must be awaited — not fire-and-forget | **Analogous** | T1 | Deno equivalent: `last_used_at` update is fire-and-forget. In Edge Functions, dangling promises may not complete. **Add note: use `EdgeRuntime.waitUntil()` or similar pattern for fire-and-forget DB writes.** |
| Soft-delete: always filter `deleted_at IS NULL` | **Partial** | T2 | `knowledge_base_documents` uses soft-delete. `match_chunks` RPC filters by chunk table which JOINs to documents — **verify RPC excludes chunks from soft-deleted documents.** Add as a verification item on T2. |
| Ownership checks add extra DB calls — mock them in tests | **Yes** | T2 | `resolve_agent` adds 1-2 DB calls before every tool. **Add note: tests must account for resolve_agent calls in mock setup.** |
| Always validate against canonical schema in `db-schema-spec.md`, not memory | **Yes** | All | Gate 2 satisfies this. |

**Gotchas NOT applicable:** Next.js params Promise, Vitest pool issues, pytest class name shadowing, Pydantic settings, FastAPI BackgroundTasks, SVG viewBox, AsyncMock defaults — all Python/Next.js specific, not relevant to Deno Edge Function.

**Gate 7 verdict: PASS — 5 gotchas flagged for ticket notes**

---

## Gate 8 — Dependency Mapping

### Dependency Graph

```
T1 (Auth + Crypto + Embedding)  ──┐
                                   ├──→  T2 (Tools + Prompts + Entry Point)
T3 (Slug Migration + Deployment) ─┘
```

### Parallelism

| Ticket | Can Start | Blocked By | Rationale |
|--------|-----------|------------|-----------|
| T1 | Immediately | Nothing | Foundation — auth, crypto, embedding are self-contained |
| T3 | Immediately | Nothing | Migration + scaffold — no shared state with T1 |
| T2 | After T1 AND T3 | T1, T3 | Tools need auth module (T1) and slug column (T3) to function |

- **T1 and T3 run in parallel** — different files, no shared state
- **T2 depends on both** — tools import `auth.ts` (T1) and query `slug` column (T3)
- **Chain depth: 2 levels** — under the 3-level flag threshold

### blockedBy Links (for Linear)

- T1: none
- T3: none
- T2: `blockedBy: [T1, T3]`

**Gate 8 verdict: PASS**

---

## All Gates Summary

| Gate | Name | Verdict |
|------|------|---------|
| 1 | Section-by-section coverage audit | **PASS** — 83 behaviors mapped |
| 2 | Schema cross-reference | **PASS** — 1 medium issue (S.3: `match_chunks` params → added to T2) |
| 3 | ACL annotation | **PASS** — all tools annotated, "not found" convention confirmed |
| 4 | Cross-reference spike artifacts | **PASS** — 8 crypto spike items on T1 |
| 5 | Edge case inventory | **PASS** — 22 edge cases mapped |
| 6 | Verification → acceptance criteria | **PASS** — 6 verification steps mapped |
| 7 | Known gotchas mapping | **PASS** — 5 gotchas flagged on tickets |
| 8 | Dependency mapping | **PASS** — T1∥T3 → T2, blockedBy links defined |

**All 8 gates pass. Ready for ticket creation.**

### Items to add to tickets (from Gates 2, 3, 7):

**T1 additions:**
- Gotcha note: `bytea` handling for `user_api_keys` columns
- Gotcha note: fire-and-forget `last_used_at` update — use `waitUntil()` or equivalent, not dangling promise

**T2 additions:**
- Done-when: `search_knowledge_base` passes `'agent_definition_id'` as `scope_column` and definition UUID as `scope_value` to `match_chunks` RPC (S.3)
- Gotcha note: verify `match_chunks` RPC excludes chunks from soft-deleted documents
- Gotcha note: tests must account for `resolve_agent` DB calls in mock setup
- ACL note: private agents from other users → "not found" (never "forbidden")

**T3 additions:**
- Gotcha note: Supabase TypeScript types won't include `slug` immediately — cast or extend manually

### Non-blocking schema doc fixes (separate from this feature):
- S.1: Fix `mcp_tokens.token_hash` description from "bcrypt" to "SHA-256" in db-schema-spec.md
- S.2: Add `mcp_check_and_increment_rate_limit` RPC to db-schema-spec.md RPC Functions section
