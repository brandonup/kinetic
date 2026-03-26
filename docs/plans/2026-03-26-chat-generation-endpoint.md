# Chat Generation Endpoint — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement `POST /conversations/{conversation_id}/generate` — the core chat endpoint that assembles the 9-layer context stack and streams an LLM response via SSE.

**Architecture:** A new `generation.py` route file with a single SSE endpoint. Context assembly is extracted into a dedicated `context_assembler.py` service module so layers can be tested independently. The endpoint stores the user message, assembles context, resolves the BYOK key, streams via `stream_llm()`, accumulates the full response, then stores the AI message.

**Tech Stack:** FastAPI (SSE via `StreamingResponse`), LiteLLM (`stream_llm` in `llm_client.py`), Supabase (9 scoped reads), tiktoken (token counting), existing `rag/retrieval.py` and `rag/framework_selection.py`.

**Ticket:** KIN-385 — Urgent, 3 pts
**Spec refs:** PRD §10 (Context Stack & Generation Engine), §7 (KB & RAG), db-schema-spec.md §1–§9/§16/§19
**Branch:** `brandonup/kin-385-dinesh-implement-chat-generation-endpoint-9-layer-context`

---

## Existing Code Inventory

| What | Where | Reuse |
|---|---|---|
| SSE streaming async generator | `app/services/llm_client.py:stream_llm()` | Call directly |
| Sync LLM call | `app/services/llm_client.py:call_llm()` | For title gen (future) |
| RAG retrieval (returns `RetrievedChunk[]`) | `app/services/rag/retrieval.py:retrieve()` | Call for L8/L9 |
| Framework selection (returns `FrameworkMatch`) | `app/services/rag/framework_selection.py:select_framework()` | Call for L7 |
| BYOK key decrypt | `app/services/user_keys.py:fetch_user_key_async()` | Call for key resolution |
| Store message | `app/api/routes/conversations.py:store_message()` | Pattern reference only — generation stores messages directly |
| Prompt registry | `app/services/prompts.py` | Add system prompt template |
| Auth deps | `app/auth/deps.py:get_current_user` | Reuse |
| Supabase client | `app/db/supabase_client.py:get_supabase()` | Reuse |
| Provider model routing | `app/services/llm_client.py:get_provider_model()` | Used internally by `stream_llm` |
| Config (RAG params, feature flags) | `app/core/config.py:settings` | Read RAG_MAX_TOKENS_*, LLM_ENABLED, RAG_ENABLED |
| `is_reasoning_model()` | `app/core/config.py` | Use for temperature/token param selection |

---

## Task 1: Context Assembler Service — Layers 1–6 (Deterministic)

**Files:**
- Create: `app/services/context_assembler.py`
- Test: `tests/test_context_assembly.py`

### What to build

A `ContextAssembler` class that takes a Supabase client and assembles layers 1–6 from DB reads. All Supabase calls wrapped in `run_in_executor`.

```python
@dataclass
class AssembledContext:
    system_parts: list[str]       # L1–L7 assembled text blocks
    rag_chunks: list[dict]        # L8+L9 citation metadata (for KIN-387)
    rag_context_text: str         # L8+L9 chunk texts joined for injection
    model_context_window: int     # from llm_models for RAG budget
    conversation_history: list[dict]  # recent messages as {role, content}
```

**Layer assembly logic:**

| Layer | DB table | Select columns | Condition |
|---|---|---|---|
| L1 | `users` | `name, bio` | `id = user_id` |
| L2 | `companies` | `name, description` | `id = conversation.company_id` |
| L3 | `projects` | `instructions` | `id = conversation.project_id` (skip if null) |
| L4 | `active_memory_entries` | `content` | `project_id = conversation.project_id` (skip if null) |
| L5 | `agent_definitions` | `instructions` | `id = conversation.active_agent_id` (skip if null) |
| L6 | `active_memory_entries` | `content` | `agent_instance_id = agent_instance.id` (skip if no agent) |

For L6, first look up `agent_instances` where `user_id = user_id AND agent_definition_id = active_agent_id`. Auto-create the instance if it doesn't exist (per ADR-003).

**Format each layer as a labeled section:**
```
[User Profile]
Name: {name}
Bio: {bio}

[Company: {name}]
{description}

[Project Instructions]
{instructions}
...
```

### Tests (TDD)

1. `test_assemble_project_conversation_all_layers` — project + agent → L1–L6 all present
2. `test_assemble_company_conversation` — no project, no agent → L1–L2 only
3. `test_assemble_project_no_agent` — project, no agent → L1–L4
4. `test_assemble_agent_no_project` — company-level + agent → L1–L2, L5–L6
5. `test_missing_bio_graceful` — user.bio is null → L1 still assembled (name only)
6. `test_agent_instance_auto_created` — no existing instance → creates one, returns L6

Mock Supabase with the established pattern from `tests/conftest.py`. Each test sets up only the rows relevant to its scenario.

### Commit

