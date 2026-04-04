# MCP Conversation Logging — `messages_mcp` Table

**Status:** Draft
**Author:** Gilfoyle
**Last updated:** 2026-03-31
**Ticket:** KIN-452, KIN-454
**Ref:** `db-schema-spec.md` (§16–17 active memory, §18 mcp_tokens, §21 mcp_rate_limits), `supabase/functions/kinetic-mcp/tools.ts`, `remote-mcp-server-spec.md`

---

## 1. Overview

Log MCP agent invocations in a purpose-built `messages_mcp` table, separate from the web app's `messages` table. Each row = one `assemble_context` call (one user query → one agent invocation with all context layers).

**Design goals:**

1. Zero latency impact on the MCP response path (fire-and-forget write)
2. Rich observability (per-layer status, latency, errors)
3. Full context payload capture (what the LLM client actually received)
4. Memory extraction from MCP interactions (agent learns from MCP conversations)
5. No schema changes to existing tables

**Depends on:** KIN-454 (`assemble_context` tool) ships first.

---

## 2. Schema — `messages_mcp`

Append-only. No `updated_at`. No soft-delete.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` | From MCP token auth |
| `agent_definition_id` | `uuid` | `NOT NULL REFERENCES agent_definitions(id) ON DELETE CASCADE` | Resolved from slug |
| `agent_instance_id` | `uuid` | `NOT NULL REFERENCES agent_instances(id) ON DELETE CASCADE` | Per-user agent instance |
| `query` | `text` | `NOT NULL` | User's original question |
| `agent_slug` | `text` | `NOT NULL` | Agent slug used (denormalized for admin readability) |
| `context_payload` | `text` | | Full assembled response sent to client (persona + memory + framework + KB concatenated). Null if invocation failed before assembly. |
| `layer_persona` | `text` | | Persona text returned, or null if empty/failed |
| `layer_memory` | `text` | | Active memory text returned, or null if empty |
| `layer_framework` | `text` | | Framework text returned, or null if no match |
| `layer_kb` | `text` | | KB search results returned, or null if no match |
| `layer_status` | `jsonb` | `NOT NULL` | Per-layer status object (see §3) |
| `latency_ms` | `int` | | Total wall-clock time for `assemble_context` in ms |
| `embedding_latency_ms` | `int` | | OpenAI embedding call latency in ms (null if skipped) |
| `token_count_estimate` | `int` | | Estimated token count of `context_payload` (application-layer, nullable) |
| `error` | `text` | | Top-level error message if invocation failed |
| `mcp_session_id` | `text` | | `Mcp-Session-Id` header value from the request (nullable — some clients skip it) |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:**
- `idx_messages_mcp_user` on `(user_id)` — admin queries by user
- `idx_messages_mcp_agent_instance` on `(agent_instance_id)` — memory extraction scoped to agent
- `idx_messages_mcp_created` on `(created_at)` — time-range admin queries

**RLS:**
- SELECT: `auth.uid() = user_id` (user can see their own MCP history)
- INSERT: service role only (Edge Function writes via service role key)
- UPDATE/DELETE: denied (append-only)

---

## 3. `layer_status` Schema

JSONB object capturing per-layer outcome. Enables admin filtering ("show me all invocations where framework failed").

```json
{
  "persona": "ok",
  "memory": "empty",
  "framework": "ok",
  "kb": "error"
}
```

Valid values per layer: `"ok"` (returned content), `"empty"` (no data for this agent), `"error"` (failure — details in `error` column or layer column), `"skipped"` (embedding failed, so vector layers couldn't run).

---

## 4. Write Path — Fire-and-Forget

Logging must not add latency to the MCP response. The write happens **after** the tool result is returned.

```
assemble_context() called
  ├─ resolveAgent()
  ├─ embedQuery()
  ├─ Promise.allSettled([persona, memory, framework, kb])
  ├─ Assemble context_payload string
  ├─ Return result to client  ← response sent here
  └─ Fire-and-forget: INSERT INTO messages_mcp (...)  ← async, non-blocking
```

**Implementation in Edge Function:**

```typescript
// After assembling the result, before returning:
const logPromise = supabase
  .from("messages_mcp")
  .insert({ user_id, agent_definition_id, agent_instance_id, query, ... })
  .then(() => {})
  .catch((err) => console.warn("MCP log write failed:", err));

