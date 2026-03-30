# Kinetic Brain — Cowork Plugin PRD

**Status:** Shipped
**Author:** Jared
**Date:** 2026-03-29
**Project:** Kinetic MVP

---

## Problem Statement

Brandon needs expert AI advisory reasoning (Nate B. Jones) integrated into his daily workflow in Claude Cowork. Today, Nate's intelligence — persona, frameworks, KB, active memory — lives in Kinetic's Supabase backend but is only accessible through the Kinetic web app. There's no way to combine Nate's expert context with the project context Brandon already maintains in Cowork.

This also tests a strategic hypothesis: Kinetic as a **portable context engine** — agent intelligence lives in Kinetic, plugs into any MCP-compatible client. If this works, it validates the "plug your brain into anything" value prop.

## Proposed Solution

A Cowork plugin (`kinetic-brain`) with a `/nate` slash command backed by a Python MCP server. When invoked, the skill orchestrates 4 MCP tool calls to Kinetic's live Supabase, assembles Nate's context layers (persona, active memory, framework, KB chunks), and injects them into the conversation alongside Brandon's existing Cowork project context.

## User Stories

- As Brandon, I want to invoke `/nate` with a question so that Claude reasons with Nate's expert persona, relevant frameworks, and KB — combined with my Cowork project context.
- As Brandon, I want Nate's frameworks to be automatically selected based on my question so that I get the right diagnostic lens without manually choosing.
- As Brandon, I want Nate's KB to be searched for relevant content so that responses are grounded in Nate's published thinking.
- As Brandon, I want the plugin to gracefully handle missing context (no matching framework, empty KB, no active memory) so that it still works with partial data.

## Success Metrics

