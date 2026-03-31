# Generation Engine Spec

**Status:** Draft
**Author:** Gilfoyle
**Date:** 2026-03-26
**Tickets:** KIN-385 (generation endpoint), KIN-386 (agent invocation), KIN-387 (citations), KIN-388 (active memory triggers), KIN-389 (title generation), KIN-390 (company conversations), KIN-392 (rolling compression), KIN-393 (compression fallback)
**PRD ref:** `docs/prd.md` §5 (Conversations), §6 (Agents), §7 (KB & RAG), §8 (Frameworks), §9 (Active Memory), §10 (Context Stack & Generation Engine)
**Schema ref:** `docs/db-schema-spec.md` §5 (conversations), §6 (messages), §7 (conversation_summaries), §8–9 (agents), §16 (active_memory_entries), §17 (memory_proposals)
**ADR ref:** `docs/adr-002-rag-retrieval-pipeline.md`, `docs/adr-003-agents-architecture.md`
**Related specs:** `docs/specs/kin-257-projects-conversations-spec.md` §2.3–2.7, `docs/specs/active-memory-spec.md`, `docs/specs/agents.md`

---

## Purpose

This spec defines the implementation contracts for the chat generation engine — the core system that receives a user message, assembles context, calls the LLM, and streams the response. Every feature that executes during or after a generation call is documented here: agent invocation, citation assembly, active memory triggers, title generation, conversation history compression, and company-level conversation scoping.

**Existing code:** `context_assembler.py` (9-layer assembly), `generation.py` (SSE endpoint), `prompts.py` (prompt templates), `llm_client.py` (LiteLLM wrapper). This spec is the authoritative reference for how these components work together and what additional features must be wired in.

---

## Part 1 — Generation Endpoint (KIN-385)

### 1.1 Endpoint Contract

**Endpoint:** `POST /api/v1/conversations/{conversation_id}/generate`
**Auth:** `get_current_user` required.
**Response:** `text/event-stream` (SSE).

**Request body:**

```json
{
  "message": "string (required, non-empty)",
  "model_id": "uuid | null (optional — override per-query model)",
  "agent_id": "uuid | null (optional — activate/switch/deactivate agent)"
}
```

### 1.2 Execution Flow

The generation endpoint executes the following steps in order. Steps marked **(bg)** run as non-blocking `BackgroundTasks` registered before `return StreamingResponse(...)`.

| Step | Action | Blocking? |
|---|---|---|
| 1 | Validate request. Verify conversation belongs to user, not soft-deleted. | Yes |
| 2 | Handle agent invocation if `agent_id` is provided (see §2). | Yes |
| 3 | Store user message (`role='user'`, `sequence=next`). | Yes |
| 4 | Assemble 9-layer context stack via `ContextAssembler.assemble()`. | Yes |
| 5 | Resolve BYOK key + model for generation (see §1.4). | Yes |
| 6 | Stream LLM response via SSE. | Yes (streaming) |
| 7 | On stream completion: store assistant message (`role='assistant'`, `sequence=next`, `model=model_string`, `agent_definition_id=active_agent_id`). | Yes |
| 8 | Update `conversations.updated_at = now()`. | Yes |
| 9 | **(bg)** Title generation — if first message and no title set (see §5). | No |
| 10 | **(bg)** Memory proposal — if `message_count % 10 == 0` (see §4). | No |
| 11 | **(bg)** Compression check — if `message_count > threshold` (see §6). | No |

**Critical:** Background tasks (steps 9–11) are registered via `background_tasks.add_task(...)` in the route handler body *before* `return StreamingResponse(...)`. They execute after the SSE stream closes. They are fire-and-forget — failures are logged but do not surface to the user (except compression fallback, which notifies inline on the next message).

### 1.3 Context Assembly (9-Layer Stack)

The `ContextAssembler` assembles layers based on conversation scope and agent state. All Supabase calls use `run_in_executor` per conventions.

**Layer resolution:**

