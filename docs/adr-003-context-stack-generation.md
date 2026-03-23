# ADR-003: Context Stack Assembly + Generation Endpoint Architecture

**Status:** Accepted — Sprint 3
**Author:** Gilfoyle
**Issue:** KIN-269
**Implements:** Sprint 3 (L1–L4 + L8 active). Sprint 4 activates L5–L7 + L9.

---

## 1. Context Stack — Layer Definitions

The context stack is a 9-layer assembly injected as the system prompt for every generation call. Layers are assembled in order (L1 → L9), with conversation history inserted between L7 and the current user message.

| Layer | Name | Data source | Sprint 3 status |
|-------|------|-------------|-----------------|
| L1 | Platform defaults | Hardcoded system prompt constant | Active |
| L2 | User preferences | `users` table: `byok_config`, `display_prefs` | Active |
| L3 | Scope instructions | `projects.instructions` (project conv) or `companies.instructions` (company conv) | Active |
| L4 | Active Memory | `active_memory_entries` where `project_id = ?` | **Stub** (returns empty; filled Sprint 5) |
| L5 | Agent system prompt | `agent_definitions.instructions` | **Inactive** (Sprint 4) |
| L6 | AgentInstance active memory | `agent_instance_memory` | **Inactive** (Sprint 4/5) |
| L7 | Framework selection result | Framework selection pipeline output | **Inactive** (Sprint 4) |
| — | Conversation history | `messages` + `conversation_summaries` (see §3) | Active |
| L8 | Project KB RAG | pgvector cosine similarity on project KB chunks | Active |
| L9 | Agent KB RAG | pgvector cosine similarity on agent KB chunks | **Inactive** (Sprint 4) |

**Insertion order in final prompt:**

```
[L1] [L2] [L3] [L4] [L5] [L6] [L7]
[conversation history]
[L8] [L9]
[current user message]
```

Conversation history sits after the agent context layers and before RAG — it provides recency context while RAG provides retrieved knowledge.

---

## 2. Layer Inclusion Rules

### 2.1 Project conversation (has `project_id`)

Active in Sprint 3: L1, L2, L3 (project instructions), L4 (stub), L8 (project KB RAG).

### 2.2 Company conversation (has `company_id`, no `project_id`)

Active in Sprint 3: L1, L2, L3 (company instructions), L4 (stub), L8 (company KB RAG if exists, else omit L8).

### 2.3 Layer omission rules

- L3 is omitted if instructions field is null or empty string.
- L4 is omitted in Sprint 3 (stub returns no content).
- L8 is omitted if no KB documents exist for the scope.
- Inactive layers (L5, L6, L7, L9) are never injected in Sprint 3 — the assembly function checks an `active_layers` constant set and skips inactive layers silently.

---

## 3. Layer Fetch Implementation

Each layer is a function with signature:

```python
async def fetch_layer_N(context: AssemblyContext) -> str | None:
    ...
```

Returns the layer content as a string, or `None` if the layer should be omitted. The assembler iterates the ordered list, collects non-None results, and concatenates with `\n\n` separators.

`AssemblyContext` carries: `user_id`, `conversation_id`, `project_id | None`, `company_id | None`, `agent_id | None`, `query_text`, `model_context_window`.

### Layer fetch sources

| Layer | Fetch |
|-------|-------|
| L1 | `PLATFORM_SYSTEM_PROMPT` constant (module-level string) |
| L2 | Single `SELECT byok_config, display_prefs FROM users WHERE id = ?` |
| L3 | `SELECT instructions FROM projects WHERE id = ?` or `SELECT instructions FROM companies WHERE id = ?` |
| L4 | Stub: `return None` |
| L8 | Embed query → cosine similarity search on `kb_chunks` → MMR → top-k (see §4) |

### 3.1 Stub pattern for Sprint 5

L4 and L6 are registered in the layer list with a stub function that immediately returns `None`:

```python
async def fetch_layer_4_active_memory(ctx: AssemblyContext) -> str | None:
    # Sprint 5: query active_memory_entries where project_id = ctx.project_id
    return None
```

Sprint 5 fills in the body without touching the assembler loop or any other layer. No refactoring required.

---

## 4. RAG Retrieval (L8)

Parameters (locked, ref ADR-002):

| Param | Value |
|-------|-------|
| Similarity threshold | 0.75 |
| MMR lambda | 0.7 |
| Top-k | 5 |
| Max tokens | `max(floor(model_context_window * 0.15), 2048)` |

Steps:
1. Embed `query_text` using platform embedding key (not BYOK).
2. `SELECT chunk_text, embedding <=> $query_embedding AS distance FROM kb_chunks WHERE project_id = ? AND 1 - distance >= 0.75 ORDER BY distance LIMIT 20`
3. Apply MMR re-ranking on the 20 candidates to select 5 diverse results.
4. Concatenate chunk texts with citation markers.
5. If total tokens exceed `RAG_MAX_TOKENS`, truncate the last chunk to fit.

