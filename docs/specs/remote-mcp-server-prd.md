# Remote MCP Server — PRD Wrapper

**Status:** Approved
**Author:** Jared
**Date:** 2026-03-29
**Project:** Kinetic
**Spec ref:** `docs/specs/remote-mcp-server-spec.md` (Approved)
**ADR ref:** `docs/adr-008-remote-mcp-edge-function.md` (Proposed)
**Crypto spike:** `docs/spike-crypto-port-deno.md` (Complete)

---

## Problem Statement

Kinetic's MCP server runs locally, is hardcoded to one agent, and requires manual per-agent configuration. Users can't connect from remote MCP clients (Claude Desktop connectors, Claude Code, ChatGPT) without local setup. This blocks the core value prop: any client, one URL, all agents auto-discovered.

## Proposed Solution

Deploy a remote MCP server as a Supabase Edge Function. One URL per user. All agents appear as MCP prompts (slash commands). Reuses existing token auth, BYOK keys, and the proven tool set from the local server.

## User Stories

### US-1: Connect MCP client to Kinetic

As a Kinetic user, I want to paste a single URL into my MCP client so that I can access all my Kinetic agents without local setup.

**Acceptance Criteria:**
- [ ] User generates an MCP token in Kinetic (existing flow)
- [ ] Connection URL format: `https://<PROJECT_REF>.supabase.co/functions/v1/kinetic-mcp` with token via `Authorization: Bearer mcp_<token>` header or `?key=` query param
- [ ] Claude Desktop (Connectors) connects and receives tool + prompt list
- [ ] Claude Code (`claude mcp add --transport http`) connects and receives tool + prompt list
- [ ] Invalid/revoked tokens return auth error
- [ ] Rate limiting enforced via `mcp_check_and_increment_rate_limit` RPC

### US-2: Discover agents as slash commands

As a Kinetic user, I want my agents to be discoverable in my MCP client (e.g., as slash commands, a prompt list, or however the client surfaces MCP prompts) so that I can invoke any agent easily without configuration.

**Acceptance Criteria:**
- [ ] MCP prompts are dynamically registered per-request: user's own agents + all public agents from other users
- [ ] Prompt name = agent slug (e.g., "nate", "maya")
- [ ] Prompt description = agent's description or first line of instructions
- [ ] Prompt body contains orchestration instructions (call all 4 tools, adopt persona, use frameworks/KB as internal reasoning)
- [ ] When user creates a new agent in Kinetic, it appears in MCP client on next request (no reconfiguration)
- [ ] Private agents from other users are not visible — only own agents and public agents

### US-3: Get agent persona

As a Kinetic user invoking an agent via MCP, I want the agent's persona (system prompt) loaded so that the LLM adopts the agent's identity.

**Acceptance Criteria:**
- [ ] `get_agent_persona` tool accepts `agent` (slug string)
- [ ] Resolves via `resolve_agent(user_id, slug)` — scoped to authenticated user
- [ ] Returns `instructions` from `agent_definitions`
- [ ] If agent not found for this user: returns `"Error: Agent '<slug>' not found for this user"`
- [ ] Agent with empty/null instructions: returns empty string (not an error)

### US-4: Get active memory

As a Kinetic user invoking an agent via MCP, I want the agent's active memory loaded so that the LLM has persistent context about me.

**Acceptance Criteria:**
- [ ] `get_active_memory` tool accepts `agent` (slug string)
- [ ] Resolves via `resolve_agent(user_id, slug)` — uses `instance_id`, not `definition_id`
- [ ] Queries `active_memory_entries` WHERE `agent_instance_id = instance_id` AND `user_id = user_id`
- [ ] If no `agent_instance` exists: auto-creates one (matching web app first-invocation behavior)
- [ ] If instance exists but has no memory entries: returns empty list (not an error)
- [ ] If agent not found: returns error per convention

### US-5: Select framework

As a Kinetic user invoking an agent via MCP, I want relevant frameworks selected based on my query so that the LLM applies structured thinking.