```
feat(api): add context assembler service — layers 1-6 (KIN-385)
```

---

## Task 2: Context Assembler — Layer 7 (Framework Selection)

**Files:**
- Modify: `app/services/context_assembler.py`
- Test: `tests/test_context_assembly.py` (add cases)

### What to build

Add L7 to `ContextAssembler`. If `active_agent_id` is set, call `select_framework()` from `rag/framework_selection.py`. If a match is found, append the `framework_text` to `system_parts`.

L7 requires the user's OpenAI key (for embedding the query). Fetch it via `fetch_user_key_async(supabase, user_id, "openai")`. If no OpenAI key, skip L7 silently (fail-open — framework selection is an enhancement, not a requirement).

### Tests

1. `test_l7_framework_matched` — mock `select_framework` returning a `FrameworkMatch` with text → text appears in system_parts
2. `test_l7_no_match` — `select_framework` returns no match → system_parts unchanged
3. `test_l7_no_openai_key` — `fetch_user_key_async` returns None → L7 skipped, no error

### Commit

```
feat(api): add framework selection layer 7 to context assembler (KIN-385)
```

---

## Task 3: Context Assembler — Layers 8–9 (RAG Retrieval)

**Files:**
- Modify: `app/services/context_assembler.py`
- Test: `tests/test_context_assembly.py` (add cases)

### What to build

Add L8 (Project KB) and L9 (Agent KB) via `rag/retrieval.py:retrieve()`.

- L8: `scope=PROJECT_KB, scope_id=project_id` — only when `project_id` is set
- L9: `scope=AGENT_KB, scope_id=active_agent_id` — only when agent is active

Both require the OpenAI key for embedding. If no key, skip RAG silently.

Pass `model_context_window` (from resolved llm_models row) to `retrieve()` for token budget calculation.

Store returned `RetrievedChunk[]` in `AssembledContext.rag_chunks` (for KIN-387 citations later). Join chunk texts into `rag_context_text` with document title headers:

```
[Source: {document_title}]
{chunk_text}
```

### Tests

1. `test_l8_project_kb_chunks_returned` — mock `retrieve()` returning chunks → `rag_context_text` populated, `rag_chunks` populated
2. `test_l9_agent_kb_chunks_returned` — same for agent scope
3. `test_l8_l9_both_scopes` — project + agent → both scopes' chunks combined
4. `test_rag_no_openai_key` — no key → RAG skipped, empty chunks
5. `test_rag_no_chunks_above_threshold` — `retrieve()` returns `[]` → graceful empty

### Commit

```
feat(api): add RAG retrieval layers 8-9 to context assembler (KIN-385)
```

---

## Task 4: Context Assembler — Conversation History

**Files:**
- Modify: `app/services/context_assembler.py`
- Test: `tests/test_context_assembly.py` (add cases)

### What to build

Fetch recent messages from `messages` table for the conversation, ordered by `sequence`. Also check `conversation_summaries` for any rolling summary.

**Assembly order in the final prompt:**
1. System message = L1–L7 joined + RAG context (L8–L9)
2. Conversation history (summary if exists + recent messages)
3. Current user message (passed separately by the endpoint)

For MVP: fetch all messages, include the last 20 in full as `conversation_history`. If a `conversation_summaries` row exists with `messages_covered_up_to >= 0`, prepend it as a system-role message before the recent messages. This matches the PRD §10 spec on rolling summary.

Store the assembled `conversation_history` as `list[dict]` with `role` and `content` keys (ready for `stream_llm` messages param).

### Tests

1. `test_conversation_history_recent_messages` — 5 messages → all 5 in history
2. `test_conversation_history_with_summary` — summary exists + 25 messages → summary + last 20
3. `test_conversation_history_empty` — no messages → empty list

### Commit

```
feat(api): add conversation history assembly to context assembler (KIN-385)
```

---

## Task 5: Generation Endpoint — SSE Streaming

**Files:**
- Create: `app/api/routes/generation.py`
- Modify: `app/main.py` (register router)
- Test: `tests/test_generation.py`

### What to build

`POST /conversations/{conversation_id}/generate` — SSE endpoint.

**Request body:**
```python
class GenerateRequest(BaseModel):
    message: str                          # User's current message
    model_id: Optional[str] = None        # llm_models.id override (UUID)
    agent_id: Optional[str] = None        # Switch active agent (updates conversation)
```

**Endpoint flow:**

1. Verify conversation ownership (user_id match, not soft-deleted)
2. If `agent_id` provided and differs from conversation's `active_agent_id`, update conversation
3. Resolve model: `model_id` param → user's `default_model_id` → error if neither
4. Look up `llm_models` row → get `model_id` string, `provider`, `context_window`
5. Verify user has BYOK key for that provider → 400 if missing
6. Store user message (insert into `messages` with role=user)
7. Assemble context via `ContextAssembler`
8. Build messages array: `[{role: "system", content: assembled_system}, ...history, {role: "user", content: message}]`
9. Stream via `stream_llm()`, accumulate full response text
10. Store AI message (insert into `messages` with role=assistant, agent_definition_id, model)
11. Return `StreamingResponse(media_type="text/event-stream")`