---

## 5. Token Budget Management

The assembler enforces a hard token ceiling = `model_context_window - RESPONSE_BUFFER_TOKENS` where `RESPONSE_BUFFER_TOKENS = 2048`.

Token counting method: `ceil(len(text) / 4)` (char-proxy). Fast and sufficient for budget enforcement; exact tiktoken counting is not required at assembly time.

### 5.1 Truncation priority (lowest → highest priority, truncate lowest first)

1. **L8/L9 RAG** — truncate to fit budget first. RAG chunks are already ordered by relevance; drop from the tail.
2. **Conversation history** — compress or truncate oldest messages (see §6).
3. **L3 scope instructions** — truncate to 1,000 tokens if still over budget.
4. **L1, L2** — never truncated. If the budget is exceeded after all truncations, proceed anyway and log a warning. These layers are small by design.

### 5.2 Layer size targets

| Layer | Soft cap |
|-------|----------|
| L1 | 500 tokens |
| L2 | 300 tokens |
| L3 | 2,000 tokens |
| L4 | 500 tokens (Sprint 5) |
| L8 | `RAG_MAX_TOKENS` (dynamic) |

---

## 6. Conversation History Injection

History is inserted after L7 (or after L4 in Sprint 3 where L5–L7 are inactive) and before L8.

### 6.1 Normal case (no compression active)

Fetch the N most recent messages in the conversation ordered by `created_at ASC`. Inject as a formatted block:

```
[Conversation history]
User: <content>
Assistant: <content>
...
```

N defaults to 50. If token budget for history is exceeded, drop oldest messages from the front until it fits.

### 6.2 Compressed case (summary exists)

When a `conversation_summaries` row exists for this conversation:
1. Fetch the most recent summary row (`ORDER BY created_at DESC LIMIT 1`).
2. Fetch the 10 most recent verbatim messages (messages created after `summary.last_message_id`).
3. Inject as:

```
[Conversation summary]
<summary text>

[Recent messages]
User: <content>
Assistant: <content>
...
```

The summary always precedes the verbatim messages. Verbatim window size (10) is locked in ADR-004.

---

## 7. Generation Endpoint

### 7.1 Route

```
POST /api/v1/conversations/{conversation_id}/messages
```

Authentication: JWT (via Authorization header or `token` query param — see §9).

### 7.2 Request body

```json
{
  "content": "string (required) — the user's message",
  "model": "string (optional) — overrides the user's default model for this message"
}
```

`agent_id` is not a request parameter. The active agent for a conversation is set at the conversation level (stored on the `conversations` row), not per-message.

### 7.3 Response

Server-Sent Events stream. `Content-Type: text/event-stream`.

**Token event** (one per LLM token):
```
data: {"type":"token","content":"Hello"}
```

**Done event** (stream complete, assistant message persisted):
```
data: {"type":"done","message_id":"<uuid>","conversation_id":"<uuid>"}

data: [DONE]
```

**Error event:**
```
event: error
data: {"type":"error","code":"<error_code>","message":"<human-readable>"}

data: [DONE]
```

The `[DONE]` sentinel always closes the stream, including on error.

### 7.4 Error codes

| HTTP status | `code` | Condition |
|-------------|--------|-----------|
| 402 | `byok_key_missing` | No API key configured for the selected model's provider |
| 403 | `conversation_access_denied` | Authenticated user doesn't own the conversation |
| 404 | `conversation_not_found` | `conversation_id` doesn't exist |
| 422 | `empty_content` | `content` is blank or whitespace-only |
| 500 | `internal_error` | Unexpected server error |

For 402–422 errors, the HTTP status is returned immediately (no SSE stream opened). For 500 errors that occur mid-stream, an `event: error` SSE event is sent before closing.

---

## 8. BYOK Key Routing

1. Resolve the model name: use `request.model` if provided, else `users.default_model`.
2. Determine the provider from the model name (LiteLLM model string prefix — e.g. `gpt-4o` → `openai`, `claude-3-5-sonnet` → `anthropic`).
3. `SELECT encrypted_key FROM user_api_keys WHERE user_id = ? AND provider = ?`
4. Decrypt in server memory using the application encryption key.
5. Pass decrypted key to LiteLLM as `api_key`. **Never log, never store in message rows, never cache between requests.**
6. If no key found → return 402 immediately before any SSE stream is opened.
7. Decrypted key is held in a local variable scoped to the request handler. It is not stored in any object that outlives the request.

---

## 9. Message Persistence Order

This order is **mandatory**. Deviation causes orphaned user messages on LLM failure.