**Acceptance Criteria:**
- [ ] `select_framework` tool accepts `agent` (slug string) and `query` (string)
- [ ] Resolves via `resolve_agent(user_id, slug)`
- [ ] If agent has no frameworks: returns `"No framework library configured for this agent. Proceeding without framework guidance."` (informational, not error)
- [ ] If agent has frameworks: embeds query via user's BYOK OpenAI key, calls `match_framework_triggers` RPC scoped to `definition_id`
- [ ] Multi-trigger boost applied, confidence gate at 0.55
- [ ] If user has no OpenAI key: returns `"Error: No OpenAI API key configured — add one in Kinetic settings to use this tool"`
- [ ] Vector type is `extensions.vector(3072)`, not `public.vector`

### US-6: Search knowledge base

As a Kinetic user invoking an agent via MCP, I want relevant KB documents retrieved so that the LLM answers from my data.

**Acceptance Criteria:**
- [ ] `search_knowledge_base` tool accepts `agent` (slug string) and `query` (string)
- [ ] Resolves via `resolve_agent(user_id, slug)`
- [ ] If agent has no KB: returns `"No knowledge base configured for this agent. Proceeding without KB context."` (informational, not error)
- [ ] If agent has KB: embeds query via user's BYOK OpenAI key, calls `match_chunks` RPC scoped to agent's KB
- [ ] Filter threshold 0.3, top 8 results
- [ ] If user has no OpenAI key: returns error per convention
- [ ] Vector type is `extensions.vector(3072)`, not `public.vector`

### US-7: List agents

As a Kinetic user, I want to see all my available agents so that I know which ones I can invoke.

**Acceptance Criteria:**
- [ ] `list_kinetic_agents` tool takes no parameters
- [ ] Queries user's own agents (`agent_instances` JOIN `agent_definitions`) plus all public agents (`agent_definitions` WHERE `visibility = 'public'`)
- [ ] Returns name, slug, description, and ownership indicator (`own` or `public`) for each agent
- [ ] If user has no agents and no public agents exist: returns empty list (not an error)

### US-8: BYOK crypto port

As a system, the Edge Function must decrypt BYOK API keys encrypted by the Python backend so that embedding-dependent tools work.

**Acceptance Criteria:**
- [ ] HKDF-SHA256 key derivation: salt = 32 zero bytes (`new Uint8Array(32)`), info = user_id UTF-8, output = 32 bytes — matches Python `HKDF(salt=None)` per RFC 5869 §2.2
- [ ] AES-256-GCM decryption: 12-byte nonce, no AAD
- [ ] Supabase `bytea` format (`\x`-prefixed hex) parsed correctly
- [ ] Cross-language test vectors pass: encrypt with Python, decrypt with Deno, output matches
- [ ] Master key loaded from `API_KEY_ENCRYPTION_KEY` secret (base64-encoded 32 bytes)
- [ ] If test vectors fail: fall back to proxying decryption through FastAPI backend (see crypto spike fallback strategy)

### US-9: Agent slug migration

As a system, agent definitions need a `slug` column for reliable MCP name resolution.

**Acceptance Criteria:**
- [ ] Migration adds `slug text NOT NULL DEFAULT ''` to `agent_definitions`
- [ ] Constraint: `UNIQUE (slug)` — globally unique, one slug per agent platform-wide
- [ ] Max length: 60 characters (truncate before uniqueness check)
- [ ] Backfill: lowercase name, replace spaces/special chars with hyphens, strip leading/trailing hyphens, truncate to 60 chars
- [ ] Backfill: empty/special-char-only names get fallback slug `agent-<first-8-chars-of-id>`
- [ ] Backfill deduplication: collisions globally get `-2`, `-3` suffix
- [ ] Agent creation API: check slug uniqueness before INSERT, return 400 "This agent name is already taken" if exists
- [ ] `db-schema-spec.md` updated with slug column and `uq_agent_definitions_slug` index
- [ ] Application code sets slug on agent creation (lowercase, hyphenated, 60 char max)

