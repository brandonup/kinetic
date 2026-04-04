# Plan: Kinetic Remote MCP Server (Supabase Edge Function)

**Status:** Approved — Rev 3
**Author:** Jared
**Date:** 2026-03-29
**Rev 2:** 2026-03-29 — Tenant isolation (`resolve_agent` helper), crypto/vector schema notes, slug migration fix, auth/rate-limit clarifications, error format convention, stateless session model.
**Rev 3:** 2026-03-29 — Gilfoyle review fixes: Bearer auth (not custom scheme), generic prompt template, `match_chunks` RPC params, HKDF salt correction.

## Context

Kinetic's MCP server currently runs locally via stdio, is hardcoded to one agent (Nate), and requires manual Cowork skill setup. Users need to interact with Kinetic agents via MCP from any client (Cowork, ChatGPT, Claude Code) with zero client-side configuration per agent.

**Goal:** Deploy a remote MCP server as a Supabase Edge Function that exposes all of a user's agents as auto-discovered slash commands via MCP prompts.

## Decisions

| Decision | Choice |
|----------|--------|
| Connection model | Per-platform URL (one URL, all agents) |
| Deployment | Supabase Edge Function (TypeScript/Deno) |
| Agent identification | Friendly name (e.g., "nate"), resolved to UUID server-side |
| Agent discovery | MCP prompts — agents auto-appear as `/nate`, `/maya`, etc. |
| Auth | Existing MCP token system (mcp_tokens table, SHA-256 hashed) |

## Architecture

```
User types /nate in Cowork
    |
    v
Claude Desktop sees MCP prompt "nate" -> loads prompt from Kinetic MCP server
    |
    v
Kinetic MCP Edge Function (Supabase)
    |-- Auth: validate token from Bearer header (preferred) or ?key= param -> resolve user_id
    |-- Prompts: list user's agents, return persona + tool instructions per agent
    |-- Tools: get_agent_persona, get_active_memory, select_framework, search_knowledge_base, list_kinetic_agents
    |
    v
Supabase DB (same project)
```

## Implementation Steps

### Step 1: Create Edge Function scaffold

**New directory:** `supabase/functions/kinetic-mcp/`

| File | Purpose |
|------|---------|
| `index.ts` | Hono app + MCP server + route handler |
| `deno.json` | Import map (supabase-js, mcp sdk, hono) |
| `auth.ts` | Token validation (SHA-256 hash -> mcp_tokens lookup) + rate limiting |
| `crypto.ts` | BYOK key decryption (HKDF-SHA256 + AES-256-GCM port from Python) |
| `embedding.ts` | OpenAI embedding helper using user's BYOK key |
| `tools.ts` | 5 tool implementations |
| `prompts.ts` | Dynamic MCP prompt registration per user's agents |

### Step 2: Auth middleware (`auth.ts`)

Port from existing Python auth at `projects/kinetic/packages/api/app/api/routes/mcp.py`:
- Extract token from `Authorization: Bearer mcp_<token>` header (preferred) or `?key=` query param. Header takes precedence if both present. Note: tokens in URLs may appear in server access logs — recommend header-based auth when the client supports it.
- Strip `mcp_` prefix, SHA-256 hash via `crypto.subtle.digest`
- Look up in `mcp_tokens` table where `revoked_at IS NULL`
- Return `user_id`; fire-and-forget update to `last_used_at`
- Call `mcp_check_and_increment_rate_limit` RPC with `p_date` set to current date (`new Date().toISOString().split('T')[0]`); fail-open on error

### Step 3: BYOK crypto (`crypto.ts`)

Port from `projects/kinetic/packages/api/app/services/encryption.py`:
- Master key from `API_KEY_ENCRYPTION_KEY` secret (base64-encoded 32 bytes)
- HKDF-SHA256: salt = 32 zero bytes (`new Uint8Array(32)`), info = user_id UTF-8, output = 32 bytes. **Not an empty buffer** — Python's `HKDF(salt=None)` uses a zero-filled salt of hash length per RFC 5869 §2.2. See `docs/spike-crypto-port-deno.md` for details.
- AES-256-GCM: 12-byte nonce, no AAD
- Handle Supabase bytea format (`\x`-prefixed hex -> binary)
- Deno Web Crypto API equivalents for all operations

> **Note (from local MCP build):** The `match_chunks` and `match_framework_triggers` RPCs use `extensions.vector(3072)`, not `public.vector`. Verify that JSON arrays returned from the OpenAI embeddings API and passed via `supabase.rpc()` cast correctly to `extensions.vector` in Deno — this was a real bug during the local MCP build that required explicit schema qualification.

### Step 4: Embedding helper (`embedding.ts`)

- Decrypt user's OpenAI key from `user_api_keys` table using crypto module
- Call `https://api.openai.com/v1/embeddings` with model `text-embedding-3-large` (3072 dims)
- Return embedding array as `number[]` — note that `match_chunks` and `match_framework_triggers` RPCs expect `extensions.vector(3072)`, not `public.vector` (see Step 3 note)
- If user has no OpenAI key: return clear error from embedding-dependent tools

