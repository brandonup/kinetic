# ADR-003: Context Stack Assembly + Generation Endpoint

**Author:** Gilfoyle
**Date:** 2026-03-22
**Status:** Accepted
**Supersedes:** —
**Superseded by:** —

---

## Context

The generation endpoint assembles a multi-layer context prompt before routing to the LLM. We need to define the layer ordering, token budget enforcement, truncation priority, conversation history injection rules, SSE streaming protocol, BYOK routing, and message persistence order. These decisions gate KIN-275 (context stack implementation) and KIN-276 (generation endpoint).

---

## Decisions

### 1. Layer ordering (9 layers)

The assembled system prompt is built in this order, top to bottom:

| Layer | Name | Source | Sprint 3 |
|-------|------|---------|----------|
| L1 | User bio | `users.bio` | Active |
| L2 | Company description | `companies.description` (active company) | Active |
| L3 | Project instructions | `projects.instructions` (null for company-scope conversations) | Active |
| L4 | Project Active Memory | `active_memory_entries` scoped to project | **Stub** (Sprint 5) |
| L5 | Agent system prompt | `agent_definitions.instructions` | **Stub** (Sprint 4) |
| L6 | Agent Active Memory | `agent_instances.active_memory_entries` | **Stub** (Sprint 5) |
| L7 | Matched framework | Output of framework selection pipeline | **Stub** (Sprint 4) |
| L8 | Project KB RAG | Top-k chunks from RAG retrieval (project KB) | Active |
| L9 | Agent KB RAG | Top-k chunks from RAG retrieval (agent KB) | **Stub** (Sprint 4) |

Conversation history is injected **after L7 and before the current user message**. This means the full prompt structure at generation time is:

```
[L1] [L2] [L3] [L4] [L5] [L6] [L7]
[conversation history]
[L8] [L9]
[current user message]
```

L8 and L9 go after conversation history so retrieved context is adjacent to the user message (most relevant at generation time).

### 2. Token budget enforcement

- Total assembled context (all layers + history, excluding the current user message) must fit within **80% of the model's context window**.
- Model context window is looked up via LiteLLM's model metadata at assembly time.
- Budget is enforced **after** assembly — assemble all layers, then truncate if needed.

### 3. Truncation priority

When assembled context exceeds the token budget, layers are truncated in this order (cut first → cut last):

1. L9 — Agent KB RAG (stub in Sprint 3, no-op)
2. L7 — Matched framework (stub in Sprint 3, no-op)
3. L6 — Agent Active Memory (stub)
4. L5 — Agent system prompt (stub)
5. L4 — Project Active Memory (stub)
6. Conversation history — trim oldest messages first, preserving the verbatim window defined in ADR-004
7. L8 — Project KB RAG (reduce top-k)
8. L3 — Project instructions (truncate to first 500 tokens)
9. L2 — Company description (truncate to first 300 tokens)
10. L1 — User bio (truncate to first 200 tokens — last resort)

Layer content is truncated (not removed entirely) where noted. Conversation history is trimmed at the message boundary (no mid-message cuts).

### 4. Conversation history injection

**When a `conversation_summaries` row exists:**
- Inject the most recent summary as a synthetic `system` message marked `[Summary of earlier conversation]`
- Then inject the `N` most recent verbatim messages (N = verbatim window from ADR-004)
- Messages before the summary window are excluded

**When no summary exists:**
- Inject all messages up to the compression threshold (ADR-004)
- If that exceeds the token budget, truncate oldest first (handled by step 6 above)

System-role messages are excluded from history injection. Only `user` and `assistant` roles are injected.

### 5. SSE protocol

**Backend:**
- `POST /api/v1/conversations/{id}/messages` is the generation endpoint
- Accepts JWT via `?token=` query param as a fallback for routes that use EventSource (which cannot send custom headers)
- Also accepts `Authorization: Bearer <token>` header (for non-EventSource callers)
- Response is `text/event-stream`
- Event format:
  - Content delta: `data: {"delta": "..."}\n\n`
  - Completion: `data: {"done": true}\n\n`
  - Error: `data: {"error": "...", "code": "..."}\n\n`

**Frontend:**
- Chat UI does NOT call the FastAPI endpoint directly
- All SSE requests are proxied through a Next.js server route (`app/api/stream/route.ts`)
- The Next.js route reads the JWT from the session cookie (server-side) and injects it as the `?token=` query param before forwarding to FastAPI

### 6. BYOK routing

1. `model_id` is resolved from the request body. Fallback: `user.default_model_id`.
2. The model's provider is looked up from the model registry.
3. The user's BYOK key for that provider is fetched from `user_api_keys`.
4. If no key exists for that provider: return **402** with `{"error": "no_byok_key", "provider": "..."}`.
5. The BYOK key is injected into the LiteLLM call as `api_key`.
6. The platform embedding key is **never** used for generation — only for embeddings (RAG, framework triggers).

### 7. Message persistence order

1. Persist the **user message** first (`role='user'`, `sequence=next`, `created_at=now()`). This is done synchronously before the LLM call.
2. Begin LiteLLM streaming call.
3. Stream delta events to the client.
4. On stream complete: persist the **assistant message** (`role='assistant'`, `sequence=next`, `model=model_string`, `agent_definition_id=conversation.active_agent_id`).
5. Bump `conversations.updated_at` to `now()` after the assistant message is persisted.

If the LLM call fails mid-stream: the user message remains persisted (correct — it was sent). The assistant message is not written. The `updated_at` bump is skipped. Client receives an error event.

### 8. Background jobs (triggered from generation endpoint)

All background jobs are fire-and-forget via `TaskDispatcher`. They do not block the streaming response.

| Condition | Job |
|-----------|-----|
| First user message in conversation AND `conversation.title IS NULL` | Title generation job (KIN-269) |
| `message_count % 10 == 0` (every 10th message) | Memory proposal job — **stub** in Sprint 3, activates in Sprint 5 |
| `message_count > compression_threshold` (ADR-004) | Rolling summary job (KIN-277) |

`message_count` = count of user-role messages in the conversation after persisting the current one.

---

## Consequences

- L8 is placed after conversation history, not before. This means KB context is closer to the user message. Trade-off: KB context doesn't inform the summary layer. Acceptable at MVP scale.
- 80% token budget leaves headroom for the current user message and the model's response generation. Adjust post-MVP if we see frequent truncation.
- Truncating L1/L2/L3 is a last resort. In practice these are short and should rarely be touched.
- SSE proxy adds one HTTP hop. Latency cost is negligible; security benefit (JWT never in EventSource URL visible to JS) is worth it.