1. Save user message to `messages` table (`role = 'user'`, `content = request.content`). Get back `user_message_id`.
2. Assemble context stack.
3. Open SSE stream to client.
4. Call LiteLLM streaming API. Buffer streamed tokens and forward each as a `token` SSE event.
5. On stream complete: concatenate all tokens → save assistant message to `messages` table (`role = 'assistant'`). Get back `assistant_message_id`.
6. Send `done` SSE event with `message_id = assistant_message_id`.
7. Send `[DONE]` sentinel.
8. Close stream.
9. Enqueue background compression check (see ADR-004 §3).

On LLM error mid-stream: send `event: error` SSE event, send `[DONE]`, close stream. The user message row remains in the DB (correct — it was sent). No assistant message row is created.

---

## 10. `conversations.updated_at` Bump Strategy

**Decision: Option A — DB trigger.**

A `BEFORE INSERT` trigger on the `messages` table bumps `conversations.updated_at = NOW()` on the parent conversation row.

**Rationale:**
- Automatic and consistent across all code paths. Any message insert (generation endpoint, future admin tools, tests) bumps the conversation timestamp without requiring application-level coordination.
- Simplifies the generation endpoint: no explicit `UPDATE conversations` call needed.
- Correct by construction: `conversations.updated_at` always reflects the most recent message time.

**Tradeoff accepted:** The trigger is "magic" — not visible in application code. Mitigated by documenting it here and in the schema spec. Integration tests that verify `updated_at` changes implicitly exercise the trigger.

Trigger definition (Supabase SQL migration):

```sql
CREATE OR REPLACE FUNCTION bump_conversation_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE conversations
  SET updated_at = NOW()
  WHERE id = NEW.conversation_id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_messages_bump_conversation_updated_at
BEFORE INSERT ON messages
FOR EACH ROW EXECUTE FUNCTION bump_conversation_updated_at();
```

---

## 11. SSE Auth Proxy

**Problem:** The browser `EventSource` API does not support custom headers. JWT cannot be sent via `Authorization: Bearer` from the client-side SSE connection.

**Solution:** Next.js server route proxies the SSE request.

### 11.1 Flow

```
Browser → POST /api/stream/conversations/{id}/messages (Next.js route handler)
           ↓ reads JWT from session cookie
           ↓ appends ?token=<jwt> to FastAPI URL
Next.js server → GET /api/v1/conversations/{id}/messages/stream?token=<jwt> (FastAPI)
           ↓ streams SSE events back
Next.js server → streams SSE events to browser
```

The Next.js route handler:
1. Reads the Supabase session cookie to extract the JWT.
2. Forwards the request body to FastAPI with `?token=<jwt>` appended.
3. Pipes the FastAPI SSE response directly to the browser response stream.

### 11.2 FastAPI token validation

FastAPI accepts the JWT via:
- `Authorization: Bearer <token>` header (standard path, used by non-SSE endpoints)
- `?token=<jwt>` query parameter (SSE path)

Both paths run through the same `get_current_user` dependency. The query param path is only enabled for the SSE endpoint — not applied globally.

### 11.3 Security note

The JWT travels as a query parameter on the internal Next.js → FastAPI leg only. It does not appear in browser URLs. The Next.js route is a server-side handler and the FastAPI service is not publicly routable. The token is not logged (FastAPI access log must exclude the `token` query param from this route — configure via middleware).

---

## 12. Assembly Code Structure

```
app/
  services/
    context_assembly/
      __init__.py          # exports assemble_context()
      assembler.py         # main orchestration loop
      layers/
        l1_platform.py
        l2_user_prefs.py
        l3_scope.py
        l4_active_memory.py   # stub
        l5_agent_prompt.py    # stub (Sprint 4)
        l6_agent_memory.py    # stub (Sprint 4/5)
        l7_framework.py       # stub (Sprint 4)
        l8_project_rag.py
        l9_agent_rag.py       # stub (Sprint 4)
      history.py             # conversation history injection
      token_budget.py        # budget tracking + truncation
    byok.py                  # key lookup + decryption
    litellm_client.py        # LiteLLM streaming wrapper
  routers/
    conversations.py         # POST /{id}/messages SSE endpoint
```

`assembler.py` iterates `LAYER_REGISTRY` — an ordered list of `(layer_id, fetch_fn)` tuples. Adding a new layer in Sprint 4/5 = add one entry to the registry and implement the fetch function. The assembler loop does not change.

---

## Done when

- [x] `docs/adr-003-context-stack-generation.md` written
- [ ] Big Head confirms understanding before implementation starts
- [ ] Big Head Sprint 3 tickets (KIN-275, KIN-276, KIN-277) unblocked
- [ ] Dinesh Sprint 3 SSE proxy ticket (KIN-274) unblocked