| Layer | Source | Present when | Assembly |
|---|---|---|---|
| L1 | `users.name` + `users.email` + `users.bio` | Always | `"User: {name}. Email: {email}. {bio}"` |
| L2 | `companies.name` + `companies.description` | Always (active company from conversation) | `"Company: {name}. {description}"` |
| L3 | `projects.instructions` | `project_id IS NOT NULL` | `"Project instructions: {instructions}"` |
| L4 | `active_memory_entries` (project scope) | `project_id IS NOT NULL` AND entries exist | `"Project memory:\n{entries joined by newline}"` |
| L5 | `agent_definitions.instructions` | `active_agent_id IS NOT NULL` | `"Agent ({name}): {instructions}"` |
| L6 | `active_memory_entries` (agent instance scope) | Agent invoked AND instance entries exist | `"Agent memory:\n{entries joined by newline}"` |
| L7 | Framework selection pipeline result | Agent invoked AND match found above threshold | Full framework text injected (see §2.3) |
| L8 | RAG retrieval — project KB | `project_id IS NOT NULL` AND KB has chunks | Top-K chunks by MMR score (see ADR-002) |
| L9 | RAG retrieval — agent KB | Agent invoked AND agent KB has chunks | Top-K chunks by MMR score |

**Prompt structure (final assembly):**

```
[System message: L1 + L2 + L3 + L4 + L5 + L6 + L7]
[Conversation history: summary (if exists) + recent N messages]
[RAG context: L8 + L9 chunks with source attribution]
[User's current message]
```

**Company-level conversations** (`project_id IS NULL`): Skip L3, L4, L8. Agent layers (L5–L7, L9) are included if an agent is active. See §3.

### 1.4 BYOK Key Resolution

1. If `model_id` is provided, look up the model in `llm_models` table. Determine the provider.
2. If `model_id` is null, use the user's `default_model_id` from `users` table. If that is also null, return 402.
3. Look up the user's API key for the resolved model's provider in `user_api_keys`.
4. If no matching key exists, return 402 with: `{ "error": "no_api_key", "provider": "<provider>", "message": "Add a <provider> API key to use this model." }`
5. Decrypt the key via `EncryptionService`.
6. Pass the decrypted key + model string to `llm_client.stream_llm()`.

### 1.5 SSE Stream Format

Each SSE event is a JSON object:

```
event: delta
data: {"content": "partial text chunk"}

event: done
data: {"message_id": "uuid", "model": "claude-sonnet-4-6", "citations": [...]}
```

**Error during stream:**

```
event: error
data: {"error": "provider_error", "message": "Rate limit exceeded"}
```

On stream error, the partial assistant message is still stored (with whatever content was generated). The frontend should handle partial messages gracefully.

### 1.6 Error Responses

| Status | Condition |
|---|---|
| 400 | Empty message |
| 402 | No BYOK key for selected model's provider |
| 404 | Conversation not found, soft-deleted, or not owned by user |
| 422 | Validation failure (malformed body) |
| 503 | LLM provider error (surface provider message if possible) |

---

## Part 2 — Agent Invocation (KIN-386)

### 2.1 Agent Lifecycle in Chat

When the user provides `agent_id` in the generate request, the system activates, switches, or deactivates the agent for the conversation.

| `agent_id` value | Current `active_agent_id` | Action |
|---|---|---|
| UUID (same as current) | Set | No-op — agent already active |
| UUID (different) | Set or null | Switch: deactivate old, activate new |
| `null` | Set | Deactivate: remove agent from context |
| `null` | Null | No-op |

### 2.2 Activate/Switch Flow

1. **Validate access:** Verify agent exists and is accessible (`visibility = 'public'` OR `owner_id = user_id`). Return 403 if not.
2. **Resolve AgentInstance:** Get-or-create pattern per ADR-003 §2:
   ```sql
   SELECT * FROM agent_instances WHERE user_id = $1 AND agent_definition_id = $2;
   -- If not found:
   INSERT INTO agent_instances (user_id, agent_definition_id)
   VALUES ($1, $2)
   ON CONFLICT (user_id, agent_definition_id) DO NOTHING
   RETURNING *;
   -- Re-SELECT if ON CONFLICT hit
   ```