---

## Surface Inventory

Every artifact this feature requires. "None" means explicitly no items in that category.

### Pages / Views

None. No new UI pages. (The "Copy MCP URL" button is out of scope — see spec.)

### API Endpoints (Edge Function routes)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/functions/v1/kinetic-mcp` | MCP request handler (tool calls, prompt list) |
| GET | `/functions/v1/kinetic-mcp` | MCP server events (streamable HTTP transport) |

### Edge Function Modules

| File | Purpose | User Story |
|------|---------|------------|
| `index.ts` | Hono app + per-request McpServer + route handler | US-1, US-2 |
| `auth.ts` | Token validation (SHA-256) + rate limiting | US-1 |
| `crypto.ts` | HKDF-SHA256 + AES-256-GCM decryption (Deno Web Crypto) | US-8 |
| `embedding.ts` | OpenAI embedding helper using decrypted BYOK key | US-5, US-6 |
| `tools.ts` | 5 tool implementations + `resolve_agent` helper | US-3, US-4, US-5, US-6, US-7 |
| `prompts.ts` | Dynamic MCP prompt registration per user's agents | US-2 |
| `deno.json` | Import map (supabase-js, mcp sdk, hono) | US-1 |

### Database Changes

| Change | Table | User Story |
|--------|-------|------------|
| Add `slug` column | `agent_definitions` | US-9 |
| Add `UNIQUE (slug)` constraint (globally unique) | `agent_definitions` | US-9 |
| Backfill migration | `agent_definitions` | US-9 |

### Background Jobs / Cron

None.

### Integrations

| Service | Purpose | User Story |
|---------|---------|------------|
| OpenAI Embeddings API (`text-embedding-3-large`) | Embed queries for framework selection + KB search | US-5, US-6 |

### Secrets / Config

| Secret | Source | User Story |
|--------|--------|------------|
| `API_KEY_ENCRYPTION_KEY` | Existing — copy to Edge Function secrets | US-8 |
| `SUPABASE_URL` | Auto-injected by Supabase | All |
| `SUPABASE_SERVICE_ROLE_KEY` | Auto-injected by Supabase | All |

### Cross-check

- Every user story maps to at least one module in the Edge Function file list: **pass**
- Every module maps to at least one user story: **pass**
- Every database change maps to a user story: **pass**
- Verification steps (spec §Verification) mapped to user stories: crypto cross-check → US-8, auth → US-1, prompts → US-2, tools → US-3/4/5/6/7, rate limiting → US-1, multi-client → US-1

---

## Data Requirements

### Modified tables

- **`agent_definitions`** — Add `slug text NOT NULL DEFAULT ''` column, `UNIQUE (slug)` constraint (globally unique), `uq_agent_definitions_slug` index. Update `db-schema-spec.md §8`.

### New tables

None.

### Access patterns

- `resolve_agent`: reads `agent_definitions` by `slug` (globally unique), checks ownership or public visibility, then `agent_instances` by `(agent_definition_id, user_id)`. Uses service role key — access control enforced in application code.
- `list_kinetic_agents`: reads user's own agents (`agent_instances` JOIN `agent_definitions`) plus public agents (`agent_definitions` WHERE `visibility = 'public'`).
- `get_active_memory`: reads `active_memory_entries` by `(agent_instance_id, user_id)`.
- `select_framework`: reads `frameworks` + calls `match_framework_triggers` RPC by `agent_definition_id`.
- `search_knowledge_base`: reads `knowledge_bases` by `agent_definition_id`, calls `match_chunks` RPC.
- All queries bypass RLS (service role key). **Tenant isolation enforced in application code via `resolve_agent` helper.**

---

## Edge Cases