**SSE event format:**
```
data: {"type": "delta", "content": "chunk text"}\n\n
data: {"type": "done", "message_id": "uuid"}\n\n
data: {"type": "error", "message": "..."}\n\n
```

**Error handling:**
- 404: conversation not found
- 400: no model resolved, no BYOK key for provider
- 500: LLM streaming failure (send error SSE event, don't raise)

**Register in `main.py`:**
```python
from app.api.routes.generation import router as generation_router
app.include_router(generation_router)
```

### Tests

1. `test_generate_success_streams_response` — mock `stream_llm` yielding 3 chunks → SSE events received, AI message stored
2. `test_generate_model_resolution_default` — no model_id param → uses user's default_model_id
3. `test_generate_model_resolution_override` — model_id param → uses that model
4. `test_generate_no_byok_key_400` — user has no key for provider → 400
5. `test_generate_no_model_400` — no model_id and no default → 400
6. `test_generate_conversation_not_found_404` — wrong conversation_id → 404
7. `test_generate_agent_switch` — agent_id differs → conversation.active_agent_id updated
8. `test_generate_stores_user_and_ai_messages` — after stream completes, both messages in DB
9. `test_generate_company_level_conversation` — no project_id → L1–L2 only in context
10. `test_generate_llm_failure_sends_error_event` — `stream_llm` raises → SSE error event, no AI message stored

### Commit

```
feat(api): add chat generation endpoint with SSE streaming (KIN-385)
```

---

## Task 6: System Prompt Template

**Files:**
- Modify: `app/services/prompts.py`

### What to build

Add a `context-stack-system-v1` prompt to the registry. This is the system prompt wrapper that introduces the context layers:

```python
"context-stack-system-v1": {
    "system": (
        "You are a helpful AI assistant. Use the context provided below to inform your responses. "
        "Always prioritize information from the context layers when relevant to the user's question.\n\n"
        "{context_layers}\n\n"
        "{rag_context}"
    ),
},
```

The `{context_layers}` and `{rag_context}` placeholders are filled by the generation endpoint using the assembled context.

### Commit

```
feat(api): add context stack system prompt template (KIN-385)
```

---

## Task 7: Integration Test — Full Flow

**Files:**
- Add to: `tests/test_generation.py`

### What to build

One integration test that wires the full flow end-to-end with mocked Supabase and mocked `stream_llm`:

1. Set up: user, company, project with instructions, agent with instructions, active memory entries for both project and agent, messages in conversation
2. Call the generate endpoint
3. Assert: SSE events received, system prompt contains all 6 deterministic layers, conversation history included, user message stored, AI message stored with correct agent_definition_id and model

This is the "golden path" test that validates the full 9-layer stack assembly.

### Commit

```
test(api): add full-flow integration test for generation endpoint (KIN-385)
```

---

## Spec-Section Coverage Matrix (Complex-tier required)

| PRD §10 Section | Task(s) in plan | Status |
|---|---|---|
| 9-layer context stack assembly | Tasks 1–4 | Covered |
| Per-query model selection | Task 5 (model_id param + resolution) | Covered |
| BYOK key resolution | Task 5 (step 5) | Covered |
| SSE streaming | Task 5 (StreamingResponse + stream_llm) | Covered |
| Conversation history + rolling summary | Task 4 | Covered |
| Agent switch mid-conversation | Task 5 (agent_id param) | Covered |
| Company-level conversations (L1–L2 only) | Task 1 test + Task 5 test | Covered |
| Framework selection (L7) | Task 2 | Covered |
| RAG retrieval L8 + L9 | Task 3 | Covered |
| Store user + AI messages | Task 5 (steps 6, 10) | Covered |
| System prompt template | Task 6 | Covered |
| Compression fallback on BYOK failure | — | ⚠️ OUT OF SCOPE — rolling summary generation is a background job (already handled by KIN-306/307 periodic proposals). First-time summary generation triggered by message count threshold, not by the generation endpoint. |
| SSE auth proxy (frontend) | — | ⚠️ OUT OF SCOPE — frontend proxy already exists at `app/api/stream/route.ts` per ticket description. Backend accepts token via header (standard auth dep). |

---

## Done When

- User can send a message and receive a streamed LLM response with full 9-layer context
- All layers assembled correctly based on conversation scope (project vs company, agent vs no-agent)
- BYOK key resolution works for all 4 providers
- Conversation history (recent messages + rolling summary) included in prompt
- Both user message and AI response stored in `messages` table
- Per-query model selection via `model_id` param works
- Agent switch mid-conversation updates `active_agent_id`
- Tests pass: context assembly (6 tests), framework L7 (3 tests), RAG L8/L9 (5 tests), history (3 tests), endpoint (10 tests), integration (1 test) = **28 tests minimum**
