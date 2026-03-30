# ADR-006: MCP Server Architecture + Auth

**Status:** Accepted
**Author:** Gilfoyle
**Date:** 2026-03-23
**Project:** Kinetic
**Ticket:** KIN-317
**Spec ref:** `docs/specs/mcp-spec.md` (KIN-286), `docs/db-schema-spec.md` §18, §21
**Depends on:** ADR-001 (infrastructure), ADR-003 (agents architecture)

---

## Context

Kinetic exposes AgentDefinitions via MCP so external AI clients (Claude Desktop, ChatGPT, Cursor) can use Kinetic's context stack without using Kinetic's chat UI. The MCP server is read-only — it assembles and returns context; the external client handles generation. Sprint 6 implements the full MCP server.

**Scope:** This ADR covers Kinetic's hosted MCP server (multi-user, token-authenticated, rate-limited). A separate local MCP server (`kinetic-brain`) was shipped for direct Cowork integration — see `son_of_anton/kinetic-brain/docs/deployment-guide.md` and `docs/specs/kinetic-brain-plugin-spec.md`.

Key constraints from locked decisions (MEMORY.md):
- Per-user bearer tokens, revocable, generated in-app
- Platform-owned keys for all MCP pipeline calls (embedding, framework reranker)
- No BYOK in MCP — external client brings its own generation key
- Public agents accessible to any authenticated user; private agents owner-only
- Per-user daily rate limit (default 1,000 req/day), HTTP 429 on exceed
- No AgentInstance data exposed (active memory is private)

Six implementation decisions needed before Big Head can build.

---

## Decisions

### 1. Token Hashing: SHA-256

**Decision:** MCP bearer tokens are hashed with SHA-256 before storage. Not bcrypt.

**Rationale (KIN-304):** MCP tokens are high-entropy opaque secrets (generated via `os.urandom(32)`, hex-encoded). They don't need the work factor that bcrypt provides for low-entropy passwords. SHA-256 is:
- Fast (~microseconds) — critical since token validation runs on every MCP request
- Deterministic — enables UNIQUE constraint on `token_hash` (bcrypt is non-deterministic; same input produces different hashes)
- Standard for API token storage (GitHub, Stripe, Linear all use SHA-256 for tokens)

`db-schema-spec.md` §18 currently says "bcrypt hash" — this is a pending correction (copy-paste from the API key encryption section). The canonical choice is SHA-256 per KIN-304 resolution.

**Implementation:**
```python
import hashlib

def hash_token(raw_token: str) -> str:
    """SHA-256 hash for MCP bearer token storage."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
```

Token lookup: `SELECT * FROM mcp_tokens WHERE token_hash = hash_token(bearer) AND revoked_at IS NULL`.

### 2. Token Validation: Hash-per-request, No Cache

**Decision:** Validate the bearer token by computing SHA-256 and querying the DB on every request. No in-memory cache.

**Rationale:** SHA-256 is sub-microsecond. The DB query is a single indexed lookup on `token_hash`. At the MVP rate limit of 1,000 req/day (~0.01 req/sec), caching adds complexity with zero measurable benefit. Caching also introduces a revocation delay — a revoked token would remain valid until the cache TTL expires.

**Review trigger:** If MCP request volume exceeds 100 req/sec sustained, add a TTL cache (60s) with immediate invalidation on revoke.

### 3. Rate Limit Storage: Supabase Row with UPSERT

**Decision:** Track daily request counts in the `mcp_rate_limits` table (db-schema-spec §21) using Supabase's UPSERT with ON CONFLICT.

**Implementation:**
```sql
INSERT INTO mcp_rate_limits (user_id, date, request_count)
VALUES ($1, CURRENT_DATE, 1)
ON CONFLICT (user_id, date)
DO UPDATE SET request_count = mcp_rate_limits.request_count + 1;
```

Check before processing: `SELECT request_count, daily_cap FROM mcp_rate_limits WHERE user_id = $1 AND date = CURRENT_DATE`. If no row exists, the user hasn't made any requests today — proceed (the INSERT above creates the row). If `request_count >= daily_cap`, return HTTP 429.

**Why not Redis:** Adds a service dependency for a counter that resets daily. Supabase row is persistent across restarts, requires no additional infrastructure, and handles the MVP scale trivially. One query per request.

**Why not in-memory:** Lost on restart. A server restart mid-day would reset all counters to zero, allowing users to exceed their daily cap.

### 4. Request Validation Order

**Decision:** Every MCP request is validated in this order:

```
1. Auth       — extract bearer token from Authorization header, SHA-256 hash,
                look up in mcp_tokens. Reject 401 if invalid/revoked.
                Extract user_id from the matched token row.

2. Rate limit — check mcp_rate_limits for user_id + today's date.
                Reject 429 if request_count >= daily_cap.
                Increment counter (UPSERT).

3. Scope      — validate requested scope params (project_id, agent_id).
                Verify user owns/can access each requested entity.
                Reject 403 if unauthorized, 404 if not found.

4. Assemble   — build context stack per the scope. Run pipeline ops
                (embedding, RAG search, framework selection) using platform keys.
                Return assembled context + metadata.
```