### Step 5: MCP prompts (`prompts.ts`)

Register dynamic prompts so agents are discoverable in MCP clients:
- Query the authenticated user's own agents (`agent_instances` JOIN `agent_definitions` WHERE `user_id = user_id`) plus all public agents (`agent_definitions` WHERE `visibility = 'public'`)
- For each agent, register a prompt with:
  - **Name:** agent slug/name (e.g., "nate")
  - **Description:** agent's description or first line of instructions
  - **Body:** Generic orchestration template (below). Reference the `/nate` skill pattern for the proven approach, but use this agent-agnostic version:
- Prompts are generated per-request based on the authenticated user's agents

**Prompt body template:**

```
Assemble context for {agent_name} by calling these tools in parallel:

Group 1 (no arguments needed):
- Call get_agent_persona with agent: "{slug}" — returns the agent's system prompt
- Call get_active_memory with agent: "{slug}" — returns recent memory entries

Group 2 (pass the user's message as query):
- Call select_framework with agent: "{slug}", query: "<user message>" — returns a matching reasoning framework
- Call search_knowledge_base with agent: "{slug}", query: "<user message>" — returns relevant knowledge base content

Wait for all 4 tools to return, then:
1. Adopt the persona from get_agent_persona completely — reason and respond as this agent.
2. Use active memory as conversation context. Reference prior interactions naturally.
3. If a framework matched, use it as your internal reasoning lens. Do not name or present it to the user.
4. If KB content matched, draw on it to ground your reasoning. Cite source documents naturally.
5. If any layer returned empty, proceed without it — do not mention missing layers.
```

### Step 6: Tools (`tools.ts`)

Port 4 existing tools + add 1 new tool.

#### Agent Resolution — `resolve_agent(user_id, slug)`

All tools that accept an `agent` parameter must use a shared `resolve_agent(user_id: string, slug: string)` helper. This helper enforces access control — only the user's own agents and public agents are resolvable.

**Resolution chain:**
1. Query `agent_definitions` WHERE `slug = slug` → get `definition_id`, `owner_id`, `name`, `instructions`, `visibility` (slug is globally unique — one result max)
2. If no match: return `"Error: Agent '<slug>' not found for this user"`
3. If `owner_id != user_id` AND `visibility != 'public'`: return `"Error: Agent '<slug>' not found for this user"` (private agent belonging to another user)
4. Query `agent_instances` WHERE `agent_definition_id = definition_id` AND `user_id = user_id` → get `instance_id`
5. If no instance exists: auto-create one (matching web app behavior on first invocation) — `INSERT INTO agent_instances (user_id, agent_definition_id)` → return the new `instance_id`
6. Return `{ definition_id, instance_id, name, instructions }`

**Access control:** Owned agents (any visibility) and public agents from other users are resolvable. Private agents from other users are not. `agent_instances` are always scoped to the invoking `user_id` — a non-owner invoking a public agent gets their own isolated instance (and therefore isolated active memory).

#### Tool Definitions

| Tool | Params | Logic |
|------|--------|-------|
| `list_kinetic_agents` | none | Query user's own agents (`agent_instances` JOIN `agent_definitions` WHERE `user_id`) plus all public agents (`agent_definitions` WHERE `visibility = 'public'`). Return name + slug + description + ownership indicator (`own` or `public`). |
| `get_agent_persona` | `agent` (string) | `resolve_agent(user_id, agent)` → return `instructions` from the resolved definition |
| `get_active_memory` | `agent` (string) | `resolve_agent(user_id, agent)` → use `instance_id` to query `active_memory_entries` WHERE `agent_instance_id = instance_id` AND `user_id = user_id`. Note: `active_memory_entries` uses `agent_instance_id`, not `agent_definition_id`. |
| `select_framework` | `agent` (string), `query` (string) | `resolve_agent(user_id, agent)` → check if agent has any `frameworks` rows for `definition_id`. If none: return `"No framework library configured for this agent. Proceeding without framework guidance."` (not an error — omit from context). If frameworks exist: embed query → call `match_framework_triggers` RPC scoped to `definition_id`, multi-trigger boost, confidence gate (0.55) |
| `search_knowledge_base` | `agent` (string), `query` (string) | `resolve_agent(user_id, agent)` → check if agent has a KB (`knowledge_bases` WHERE `agent_definition_id = definition_id`). If none: return `"No knowledge base configured for this agent. Proceeding without KB context."` (not an error — omit from context). If KB exists: embed query → call `match_chunks` RPC with `scope_column = 'agent_definition_id'`, `scope_value = definition_id`, `match_count = 20`, filter threshold (0.3), top 8 |

#### Graceful resolution for optional resources

KBs and framework libraries are both optional per agent. When either is missing, the tool must return a short informational message (not an error) so the calling LLM cleanly omits that layer from its context window rather than treating it as a failure. This applies to both the MCP server and the in-app generation engine (layers L7/L8/L9) — the behavior should be consistent across both surfaces.

#### Error Response Convention