| Case | Expected Behavior | User Story |
|------|-------------------|------------|
| Agent has no KB | `search_knowledge_base` returns informational message, not error. LLM omits KB layer from context. | US-6 |
| Agent has no framework library | `select_framework` returns informational message, not error. LLM omits framework layer from context. | US-5 |
| Agent has no instructions (empty system prompt) | `get_agent_persona` returns empty string. LLM operates without persona. | US-3 |
| Agent instance doesn't exist yet (never invoked in web app) | `resolve_agent` auto-creates instance on first MCP call | US-4 |
| User has no BYOK OpenAI key | Embedding-dependent tools (US-5, US-6) return clear error. Non-embedding tools (US-3, US-4, US-7) work normally. | US-5, US-6 |
| User has no agents | `list_kinetic_agents` returns empty list. Prompts list is empty (no slash commands). | US-7, US-2 |
| Agent instance exists but has no memory entries | `get_active_memory` returns empty list | US-4 |
| Two users try to create agent with same slug | Second user gets "This agent name is already taken" — `UNIQUE(slug)` enforced globally | US-9 |
| Agent name with only special chars (e.g., "!!!") | Backfill assigns fallback slug `agent-<first-8-chars-of-id>` | US-9 |
| Very long agent name | Slug truncated to 60 characters before uniqueness check | US-9 |
| Public agent invoked by non-owner | `resolve_agent` resolves it; auto-creates `agent_instance` for invoking user; memory isolated per instance | US-4 |
| Private agent from another user | `resolve_agent` returns "not found" error — private agents not visible to non-owners | US-3 |
| `list_kinetic_agents` with public agents | Returns both own + public agents, with ownership indicator (`own` or `public`) | US-7 |
| BYOK key decryption succeeds but OpenAI rejects key | Return `"Error: OpenAI API error — <message>"` | US-5, US-6 |
| `match_chunks` / `match_framework_triggers` returns empty (below threshold) | Return empty results; distinct from "no resource configured" informational message | US-5, US-6 |
| Token in URL query param | Works but logged in server access logs. Header auth recommended. | US-1 |
| Both header and query param token provided | Header takes precedence | US-1 |
| Revoked token | Auth fails, returns error | US-1 |
| Rate limit exceeded | `mcp_check_and_increment_rate_limit` RPC enforced. Fail-open on RPC error (rate limit service down shouldn't block MCP). | US-1 |
| HKDF salt mismatch (Deno vs Python) | Test vectors catch this pre-integration. Fallback: proxy decryption through FastAPI. | US-8 |
| `match_chunks` / `match_framework_triggers` vector schema | Must use `extensions.vector(3072)`, not `public.vector` | US-5, US-6 |
| Edge Function cold start | 2-3s latency on first request after ~5 min idle. Acceptable for MCP tool calls. | US-1 |

---

## Out of Scope

Carried from spec — do not change:

- MCP conversation logging (Feature 3 — separate spec)
- Conversation storage + active memory from MCP sessions
- Admin observability for MCP-sourced conversations
- UI "Copy MCP URL" button on profile page

---

## Dependencies

### Technical
- **Crypto spike** (`docs/spike-crypto-port-deno.md`) — Complete. Provides Deno crypto module and test vector protocol.
- **ADR-008** (`docs/adr-008-remote-mcp-edge-function.md`) — Proposed. Architecture decisions for Edge Function + auth + BYOK.
- **Existing token auth** — MCP token generation already in production (KIN-321).

### Product
- None — all upstream features are shipped.

### External
- **MCP TypeScript SDK** — npm package, used in Edge Function for McpServer + transport.
- **Hono** — npm package, HTTP framework for the Edge Function.
- **OpenAI Embeddings API** — external service, called with user's BYOK key.

---

## Open Questions

None remaining. All questions resolved during spec review:
- ~~Reuse `messages` table or new table for MCP logging?~~ → Out of scope (separate spec)
- ~~`extensions.vector` vs `public.vector`?~~ → Resolved: `extensions.vector(3072)`
- ~~Slug uniqueness scope?~~ → Resolved: `UNIQUE (slug)` — globally unique, platform-wide
- ~~HKDF salt handling?~~ → Resolved: 32 zero bytes per RFC 5869