**Why rate limit before scope:** Rate limiting is cheap (one DB query). Scope validation may involve multiple ownership checks. Putting rate limit first prevents an attacker from probing entity existence at scale — they hit the rate limit wall before getting useful 403/404 signals.

### 5. Platform Key Isolation

**Decision:** All LLM calls within the MCP pipeline use platform-owned keys. BYOK is never involved in MCP.

| MCP Pipeline Step | Key Used | Model |
|---|---|---|
| Query embedding (for RAG vector search) | `PLATFORM_OPENAI_KEY` | `text-embedding-3-large` |
| Framework selection — embedding similarity | `PLATFORM_OPENAI_KEY` | `text-embedding-3-large` |
| Framework selection — Haiku reranker | `PLATFORM_ANTHROPIC_KEY` | Haiku |
| Context assembly (string concatenation) | No LLM call | N/A |

**Why no BYOK in MCP:** The external client (Claude Desktop, Cursor) handles generation. Kinetic's MCP server only assembles context — it doesn't generate responses. The pipeline ops (embedding, reranking) are internal infrastructure costs, not user-billable generation. Using BYOK for pipeline ops would force users to configure keys just to use MCP, which defeats the purpose of a lightweight connector.

**User cost:** Zero. MCP pipeline calls are platform-subsidized. Users are not charged for embedding or reranking when using MCP.

### 6. Conversation History (L4): Omitted in Sprint 6

**Decision:** The MCP context stack does not include conversation history (Layer 4). No `conversation_id` parameter is accepted.

**Rationale:** MCP is stateless — the external client manages its own conversation history. Injecting Kinetic's conversation history would create a confusing dual-history scenario. The external client's conversation context is sufficient.

**Implementation:** The context assembly function returns an empty string for Layer 4 when the caller is MCP. This is the default behavior when no conversation_id is provided — no special casing required.

**Future consideration:** If users request cross-client conversation continuity (start in Kinetic web, continue in Claude Desktop), a `conversation_id` param could be added. This is not in scope for V1.

---

## Alternatives Considered

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| bcrypt for tokens | Resistant to brute-force on leaked hashes | Slow (~100ms per validation), non-deterministic (no UNIQUE constraint), overkill for high-entropy tokens | KIN-304: wrong tool for the job. SHA-256 is standard for API tokens. |
| Redis for rate limits | Sub-millisecond reads, built-in TTL/expiry | New service dependency, lost on Redis restart (without persistence), ops overhead | Supabase row is simpler, persistent, and handles MVP scale |
| In-memory rate limit | Fastest possible reads | Lost on restart, inaccurate in multi-process deployments | Correctness matters more than speed at this scale |
| BYOK for MCP pipeline | Users pay for their own pipeline ops | Forces key configuration for MCP usage, user friction, billing confusion | MCP should be zero-cost to the user; pipeline ops are platform infrastructure |
| Cache validated tokens (60s TTL) | Reduces DB queries by ~98% at high volume | Revocation delay (up to 60s), added complexity, cache invalidation logic | Not needed at MVP scale (~0.01 req/sec). Add when volume justifies it. |

---

## Consequences

**Positive:**
- SHA-256 token validation is fast and simple — no bcrypt timing concerns
- Rate limiting is persistent and correct across restarts
- Clear validation order prevents entity enumeration via MCP
- Platform key isolation makes MCP zero-cost for users — reduces adoption friction
- No conversation history simplifies the initial implementation

**Negative:**
- SHA-256 tokens are vulnerable to offline brute-force if the DB is compromised (mitigated by high-entropy tokens — 256 bits of randomness makes brute-force infeasible)
- Supabase rate limit adds one DB query per request (acceptable at MVP scale)
- No conversation continuity across Kinetic web and MCP clients

**Neutral:**
- `db-schema-spec.md` §18 needs a pending update (bcrypt → SHA-256). Implementation should use SHA-256 regardless.

---

## Risks

- **Token DB leak:** If `mcp_tokens` table is compromised, SHA-256 hashes of 256-bit random tokens are computationally infeasible to reverse. Risk is theoretical, not practical.
- **Rate limit row bloat:** One row per user per day accumulates over time. Add a cleanup job (delete rows older than 90 days) post-MVP. No impact at current scale.
- **Platform key cost:** Kinetic absorbs embedding + reranking costs for all MCP requests. At 5 users × 1,000 req/day, embedding cost is ~$0.10/day. Monitor if user base grows.

---

## Review Trigger

- MCP request volume exceeds 100 req/sec → add token validation cache
- User base exceeds 100 active MCP users → re-evaluate platform key cost model
- Cross-client conversation continuity requested → revisit L4 omission
- Supabase rate_limits table exceeds 100K rows → add cleanup job