All tools return errors as plain text content strings: `"Error: <description>"`. No JSON error objects, no HTTP status codes in the MCP response. This matches the convention established in the local MCP server. Errors are for actual failures (auth, missing agent, missing BYOK key), not for optional resources that haven't been configured. Examples:
- `"Error: Agent 'nate' not found for this user"`
- `"Error: No OpenAI API key configured — add one in Kinetic settings to use this tool"`

### Step 7: Main entry point (`index.ts`)

- Create Hono app
- On each request: authenticate -> create per-request McpServer instance -> register tools + prompts for that user -> handle MCP transport
- Use streamable HTTP transport (POST for requests, GET for server events)
- The server is fully stateless — a new McpServer instance is created per HTTP request. No server-initiated notifications or subscriptions are supported.

### Step 8: Secrets & deployment

```bash
# Set secrets (from Kinetic's existing API_KEY_ENCRYPTION_KEY)
supabase secrets set API_KEY_ENCRYPTION_KEY=<base64-encoded-32-byte-key>

# Deploy (--no-verify-jwt because we use custom token auth)
supabase functions deploy kinetic-mcp --no-verify-jwt
```

`SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are auto-injected by Supabase.

### Step 9: Agent name resolution

Add `slug` column to `agent_definitions` table for reliable matching:

- Migration: `ALTER TABLE agent_definitions ADD COLUMN slug text NOT NULL DEFAULT ''`
- Constraint: `UNIQUE (slug)` — globally unique. One slug, one agent, platform-wide.
- Max length: 60 characters (truncate before uniqueness check)
- Backfill logic:
  1. Lowercase the `name`
  2. Replace spaces and special characters with hyphens, strip leading/trailing hyphens
  3. Truncate to 60 characters
  4. If result is empty (name was all special characters): assign fallback slug `agent-<first-8-chars-of-id>`
  5. Deduplicate collisions globally by appending `-2`, `-3`, etc.
  6. Example: User A and User B both have "Nate Jones" → `nate-jones`, `nate-jones-2`
- Agent creation API: before INSERT, check if slug exists. If taken, return 400 with `"This agent name is already taken."` No auto-suffixing — user picks a new name.
- Tool resolution: `resolve_agent` queries `agent_definitions.slug` globally (no owner filter on slug lookup — ownership/visibility checked after) — no fallback to `name` (slug is the canonical identifier)
- **Schema dependency:** Update `docs/db-schema-spec.md §8` with slug column + `uq_agent_definitions_slug` UNIQUE index.

### Step 10: User setup instructions

User flow:
1. Log into Kinetic -> Profile -> MCP Tokens -> Generate token
2. Copy connection URL: `https://<PROJECT_REF>.supabase.co/functions/v1/kinetic-mcp?key=mcp_<token>`
3. In Claude Desktop: Settings -> Connectors -> Add custom connector -> paste URL
4. Type `/nate` (or any agent name) -> it just works

## Critical files to reference

| File | What to port/reference |
|------|----------------------|
| `packages/mcp/server.py` | All 5 tool implementations, constants, business logic |
| `projects/kinetic/packages/api/app/api/routes/mcp.py` | Token auth + rate limiting logic |
| `projects/kinetic/packages/api/app/services/encryption.py` | HKDF + AES-GCM encryption to port |
| `projects/kinetic/packages/api/app/services/user_keys.py` | BYOK key fetch + bytea handling |
| `projects/kinetic/packages/api/migrations/000_complete_schema.sql` | Schema for all tables + RPCs |

## Verification

1. **Crypto cross-check:** Encrypt a test value with Python, decrypt with TypeScript — must match
2. **Auth:** Create MCP token via existing API, verify Edge Function accepts it and rejects invalid/revoked tokens
3. **Prompts:** Connect from Claude Desktop, verify agent names appear as slash commands
4. **Tools:** Test each tool with a known agent — persona returns, memory returns, framework selection works, KB search works
5. **Rate limiting:** Verify rate limit RPC is called and enforced
6. **Multi-client:** Test URL in Claude Desktop (Connectors) and Claude Code (`claude mcp add --transport http`)

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| HKDF implementation mismatch (Python cryptography vs Deno Web Crypto) | BYOK key decryption fails, embedding tools broken | Cross-language test vectors; verify Python HKDF(salt=None) = Deno empty salt |
| Edge Function cold start latency (2-3s) | First request slow | Acceptable for MCP tool calls; Supabase keeps functions warm ~5 min |
| Per-request McpServer creation overhead | Performance concern | McpServer is lightweight; Edge Functions are stateless by design |
| `user_api_keys` bytea column format | Decryption fails | Port `to_bytes()` helper exactly — handle `\x`-prefixed hex and plain hex |
| MCP prompt registration is per-request (dynamic) | Latency on prompt list | Cache agent list for duration of MCP session |

## Out of scope (follow-on work)

- MCP conversation logging (Feature 3 — separate spec)
- Conversation storage + active memory from MCP sessions
- Admin observability for MCP-sourced conversations
- UI "Copy MCP URL" button on profile page