3. **Update conversation:** `PATCH conversations SET active_agent_id = <agent_id>`.
4. **Context assembly:** Layers 5–7 and 9 now included (system prompt, instance active memory, framework selection, agent KB RAG).

### 2.3 Framework Selection Pipeline (Layer 7)

When an agent is active, the 3-step MVP selection pipeline runs to find a matching framework:

1. **Embed query** — embed the user's current message using platform-owned `text-embedding-3-large` key.
2. **Trigger similarity search** — cosine similarity against `framework_trigger_embeddings` for the agent's frameworks. Return top-5 candidates above `SIMILARITY_THRESHOLD` (0.3).
3. **Trigger-count boost + gate** — among candidates, boost frameworks where multiple triggers scored above threshold. Apply confidence gate. If best candidate exceeds final threshold, inject the full framework text. If not, no framework is injected (L7 is empty).

**Framework override handling (from AgentInstance):**

| Override | Effect on pipeline |
|---|---|
| `pinned: ["framework-id"]` | Skip pipeline entirely. Inject the pinned framework directly. If multiple pinned, inject all. |
| `excluded: ["framework-id"]` | Remove excluded frameworks from the candidate pool before step 2. |
| `disabled: true` | Skip framework selection entirely. L7 is empty. |

### 2.4 Deactivate Flow

1. **Update conversation:** `PATCH conversations SET active_agent_id = NULL`.
2. **Context assembly:** Layers 5–7 and 9 are excluded. Base context only (L1–L4 + L8 if project conversation).

### 2.5 Agent Switch and History

When switching agents, the full conversation history is preserved. The new agent sees all prior messages, including responses from the previous agent. Each message retains its `agent_definition_id` — the UI uses this to show attribution markers.

**No state transfer:** Agent A's active memory is not copied to Agent B. Each AgentInstance maintains its own memory independently.

---

## Part 3 — Company-Level Conversations (KIN-390)

### 3.1 Scope Detection

Company conversations have `conversations.project_id = NULL`. This is set at creation and is immutable.

### 3.2 Context Assembly Differences

| Layer | Project conversation | Company conversation |
|---|---|---|
| L1 — User profile | Yes | Yes |
| L2 — Company context | Yes | Yes |
| L3 — Project instructions | Yes | **No** |
| L4 — Project active memory | Yes | **No** |
| L5 — Agent system prompt | If agent invoked | If agent invoked |
| L6 — Agent active memory | If agent invoked | If agent invoked |
| L7 — Matched framework | If agent invoked | If agent invoked |
| L8 — Project KB RAG | Yes (if KB exists) | **No** |
| L9 — Agent KB RAG | If agent invoked | If agent invoked |

### 3.3 Implementation

The `ContextAssembler` checks `conversation.project_id`:
- If not null → fetch project, include L3, L4, L8.
- If null → skip L3, L4, L8. Still include L1, L2 from the conversation's `company_id`.

**Active memory note:** User-initiated "Save to memory" is disallowed in company conversations (no project scope, no agent scope unless agent is active). If an agent is active, saves go to the AgentInstance's active memory.

---

## Part 4 — Active Memory Triggers in Chat (KIN-388)

### 4.1 Three Triggers

The active memory system has three write triggers. All are wired into the generation endpoint. The backend CRUD and proposal review APIs already exist (KIN-308). This ticket wires them into the chat lifecycle.

### 4.2 Trigger 1 — User-Initiated ("Save to memory")

**Already works.** Frontend sends selected text to `POST /api/v1/active-memory`. No backend change needed for this trigger.

**Scope resolution during chat:**
- Agent active → save to AgentInstance active memory
- No agent, project conversation → save to project active memory
- No agent, company conversation → disallowed (no memory scope)

