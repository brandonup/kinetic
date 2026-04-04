# ADR-008: Remote MCP Server — Edge Function Deployment + Auth Model

**Status:** Proposed
**Author:** Gilfoyle
**Date:** 2026-03-29
**Project:** Kinetic
**Spec ref:** `docs/specs/remote-mcp-server-spec.md`
**Depends on:** ADR-006 (MCP server architecture + auth), ADR-003 (agents architecture)
**Supersedes:** ADR-006 §5 (Platform Key Isolation) — see Decision 3 below

---

## Context

Kinetic has two MCP implementations today:

1. **Hosted MCP endpoint** (`/api/v1/mcp/context`) — FastAPI route, token-authenticated, assembles context and returns it as a single JSON payload. Works but is not an MCP server — it's a REST endpoint that MCP clients can't discover or interact with natively.
2. **Local MCP server** (`packages/mcp/`) — Python stdio server, runs on the user's machine, hardcoded to one agent (Nate), requires manual Cowork configuration per agent.

Neither scales to the target experience: any MCP client connects to one URL and discovers all of a user's agents as slash commands. Three architectural decisions are needed before implementation.

**Constraints:**
- Kinetic's backend is Supabase (Postgres + Edge Functions). No standalone server infrastructure.
- MCP clients (Claude Desktop, Claude Code, ChatGPT) expect a remote HTTP endpoint, not stdio.
- Agent discovery must be dynamic — when a user creates a new agent in Kinetic, it should appear in their MCP client without reconfiguration.
- The local MCP server proved the tool set (persona, memory, frameworks, KB search). The remote server ports these tools, not reinvents them.

---

## Decisions

### 1. Deployment Target: Supabase Edge Functions (Deno)

**Decision:** Deploy the remote MCP server as a Supabase Edge Function, not as a new FastAPI route or standalone service.