| Metric | Baseline | Target | Timeframe |
|---|---|---|---|
| `/nate` returns grounded response | N/A (doesn't exist) | Works on first invocation | Day 1 |
| Framework auto-selection accuracy | N/A | Correct framework for 3/5 test queries | Week 1 |
| Response quality (Brandon subjective) | Claude without Nate context | Noticeably sharper, more specific reasoning | Week 1 |
| Portable brain thesis validated | Unproven | Brandon confirms "this is the right model" or identifies what's missing | Week 2 |

## Scope

**In scope:**
- Plugin directory structure (`.claude-plugin/`, skills, mcp-server)
- Python MCP server with 4 tools: `get_agent_persona`, `get_active_memory`, `select_framework`, `search_knowledge_base`
- `/nate` SKILL.md that orchestrates tool calls and context assembly
- Bundled fallback of Nate's system prompt in `references/`
- README with setup instructions
- `.plugin` packaging for Cowork install

**Out of scope:**
- Multi-agent support (only Nate for v0) — extend later if thesis validated
- Active memory writes (read-only for v0) — Cowork conversations don't write back to Kinetic
- MMR reranking in retrieval — marginal benefit at 8 chunks, adds complexity
- Haiku reranker in framework selection — already skipped in production Kinetic
- Authentication UI — env vars only, single-user setup
- Conversation history from Kinetic — Cowork handles its own transcript natively

## Surface Inventory

- **Pages / Views:** None — this is a plugin, not a UI feature. The `/nate` skill surfaces within Cowork's existing chat interface.
- **API Endpoints:** None new. The MCP server calls Supabase directly via client library, not via Kinetic's FastAPI endpoints.
- **Database Tables:** None new or modified. Reads from existing tables:
  - `agent_definitions` (read `instructions` by ID)
  - `active_memory_entries` (read by `agent_instance_id` + `user_id`)
  - `framework_trigger_embeddings` (via `match_framework_triggers` RPC)
  - `frameworks` (read full framework by ID)
  - `knowledge_base_chunks` (via `match_chunks` RPC)
- **Background Jobs / Cron:** None
- **Integrations:**
  - Supabase (via `supabase-py`, service role key)
  - OpenAI Embeddings API (`text-embedding-3-large`, 3072 dims)
  - MCP protocol (stdio, via `mcp` Python SDK)

## Data Requirements

None — this feature requires no new or modified tables. All queries target existing Kinetic tables and RPCs.

**Access patterns:**
- `agent_definitions`: single-row read by UUID (L5)
- `active_memory_entries`: filtered list read by `agent_instance_id` + `user_id`, ordered by recency (L6)
- `match_framework_triggers` RPC: vector similarity search scoped to agent, returns top 20 candidates (L7)
- `frameworks`: single-row read by UUID to fetch matched framework content (L7)
- `match_chunks` RPC: vector similarity search scoped to `agent_definition_id`, returns top 20 candidates (L9)

**Auth model:** Service role key (bypasses RLS). Acceptable for v0 — single user, local machine.

## Component Specifications

### MCP Server (`mcp-server/server.py`)

**Runtime:** Python 3.11+, stdio transport
**Dependencies:** `mcp>=1.0.0`, `supabase>=2.0.0`, `openai>=1.0.0`, `pydantic>=2.0.0`

**Initialization:** FastMCP server (`kinetic_brain_mcp`) with lifespan pattern:
- Create Supabase client from `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`
- Create OpenAI client from `OPENAI_API_KEY`
- Both available to all tools via context

**Shared helper:**
- `embed_query(oai_client, text) -> list[float]` — single call to `text-embedding-3-large`, returns 3072-dim vector

#### Tool: `get_agent_persona`

| Field | Value |
|---|---|
| Input | None (uses `NATE_AGENT_ID` env var) |
| Query | `agent_definitions` table, select `id, name, instructions`, filter by ID |
| Output | Formatted string: agent name + instructions text |
| Error handling | Return "Agent not found" if ID invalid |
| Annotations | `readOnlyHint=True`, `idempotentHint=True` |

**Done-when:**
- Returns Nate's name and full instructions text
- Returns clear error message for invalid agent ID
- Does not crash on network timeout

#### Tool: `get_active_memory`

| Field | Value |
|---|---|
| Input | None (uses `NATE_INSTANCE_ID` + `KINETIC_USER_ID` env vars) |
| Query | `active_memory_entries` table, filter by `agent_instance_id` + `user_id`, order by `created_at` desc |
| Output | Formatted markdown list of memory entries (content + timestamp), or "No active memories" |
| Error handling | Return empty gracefully — no memories is valid state |
| Annotations | `readOnlyHint=True` |

**Done-when:**
- Returns formatted memory entries when they exist
- Returns "No active memories" when empty
- Entries are ordered most-recent-first

#### Tool: `select_framework`

| Field | Value |
|---|---|
| Input | `query: str` (user's question) |
| Pipeline | 1. Embed query → 2. `match_framework_triggers` RPC (top 20) → 3. Group by framework, multi-trigger boost → 4. Threshold gate (>=0.55) → 5. Fetch full framework |
| Output | Assembled framework text, or "No matching framework found" |
| Error handling | Embedding failure → return "Framework selection unavailable". RPC failure → same. |
| Annotations | `readOnlyHint=True` |

**Pipeline details (ported from `framework_selection.py`):**
- RPC params: `query_embedding` (3072 dims), `p_agent_id` (from env), `match_count=20`
- Grouping: collect triggers by `framework_db_id`, base score = max similarity
- Boost: `boosted_score = base + (trigger_count - 1) * 0.05`
- Gate: top candidate `boosted_score >= 0.55` → fetch framework; else → no match
- Framework fetch: `frameworks` table by ID, assemble text from relevant fields

**Done-when:**
- Returns matching framework text for a relevant query (e.g., "How should I price my AI SaaS?")
- Returns "No matching framework found" for an irrelevant query (e.g., "What's the weather?")
- Multi-trigger boost correctly ranks frameworks with multiple trigger matches higher
- Handles embedding API errors without crashing

#### Tool: `search_knowledge_base`

| Field | Value |
|---|---|
| Input | `query: str` (user's question) |
| Pipeline | 1. Embed query → 2. `match_chunks` RPC (top 20) → 3. Filter similarity >= 0.3 → 4. Take top 8 → 5. Format with metadata |
| Output | Formatted KB chunks with source metadata (document title, section path, similarity), or "No relevant knowledge base entries found" |
| Error handling | Embedding failure → return "KB search unavailable". RPC failure → same. |
| Annotations | `readOnlyHint=True` |

**RPC params:** `query_embedding` (3072 dims), `scope_column="agent_definition_id"`, `scope_value` (from `NATE_AGENT_ID` env), `match_count=20`

**Done-when:**
- Returns formatted chunks with document title and section path for relevant queries
- Returns "No relevant knowledge base entries found" for irrelevant queries
- Similarity scores are visible in output (aids debugging)
- Maximum 8 chunks returned
- Handles embedding API errors without crashing

### Skill: `/nate` (`skills/nate/SKILL.md`)

**Trigger:** User types `/nate`, "ask Nate", "talk to Nate", "get Nate's perspective"

**Orchestration sequence:**
1. Call `get_agent_persona` and `get_active_memory` (parallel, no args)
2. Call `select_framework` and `search_knowledge_base` with user's query (parallel)
3. Adopt Nate's persona from the returned instructions
4. Reason with all assembled layers:
   - L5 (persona) → defines reasoning style and voice
   - L6 (active memory) → recent context from prior conversations
   - L7 (framework) → diagnostic approach for this query
   - L9 (KB chunks) → domain knowledge grounding
5. If any layer is empty, gracefully omit — do not mention missing context
6. Cite KB sources when drawing on them; do not name frameworks explicitly (per Nate's prompt: frameworks are internal reasoning, not output)

**Done-when:**
- `/nate How should I price my AI SaaS?` triggers all 4 MCP tools
- Claude responds in Nate's voice (direct, opinionated, concrete)
- Framework is applied as reasoning, not cited as "according to framework X"
- KB content is referenced with source attribution
- Empty layers (e.g., no active memory) are silently omitted
- Works when invoked mid-conversation (preserves Cowork project context)

### Plugin Config

**`plugin.json`:**
- name: `kinetic-brain`
- version: `0.1.0`
- description: "Expert AI advisory reasoning powered by Kinetic's context engine"
- author: Son of Anton

**`.mcp.json`:**
- Server name: `kinetic-brain`
- Command: `python`, args: `["${CLAUDE_PLUGIN_ROOT}/mcp-server/server.py"]`
- Env: 6 variables (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENAI_API_KEY`, `NATE_AGENT_ID`, `NATE_INSTANCE_ID`, `KINETIC_USER_ID`)

**Done-when:**
- `claude plugin validate` passes with no errors
- Plugin installs in Cowork without errors
- MCP server starts and tools are available in the tool list

## Dependencies

- **Technical:**
  - Nate's `agent_definition` row must exist in Supabase with instructions populated
  - Nate's `agent_instance` row must exist (for active memory scoping)
  - `match_framework_triggers` RPC must be deployed (migration `20260328000006`)
  - `match_chunks` RPC must be deployed (or fallback path available)
  - Framework trigger embeddings must exist for Nate's frameworks
  - KB chunks must exist for Nate's agent (documents ingested and chunked)
- **Product:** Nate's system prompt approved (currently "In Review" — KIN-353)
- **External:** OpenAI API access for embeddings

## Decisions Needed

None — all decisions resolved during brainstorming:
- Auth: service role key (v0, local, single user)
- Embedding: env var OpenAI key
- IDs: env vars
- MMR: skip for v0
- Reranker: skip (matches production)

## Open Questions

None — all resolved.

- [x] Nate's `agent_definition` row exists in live Supabase (Brandon confirmed 2026-03-29)
- [x] Nate's `agent_instance` exists for Brandon's user (Brandon confirmed 2026-03-29)
- [x] Framework trigger embeddings generated (Brandon confirmed 2026-03-29)
- [x] KB documents ingested and chunked (Brandon confirmed 2026-03-29)

---

## Implementation Notes (2026-03-29)

Shipped with deviations from the original spec. Documenting what changed and why.

### Plugin system did not work

The spec called for a `.plugin` file installed via Cowork's plugin system. In practice:
- Cowork's plugin upload (Customize > Personal plugins > +) failed silently with no error message
- Cowork's "custom connector" feature requires a remote HTTPS URL with OAuth — incompatible with a local stdio server
- The `.claude-plugin/plugin.json` manifest and `.mcp.json` bundled in the plugin were never used

**What shipped instead:** Two separate components configured directly in Cowork:
1. **MCP server** — configured in `~/Library/Application Support/Claude/claude_desktop_config.json` via Settings > Developer > Edit Config. Cowork launches the Python process automatically via stdio.
2. **`/nate` skill** — created manually via Cowork's Customize > Skills > Write skill instructions UI

### FastMCP lifespan pattern incompatible

The spec called for a `lifespan` context manager pattern to initialize Supabase and OpenAI clients. With `mcp` v1.26.0, `ctx.request_context.lifespan_state` throws `AttributeError`.

**What shipped:** Module-level globals. Clients are initialized at import time, stored in a `_APP_STATE` dict, accessed via `_get_state()`.

### Framework table columns differ from spec

The spec assumed columns `content`, `nate_would_say`, `guidance`, `scaffold` on the `frameworks` table. The actual table has `description`, `when_to_apply`, `principles`, `steps`, `example_application`.

### Supabase RPC functions required manual creation

- `match_framework_triggers` existed but used `vector(3072)` (public schema) while the embedding columns are `extensions.vector`. Recreated with `extensions.vector(3072)` and `SET search_path = public, extensions`.
- `match_chunks` did not exist (known gap, KIN-360). Created during deployment with the same `extensions.vector` fix.

### NATE_AGENT_ID format

The initial deployment used an MCP hash (`mcp_f4fd17e...`) instead of a Supabase UUID. The env var must be a UUID from the `agent_definitions.id` column.

### Deployment guide

Full setup instructions written at `kinetic-brain/docs/deployment-guide.md` based on the actual deployment experience, including all workarounds discovered during setup.