### 4.3 Trigger 2 — AI-Proposed at Conversation End

**Existing endpoint:** `POST /api/v1/conversations/{conversation_id}/end`

This endpoint already exists (KIN-307). When called, it fires a background job that:
1. Fetches recent conversation messages.
2. Calls the LLM with a proposal generation prompt (user's BYOK key).
3. Stores results as `memory_proposals` rows with `trigger_type='conversation_end'`, `status='pending'`.

**No new work needed** for this trigger — it's already implemented.

### 4.4 Trigger 3 — Periodic Background Proposals (every 10 messages)

**Wiring into generation endpoint (step 10 in §1.2):**

After the assistant message is stored, check:
```python
message_count = get_message_count(conversation_id)
if message_count > 0 and message_count % 10 == 0:
    background_tasks.add_task(generate_periodic_proposals, conversation_id, user_id)
```

**`generate_periodic_proposals` function:**

1. Fetch the most recent 10 messages for the conversation.
2. Resolve the user's BYOK key (default model, or first available). If no key → skip silently.
3. Call LLM with the proposal prompt from `active-memory-spec.md` Part 2, Trigger 3.
4. For each returned string, check for duplicate against existing `pending` proposals (case-insensitive content match).
5. Insert non-duplicate proposals into `memory_proposals` with `trigger_type='periodic'`.

**Scope resolution for proposals:**
- If `conversation.active_agent_id` is set → proposals scoped to `agent_instance_id`
- Else if `conversation.project_id` is set → proposals scoped to `project_id`
- Else (company conversation, no agent) → skip proposal generation

**BYOK failure:** Skip silently. Log at `WARNING` level. No user notification.

### 4.5 Active Memory Injection (Context Assembly)

At context assembly time (step 4 in §1.2):

**L4 — Project Active Memory:**
```sql
SELECT content FROM active_memory_entries
WHERE project_id = $1 AND user_id = $2
ORDER BY created_at ASC
```
Join entries with newlines. Inject as: `"Project memory:\n{joined entries}"`

**L6 — Agent Instance Active Memory:**
```sql
SELECT content FROM active_memory_entries
WHERE agent_instance_id = $1 AND user_id = $2
ORDER BY created_at ASC
```
Inject as: `"Agent memory:\n{joined entries}"`

---

## Part 5 — Title Auto-Generation (KIN-389)

### 5.1 Trigger

After the first generation completes (step 9 in §1.2):

```python
if message_count == 2 and conversation.title is None:  # 1 user + 1 assistant
    background_tasks.add_task(generate_title, conversation_id, user_message, user_id)
```

### 5.2 Title Generation Flow

1. Resolve the user's BYOK key (default model or first available).
2. If no key configured → skip. Title stays null. UI renders "New conversation."
3. Call LLM with prompt:
   ```
   Generate a concise title (max 60 characters) for a conversation that starts with this message.
   Return only the title text, no quotes or formatting.

   Message: {first_user_message}
   ```
4. On success: `UPDATE conversations SET title = $1 WHERE id = $2 AND title IS NULL`.
   - The `AND title IS NULL` guard prevents overwriting a user-renamed title.
5. On failure: log at `WARNING`. Title stays null.

### 5.3 User Override

Users rename conversations via `PATCH /api/v1/conversations/{id}` with `title` field. Once set by the user, the auto-generation job does not overwrite it (guarded by `title IS NULL` in the UPDATE).

**Decision (MEMORY.md 2026-03-21):** Title generation uses BYOK key. If no key is configured, title stays null and UI renders "New conversation."

---

## Part 6 — Rolling Summary Compression (KIN-392)

### 6.1 Trigger

After the assistant message is stored (step 11 in §1.2):

```python
total_messages = get_message_count(conversation_id, exclude_system=True)
if total_messages > COMPRESSION_THRESHOLD:
    background_tasks.add_task(compress_conversation, conversation_id, user_id)
```

**Parameters (configuration constants):**
- `COMPRESSION_THRESHOLD = 20` — total non-system messages before compression activates
- `RECENT_MESSAGES_KEPT = 10` — number of recent messages kept verbatim

### 6.2 Compression Flow

1. Fetch all non-system messages for the conversation, ordered by `sequence ASC`.
2. Determine which messages need summarizing:
   - Keep the most recent `RECENT_MESSAGES_KEPT` messages verbatim.
   - Messages older than that are candidates for compression.
3. Check if a summary already covers these messages:
   ```sql
   SELECT messages_covered_up_to FROM conversation_summaries
   WHERE conversation_id = $1
   ORDER BY created_at DESC LIMIT 1
   ```
4. If `messages_covered_up_to >= last_candidate_sequence` → no new compression needed.
5. If new messages need summarizing, collect the un-summarized messages (those with `sequence > messages_covered_up_to` AND `sequence <= total - RECENT_MESSAGES_KEPT`).
6. Resolve user's BYOK key (default model or first available).
7. Call LLM with prompt:
   ```
   Summarize the following conversation segment, preserving key facts, decisions, open questions, and any action items. Be concise but complete.

   {messages formatted as "User: ..." / "Assistant: ..."}
   ```
8. Store result:
   ```sql
   INSERT INTO conversation_summaries (conversation_id, summary_text, messages_covered_up_to, model)
   VALUES ($1, $2, $3, $4)
   ```

### 6.3 Context Assembly with Compression

At context assembly time, conversation history is built as:

1. Fetch the latest `conversation_summaries` row (if any).
2. Fetch the most recent `RECENT_MESSAGES_KEPT` messages.
3. Assemble:
   ```
   [Previous context summary: {summary_text}]
   [Recent messages: user/assistant pairs in order]
   ```

If no summary exists, include all messages (up to a reasonable limit to avoid context overflow).

### 6.4 Summary Rows

Summary rows are append-only. The most recent row is used at assembly time. Old rows are retained for audit. No cleanup job in MVP.

---

## Part 7 — Compression Fallback (KIN-393)

### 7.1 When Fallback Activates

The fallback activates when the compression LLM call (§6.2 step 7) fails after standard retry (3 attempts with exponential backoff):

- BYOK key invalid or revoked
- Provider rate limit
- Provider outage
- No BYOK key configured

### 7.2 Fallback Behavior

1. **Truncate:** Remove the oldest messages from the conversation history used in context assembly. Keep only the most recent `RECENT_MESSAGES_KEPT` messages.
2. **No summary stored:** Do not create a `conversation_summaries` row — the messages are simply excluded from context.
3. **Notify user:** On the next generation, inject an inline system notification in the SSE stream:
   ```
   event: notification
   data: {"type": "compression_failed", "message": "Older messages were trimmed to fit context limits. Check your API key settings."}
   ```
4. **Log:** Log at `ERROR` level with the failure reason.

### 7.3 Recovery

If the user fixes their BYOK key and sends another message, the next compression attempt (triggered by step 11 in §1.2) will run the full LLM-based compression. The truncated messages are still in the database — they are only excluded from context assembly, not deleted.

---

## Part 8 — Citation Assembly (KIN-387)

### 8.1 What Citations Are

When the generation response uses content from KB chunks (L8 or L9), the response includes structured citation metadata so the user can trace AI claims back to source documents.

### 8.2 Citation Data Model

Each citation is a reference to a retrieved chunk:

```json
{
  "document_id": "uuid",
  "document_title": "string",
  "file_type": "string",
  "chunk_index": "int",
  "snippet": "string (first ~200 chars of the chunk)",
  "similarity_score": "float",
  "scope": "project_kb | agent_kb"
}
```

### 8.3 Assembly Flow

1. During RAG retrieval (L8/L9), the `ContextAssembler` collects chunk metadata alongside content. Each `RetrievedChunk` object includes: `chunk_id`, `document_id`, `document_title`, `file_type`, `content`, `similarity_score`, `scope`.
2. After generation completes, the citation array is included in the `done` SSE event:
   ```
   event: done
   data: {"message_id": "uuid", "model": "string", "citations": [{...}, {...}]}
   ```
3. Citations are ordered by `similarity_score DESC` (most relevant first).

### 8.4 Citation Storage

Citations are **not** persisted to the database in MVP. They are computed at generation time and returned in the SSE response only. If the user navigates away and returns, citations are not available for past messages.

**Rationale:** Persisting citations adds a table and write overhead. At MVP scale, the cost of recomputing (if needed) is negligible. Post-MVP, a `message_citations` table can be added.

### 8.5 Frontend Display

Citations appear as expandable references below the AI response. Each citation shows:
- Document title (clickable — navigates to the document in the KB)
- File type icon
- Snippet preview (first ~200 chars)
- Relevance indicator (similarity score mapped to high/medium/low)

---

## Part 9 — Dependencies and Build Order

### 9.1 Ticket Dependencies

```
KIN-385 (generation endpoint) — FOUNDATION, no blockers
  ├── KIN-384 (conversation CRUD) — independent, can parallel
  ├── KIN-386 (agent invocation) — depends on KIN-385
  ├── KIN-387 (citations) — depends on KIN-385 (RAG retrieval)
  ├── KIN-388 (active memory triggers) — depends on KIN-385 (generation hook)
  ├── KIN-389 (title generation) — depends on KIN-385 (background task hook)
  ├── KIN-390 (company conversations) — depends on KIN-385 (scope logic)
  ├── KIN-392 (compression) — depends on KIN-385 (background task hook)
  └── KIN-393 (compression fallback) — depends on KIN-392
```

### 9.2 Implementation Order

1. **KIN-384** (Conversation CRUD) — independent, can start immediately
2. **KIN-385** (Generation endpoint) — core dependency for all others (in Code Review)
3. **KIN-386** (Agent invocation) — adds agent lifecycle to generation
4. **KIN-387** (Citations) — adds citation metadata to RAG response
5. **KIN-388** (Active memory triggers) — adds periodic proposal hook
6. **KIN-389** (Title generation) — adds title background task
7. **KIN-390** (Company conversations) — scoping logic in context assembler
8. **KIN-392** (Compression) → **KIN-393** (Fallback) — sequential pair

KIN-384 and KIN-390 are independent of KIN-386–389 and can be parallelized.

---

## Part 10 — Testing Strategy

### 10.1 Unit Tests

| Component | Test focus |
|---|---|
| `ContextAssembler` | Layer inclusion/exclusion per scope (project vs company), agent vs no-agent, empty layers |
| Agent invocation | Get-or-create, access control (private vs public), switch mid-conversation |
| Citation assembly | Chunk metadata mapping, ordering, empty RAG results |
| Title generation | First-message trigger, skip if title exists, BYOK failure handling |
| Compression | Threshold trigger, summary storage, messages-covered tracking |
| Compression fallback | BYOK failure → truncation, notification event |
| Memory proposal trigger | 10-message interval, scope resolution, deduplication |

### 10.2 Integration Tests

| Scenario | What to verify |
|---|---|
| Full generation flow (project + agent) | All 9 layers assembled, SSE stream completes, messages stored |
| Company conversation | L3/L4/L8 excluded, L1/L2 included |
| Agent switch mid-conversation | Old agent deactivated, new agent layers in context, history preserved |
| BYOK key missing | 402 returned with provider info |
| Long conversation compression | Summary created at threshold, recent messages kept verbatim |
| Citation in response | Citations returned in `done` event with correct document metadata |

---

## Open Questions

None. All architectural decisions referenced in this spec are locked in MEMORY.md or resolved in existing ADRs. Compression threshold values (20/10) are starting points — adjust based on context window analysis post-implementation.