**Rationale:**
- **Zero new infrastructure.** Edge Functions run on Supabase's existing Deno runtime. No Docker, no VPS, no separate deploy pipeline.
- **Same-project DB access.** `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are auto-injected. No credential management for DB access.
- **Scales to zero.** No idle compute cost. Functions spin up on request, stay warm ~5 minutes.
- **Aligns with Kinetic's infra decision (ADR-001).** Supabase is the chosen backend. Adding a FastAPI route would work but creates a second deployment path for what is fundamentally a Supabase-native workload.

**Tradeoff — new runtime:** This introduces Deno/TypeScript as a second backend language alongside Python/FastAPI. The crypto port (HKDF + AES-GCM) and Supabase client usage must be validated in Deno. This is the primary implementation risk (see Risks).

**Tradeoff — cold starts:** First request after ~5 minutes of inactivity incurs a 2-3 second cold start. Acceptable for MCP tool calls (users are already waiting for LLM generation). Not acceptable if this ever becomes a latency-sensitive API — but that's not the use case.

### 2. Transport + Session Model: Stateless Streamable HTTP

**Decision:** Use MCP Streamable HTTP transport with stateless, per-request server instantiation. No session persistence across requests.

**Rationale:**
- **Edge Functions are ephemeral.** No in-memory state survives between invocations. Session-aware MCP would require external session storage (Redis, DB), adding complexity for no clear benefit.
- **MCP tool calls are request/response.** The client sends a tool call, the server returns results. No server-initiated notifications or subscriptions are needed for context assembly.
- **Dynamic prompt registration works per-request.** Each request authenticates the user, queries their agents, and registers MCP prompts dynamically. This is slightly redundant (re-querying agents on every request) but correct and simple.

**What this rules out:** Server-sent events for push notifications, long-lived subscriptions, and server-initiated resource updates. If these become needed (e.g., real-time memory updates), a different transport model would be required.

### 3. BYOK for Embeddings (Supersedes ADR-006 §5)

**Decision:** The remote MCP server uses the user's BYOK OpenAI key for embedding calls (framework selection + KB search). This reverses ADR-006 Decision 5 ("Platform Key Isolation — BYOK is never involved in MCP").

**Rationale — why the reversal:**

ADR-006 was written for the hosted FastAPI endpoint, where platform keys absorb embedding costs as an infrastructure subsidy. The economics change for a remote MCP server:

- **Scale model is different.** The hosted endpoint serves one context payload per request. The remote MCP server exposes individual tools — a single user session might call `select_framework` and `search_knowledge_base` separately, doubling embedding calls. At scale, platform-subsidized embeddings become a cost risk.
- **Edge Functions can't access platform secrets easily.** The FastAPI backend has `PLATFORM_OPENAI_KEY` in its environment. Edge Functions have their own secret store. Sharing platform keys across two runtimes increases the blast radius if either is compromised.
- **Users already have BYOK keys configured.** Kinetic requires a BYOK OpenAI key for the web app's generation engine. The remote MCP server reuses the same key — no additional user friction.
- **Crypto port is required anyway.** The BYOK key is encrypted with HKDF + AES-GCM in the DB. The Edge Function must port the decryption logic regardless (for future features). Using BYOK for embeddings exercises this code path immediately, which is better than shipping untested crypto.

**Fallback behavior:** If a user has no OpenAI key configured, embedding-dependent tools (`select_framework`, `search_knowledge_base`) return a clear error: `"Error: No OpenAI API key configured. Add one in Kinetic Settings > API Keys."` Non-embedding tools (`get_agent_persona`, `get_active_memory`, `list_kinetic_agents`) work without a key.

**Cost shift:** Embedding costs move from platform to user. At `text-embedding-3-large` pricing ($0.00013/1K tokens), a heavy MCP user making 100 embedding calls/day costs ~$0.01/day. Negligible, but should be documented in user-facing copy.

### 4. Auth Model: Reuse Existing Token System, Service Role Key for DB

**Decision:** Authenticate MCP requests using the existing `mcp_tokens` table (SHA-256 hashed bearer tokens, per ADR-006 §1). Access the database using `SUPABASE_SERVICE_ROLE_KEY`, which bypasses RLS. All queries must manually filter by `user_id`.

**Rationale:**
- **Token system is proven.** Already implemented, tested (KIN-321), and in production on the FastAPI endpoint.
- **Service role key is necessary.** Edge Functions can't use Supabase Auth JWTs (the MCP client doesn't go through Supabase Auth). The service role key is the standard pattern for server-side Supabase access.

**Security invariant:** Because the service role key bypasses RLS, **every query must include a `user_id` or `owner_id` filter**. A single missed filter is a cross-tenant data leak. This is not a new risk — the FastAPI MCP endpoint uses the same pattern — but it must be enforced consistently in the new codebase.

**Recommended mitigation:** Implement a `resolve_agent(user_id, slug)` helper that encapsulates the ownership check. All tool implementations call this helper rather than querying `agent_definitions` directly. This centralizes the tenant boundary in one function.

---

## Alternatives Considered

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **Supabase Edge Function (chosen)** | Zero new infra, same-project DB, scales to zero, auto-injected secrets | New runtime (Deno), cold starts, crypto port risk | N/A — this is the decision |
| **New FastAPI route** | Same language/runtime as existing backend, no crypto port | Second deployment path (Vercel for frontend, Supabase for DB, now also a FastAPI server for MCP), needs hosting (Railway/Fly/etc.), idle compute cost | Adds infrastructure Kinetic doesn't have. Would need to deploy and manage a persistent server. |
| **Standalone Node.js server (Cloudflare Workers / Vercel Functions)** | Mature MCP TypeScript SDK, no cold start (Cloudflare), good DX | Third infrastructure provider, credential management for Supabase access, not same-project | Fragments the stack. Supabase Edge Functions keep everything in one project. |
| **Extend local MCP server to be multi-agent** | No new deployment, works today | Still local-only (no remote clients), still requires per-user machine setup, doesn't solve discovery | Doesn't meet the goal of "any client, one URL." |

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **Platform keys for embeddings (ADR-006 §5)** | Zero cost to user, simpler (no crypto port needed for MVP) | Platform absorbs all embedding cost at scale, key sharing across runtimes, untested crypto ships later | Cost risk at scale, and the crypto port is needed anyway for future features. Better to exercise it now. |
| **BYOK for embeddings (chosen)** | User pays marginal cost, exercises crypto port immediately, no platform key in Edge Function | Requires crypto port (HKDF + AES-GCM), users without keys get degraded tools | Crypto port is the main risk but it's a one-time cost. Degraded-without-key behavior is acceptable. |

---

## Consequences

**Positive:**
- One URL per user, all agents auto-discovered — the target UX.
- No new infrastructure to deploy or manage.
- BYOK embedding exercises the crypto port early, preventing a deferred risk from becoming a launch blocker later.
- Stateless model is simple to reason about and scale.

**Negative:**
- Deno/TypeScript is a second backend language. Two codebases to maintain for overlapping logic (crypto, agent resolution, embedding).
- Cold starts add 2-3 seconds on first request after idle. Users may perceive this as slowness.
- Service-role key without RLS requires disciplined `user_id` filtering. No safety net if a query misses the filter.
- Per-request prompt registration re-queries the agent list on every request. Minor DB load, but redundant.

**Neutral:**
- ADR-006 decisions §1-4, §6 remain in effect. Only §5 (Platform Key Isolation) is superseded for the remote MCP server. The FastAPI endpoint (if retained) can continue using platform keys.

---

## Risks

- **HKDF implementation mismatch (Python `cryptography` vs Deno Web Crypto):** The BYOK decryption chain (HKDF-SHA256 → AES-256-GCM) must produce identical results across both runtimes. Python's `HKDF(salt=None)` uses an empty byte string internally — Deno must match this exactly. **Mitigation:** Write cross-language test vectors before building anything else. If they don't match, fall back to proxying decryption through the FastAPI backend (adds latency, but unblocks the project).
- **Service-role key leak:** If the Edge Function's environment is compromised, the attacker has full DB access. **Mitigation:** Edge Function secrets are encrypted at rest by Supabase. Limit the function's network egress to Supabase and OpenAI. Monitor for unusual query patterns.
- **Supabase `bytea` format divergence:** The `key_ciphertext` and `key_nonce` columns store binary data as Postgres `bytea`. Supabase returns this as `\x`-prefixed hex strings. The Deno code must handle this format exactly. **Mitigation:** Port the Python `to_bytes()` helper with explicit hex parsing. Test with real encrypted keys, not synthetic data.
- **Agent slug collisions during backfill:** The new `slug` column (spec Step 9) must be unique per owner, not globally unique. The backfill migration must handle duplicate names within the same owner. **Mitigation:** Spec revision (in progress) defines the deduplication strategy.

---

## Review Trigger

- If Supabase Edge Function cold starts exceed 5 seconds consistently → evaluate Cloudflare Workers or a persistent server
- If embedding cost complaints arise from users → consider a hybrid model (platform keys for low-volume users, BYOK for heavy users)
- If a second feature requires crypto in Deno → extract a shared crypto library package
- If the FastAPI MCP endpoint is retired → remove ADR-006 §5 reference and mark this ADR as the sole MCP auth/key decision