// Keep alive after response (same pattern as last_used_at in auth.ts)
try {
  (globalThis as any).EdgeRuntime.waitUntil(logPromise);
} catch {
  // Fallback: dangling promise
}
```

**Failure mode:** If the log write fails, the user's MCP interaction is unaffected. Log a warning. No retry — MCP logs are best-effort, not transactional.

---

## 5. Memory Extraction from MCP

MCP interactions should feed into the same active memory system as web conversations. The extraction is different because:

- Web: extracts from a multi-turn conversation (last 10 messages)
- MCP: extracts from a single query + agent response pair

### Trigger

Memory extraction fires when `messages_mcp` row count for an `agent_instance_id` reaches a threshold since last extraction. Recommended: **every 5 invocations** (not every 10 messages, since MCP invocations are denser than chat turns).

### Extraction input

The LLM prompt for MCP memory extraction receives:

```
User query: "{query}"
Agent context used: {context_payload}
```

This gives the LLM enough to understand what the user asked and what the agent knew. The extraction prompt should be the same `PROPOSAL_PROMPT` used for web conversations, with a preamble noting this is an MCP interaction.

### Output

Same as web: insert rows into `memory_proposals` with `status='pending'`.

**Schema note:** `memory_proposals.conversation_id` is currently `NOT NULL REFERENCES conversations(id)`. MCP interactions don't have a conversation. Two options:

- **(a)** Make `conversation_id` nullable, add `mcp_message_id uuid REFERENCES messages_mcp(id)` — polymorphic source
- **(b)** Add `source_type text NOT NULL DEFAULT 'conversation'` + `source_id uuid NOT NULL` — generic source reference

**Recommendation:** Option (a). It's one nullable change + one new column, and keeps FK integrity. The check constraint becomes: `CHECK (conversation_id IS NOT NULL OR mcp_message_id IS NOT NULL)`.

### Where extraction runs

**Not in the Edge Function.** Memory extraction requires an LLM call (user's BYOK key) which is too heavy for fire-and-forget. Instead:

- Option 1: Cron job / scheduled task that polls `messages_mcp` for unprocessed batches
- Option 2: The Edge Function enqueues a job (e.g., calls a FastAPI endpoint) after every Nth invocation

Option 1 is simpler and decoupled. Recommended polling interval: every 5 minutes.

---

## 6. Admin Observability

### Query: Recent MCP activity for a user

```sql
SELECT agent_slug, query, layer_status, latency_ms, created_at
FROM messages_mcp
WHERE user_id = :user_id
ORDER BY created_at DESC
LIMIT 50;
```

### Query: Invocations where a layer failed

```sql
SELECT *
FROM messages_mcp
WHERE layer_status->>'framework' = 'error'
  AND created_at > now() - interval '24 hours';
```

### Query: Average latency by agent

```sql
SELECT agent_slug,
       AVG(latency_ms) AS avg_ms,
       AVG(embedding_latency_ms) AS avg_embed_ms,
       COUNT(*) AS invocations
FROM messages_mcp
WHERE created_at > now() - interval '7 days'
GROUP BY agent_slug;
```

---

## 7. Migration SQL

```sql
-- messages_mcp table (KIN-452)
CREATE TABLE IF NOT EXISTS public.messages_mcp (
  id                    uuid        NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id               uuid        NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  agent_definition_id   uuid        NOT NULL REFERENCES public.agent_definitions(id) ON DELETE CASCADE,
  agent_instance_id     uuid        NOT NULL REFERENCES public.agent_instances(id) ON DELETE CASCADE,
  query                 text        NOT NULL,
  agent_slug            text        NOT NULL,
  context_payload       text,
  layer_persona         text,
  layer_memory          text,
  layer_framework       text,
  layer_kb              text,
  layer_status          jsonb       NOT NULL,
  latency_ms            int,
  embedding_latency_ms  int,
  token_count_estimate  int,
  error                 text,
  mcp_session_id        text,
  created_at            timestamptz NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX idx_messages_mcp_user ON public.messages_mcp (user_id);
CREATE INDEX idx_messages_mcp_agent_instance ON public.messages_mcp (agent_instance_id);
CREATE INDEX idx_messages_mcp_created ON public.messages_mcp (created_at);

-- RLS
ALTER TABLE public.messages_mcp ENABLE ROW LEVEL SECURITY;

CREATE POLICY messages_mcp_select_own ON public.messages_mcp
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY messages_mcp_insert_service ON public.messages_mcp
  FOR INSERT WITH CHECK (true);
  -- INSERT restricted to service role in practice (Edge Function uses service role key).
  -- No user-facing INSERT endpoint exists.

CREATE POLICY messages_mcp_update_deny ON public.messages_mcp
  FOR UPDATE USING (false);

CREATE POLICY messages_mcp_delete_deny ON public.messages_mcp
  FOR DELETE USING (false);

-- memory_proposals: add MCP source column
ALTER TABLE public.memory_proposals
  ALTER COLUMN conversation_id DROP NOT NULL;

ALTER TABLE public.memory_proposals
  ADD COLUMN IF NOT EXISTS mcp_message_id uuid REFERENCES public.messages_mcp(id) ON DELETE CASCADE;

ALTER TABLE public.memory_proposals
  ADD CONSTRAINT chk_memory_proposals_source
  CHECK (conversation_id IS NOT NULL OR mcp_message_id IS NOT NULL);
```

---

## 8. Edge Cases

| Case | Behavior |
|---|---|
| Embedding fails (no BYOK key) | `layer_framework` and `layer_kb` = null, `layer_status` shows `"skipped"` for both. Persona + memory still logged. |
| Agent slug doesn't exist | `assemble_context` returns error. Row logged with `error` column set, all layers null. |
| `context_payload` exceeds reasonable size | Application truncates at 100K chars. Add `truncated boolean DEFAULT false` if this becomes an issue. |
| `Mcp-Session-Id` not sent by client | `mcp_session_id` is null. No functional impact. |
| Edge Function `waitUntil` not available | Log write runs as dangling promise. May not complete if Edge Function exits early. Acceptable — best-effort. |
| User has no company (shouldn't happen) | Not relevant — `messages_mcp` doesn't require `company_id`. |

---

## 9. Out of Scope

- MCP conversation threading / multi-turn context (future: KIN-453 Option C)
- Real-time streaming of MCP logs to admin dashboard
- Log retention / TTL policy
- Unified view merging `messages` + `messages_mcp` (future UI work)
