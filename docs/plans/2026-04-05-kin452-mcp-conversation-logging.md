# KIN-452: MCP Conversation Logging — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Log every `assemble_context` invocation to a `messages_mcp` table with per-layer status, latency, and error tracking — zero latency impact on MCP response path.

**Architecture:** New `messages_mcp` table (append-only, no soft-delete). Edge Function writes fire-and-forget after returning the tool result. `memory_proposals` gains a nullable `mcp_message_id` FK for MCP-sourced memory extraction. Memory extraction deferred to a future cron/scheduled task.

**Tech Stack:** Supabase (Postgres migration + RLS), Deno (Edge Function), Python/FastAPI (admin query endpoint), pytest (API tests)

**Spec:** `docs/specs/mcp-conversation-logging-spec.md` — full schema, write path, memory extraction design, admin queries, edge cases. **Read the spec before each task.**

---

## Task 1: Migration — `messages_mcp` table + `memory_proposals` schema update

**Files:**
- Create: `packages/api/migrations/20260405000012_messages_mcp.sql`
- Modify: `packages/api/migrations/000_complete_schema.sql`

**Step 1:** Write the migration SQL. Use the exact SQL from spec §7. Includes:
- `messages_mcp` table with all 17 columns
- 3 indexes: `idx_messages_mcp_user`, `idx_messages_mcp_agent_instance`, `idx_messages_mcp_created`
- RLS: SELECT own, INSERT open (service role), UPDATE/DELETE deny
- `memory_proposals.conversation_id` → nullable
- New `memory_proposals.mcp_message_id` FK
- CHECK constraint: `conversation_id IS NOT NULL OR mcp_message_id IS NOT NULL`

**Step 2:** Update `000_complete_schema.sql`:
- Add `messages_mcp` table definition after the `mcp_rate_limits` section
- Modify `memory_proposals` definition: `conversation_id` nullable, add `mcp_message_id`, add CHECK constraint

**Step 3:** Commit migration.

---

## Task 2: Edge Function — fire-and-forget logging in `assemble_context`

**Files:**
- Modify: `supabase/functions/kinetic-mcp/tools.ts`

**Step 1:** Modify `assembleContext()` (line 445) to:
1. Record `startTime = Date.now()` at the top
2. After `Promise.allSettled`, record `embeddingEndTime` for embedding latency
3. Build a `layer_status` JSONB object from the `allSettled` results
4. Extract individual layer text for `layer_persona`, `layer_memory`, `layer_framework`, `layer_kb`
5. After assembling `sections` and before `return`, fire the log write

**Step 2:** Add the fire-and-forget write. Follow the existing `waitUntil` pattern from `auth.ts:74-91`:

```typescript
const logRow = {
  user_id: userId,
  agent_definition_id: agent.definitionId,
  agent_instance_id: agent.instanceId,
  query,
  agent_slug: slug,
  context_payload: result,       // the assembled sections string
  layer_persona: persona || null,
  layer_memory: memoryText || null,
  layer_framework: frameworkText || null,
  layer_kb: kbText || null,
  layer_status: layerStatus,
  latency_ms: Date.now() - startTime,
  embedding_latency_ms: embeddingLatency,
  error: topLevelError || null,
  mcp_session_id: null,          // added in Task 3
};

const logPromise = supabase
  .from("messages_mcp")
  .insert(logRow)
  .then(() => {})
  .catch((err: Error) => console.warn("MCP log write failed:", err));

try {
  (globalThis as any).EdgeRuntime.waitUntil(logPromise);
} catch {
  // Fallback: dangling promise
}
```

**Step 3:** Return `result` after the fire-and-forget (response is not blocked).

**Key decisions:**
- `layer_status` values: `"ok"` (non-empty content), `"empty"` (empty string/no data), `"error"` (rejected promise), `"skipped"` (embedding failed → vector layers couldn't run)
- `embedding_latency_ms`: measure around the `embedQuery()` call specifically
- `mcp_session_id`: needs to be threaded from `index.ts` → `executeTool` → `assembleContext` (Task 3)

**Step 4:** Commit.

---

## Task 3: Thread `mcp_session_id` from request to log

**Files:**
- Modify: `supabase/functions/kinetic-mcp/index.ts`
- Modify: `supabase/functions/kinetic-mcp/tools.ts`

**Step 1:** In `index.ts`, extract `Mcp-Session-Id` header from incoming request and pass it through `handleMcpMethod` → `executeTool`.

- Update `handleMcpMethod` signature to accept optional `sessionId: string | null`
- Update `executeTool` signature to accept optional `sessionId: string | null`
- Thread from `Deno.serve` handler through all call sites

**Step 2:** In `tools.ts`, update `assembleContext` signature to accept `sessionId`, use it in the log row.

**Step 3:** Update `executeTool` to pass `sessionId` to `assembleContext`.

**Step 4:** Commit.

---

## Task 4: Admin endpoint — query MCP activity

**Files:**
- Create: `packages/api/app/api/routes/admin_mcp_logs.py`
- Modify: `packages/api/app/main.py` (register router)
- Create: `packages/api/tests/test_admin_mcp_logs.py`

**Step 1:** Write failing tests:
- `TestListMcpLogs.test_returns_logs_for_user` — happy path, returns paginated results
- `TestListMcpLogs.test_returns_empty` — no logs
- `TestListMcpLogs.test_non_admin_returns_403`
- `TestMcpLogStats.test_returns_aggregated_stats` — avg latency, invocation count by agent
- `TestMcpLogStats.test_non_admin_returns_403`

**Step 2:** Implement endpoints:
- `GET /api/v1/admin/mcp/logs?user_id=&limit=50` — recent MCP activity (spec §6, query 1)
- `GET /api/v1/admin/mcp/stats?days=7` — avg latency by agent (spec §6, query 3)

Both admin-only (`require_admin`). Use `run_in_executor` + service-role client. Follow `admin_users.py` patterns exactly.

**Step 3:** Register router in `main.py`.

**Step 4:** Run tests, commit.

---

## Task 5: Update `db-schema-spec.md` + `000_complete_schema.sql` docs

**Files:**
- Modify: `docs/db-schema-spec.md` — add §22 `messages_mcp`, update §16 `memory_proposals`
- Verify: `000_complete_schema.sql` already updated in Task 1

**Step 1:** Add `messages_mcp` section to db-schema-spec. Copy column table from spec §2.

**Step 2:** Update `memory_proposals` section: note `conversation_id` is nullable, new `mcp_message_id` FK, CHECK constraint.

**Step 3:** Commit.

---

## Done-When Checklist

1. [x] `messages_mcp` table created (migration)
2. [x] `memory_proposals` schema updated (nullable `conversation_id`, new `mcp_message_id` FK)
3. [x] Edge Function writes a row per `assemble_context` call (fire-and-forget)
4. [ ] Memory extraction pipeline — **deferred** (spec §5 recommends cron; out of scope for this ticket, noted in comment)
5. [x] Admin can query MCP activity, latency, and per-layer errors

**Note on done-when #4:** The spec recommends memory extraction as a separate cron job (spec §5: "Not in the Edge Function"). This ticket creates the schema support (`mcp_message_id` FK on `memory_proposals`) but the extraction pipeline itself should be a follow-up ticket.

---

## Test Strategy

- **Admin endpoints:** Mock Supabase client, test happy path + empty + 403. Follow `test_admin_users.py` patterns.
- **Edge Function logging:** Manual verification via Cowork `/nate` invocation → check `messages_mcp` table in Supabase.
- **Migration:** Paste in dev Supabase SQL Editor, verify table + indexes + RLS created, verify CHECK constraint.
