# Projects + Conversations Spec (KIN-257)

**Status:** Draft
**Author:** Jared
**Date:** 2026-03-22
**Sprint target:** Implementation in Sprint 2 (Projects CRUD) + Sprint 3 (Conversations + Chat UI)
**Schema ref:** `docs/db-schema-spec.md` §4 (`projects`), §5 (`conversations`), §6 (`messages`), §7 (`conversation_summaries`)

---

## Purpose

This spec defines the API contracts, behavioral rules, and UI requirements for Projects and Conversations — the two entities that form the primary workspace surface of Kinetic. Projects are the organizational unit; Conversations are where the user interacts with the AI. Both are implemented across two sprints and this spec covers them together because their data model and sidebar UI are tightly coupled.

**Implementers:** Dinesh owns all CRUD endpoints and UI. Big Head owns context assembly, generation, and conversation history compression.

---

## Part 1 — Projects

### 1.1 What a Project Is

A Project is an in-app workspace for a specific initiative. It belongs to a Company and owns:
- A set of instructions (static context, Layer 3)
- An Active Memory (dynamic context, Layer 4 — implemented in Sprint 5)
- A Knowledge Base (RAG retrieval, Layer 8 — implemented in Sprint 2)
- A list of Conversations

Projects do not exist outside a Company. Deleting a company cascades to all its projects.

### 1.2 API Contract — Project CRUD

**Base path:** `/api/v1/projects`
**Auth:** All endpoints require `get_current_user`. All operations are scoped to the authenticated user.
**Schema ref:** `docs/db-schema-spec.md` §4 (`projects` table)

#### `POST /api/v1/projects`

Create a project.

**Request body:**
```
{
  "name": string (required, non-empty),
  "company_id": uuid (required),
  "instructions": string (optional, max ~2000 chars / ~500 tokens)
}
```

**Behavior:**
- Verify `company_id` belongs to the requesting user. Return 403 if not.
- Set `user_id` from the authenticated user (denormalized for RLS — see `db-schema-spec.md` § Denormalized user_id).
- No auto-creation of Knowledge Base at this point — KB is created on first document upload (Sprint 2).
- Return 201 with the created project row.

**Response body (201):**
```
{
  "id": uuid,
  "name": string,
  "company_id": uuid,
  "user_id": uuid,
  "instructions": string | null,
  "created_at": ISO timestamp,
  "updated_at": ISO timestamp
}
```

**Errors:**
- 400 — `name` is empty or missing
- 403 — `company_id` does not belong to the requesting user
- 422 — validation failure (malformed body)

---

#### `GET /api/v1/projects`

List all projects for the authenticated user.

**Query params:**
- `company_id` (optional, uuid) — filter by company

**Behavior:**
- Returns all projects owned by the user, ordered by `updated_at DESC`.
- If `company_id` is provided, filter to that company. Return 403 if the company does not belong to the user.

**Response body (200):**
```
{
  "projects": [
    {
      "id": uuid,
      "name": string,
      "company_id": uuid,
      "instructions": string | null,
      "created_at": ISO timestamp,
      "updated_at": ISO timestamp
    }
  ]
}
```

---

#### `GET /api/v1/projects/{project_id}`

Fetch a single project.

**Behavior:** Return 404 if the project does not exist or does not belong to the user.

**Response body (200):** Same shape as a single item from the list endpoint.

---

#### `PATCH /api/v1/projects/{project_id}`

Update a project's fields.

**Request body (all fields optional):**
```
{
  "name": string,
  "company_id": uuid,
  "instructions": string | null
}
```

**Behavior:**
- If `company_id` is provided, verify the new company belongs to the user. Return 403 if not.
- If `company_id` changes, everything transfers — conversations, Active Memory entries, and KB remain attached to the project and move to the new company. No orphaned data. (MEMORY.md 2026-03-21: "Project company reassignment: everything moves.")
- Partial updates only — omitted fields are not changed.
- Return 200 with the updated project row.

**Errors:**
- 403 — new `company_id` does not belong to the user
- 404 — project not found or not owned by user

---

#### `DELETE /api/v1/projects/{project_id}`

Delete a project.

**Behavior:**
- Hard delete. Cascade is handled by the DB (`ON DELETE CASCADE` on `conversations`, `knowledge_bases`, `active_memory_entries`).
- Return 204.

**Note:** No soft-delete for Projects in MVP. Conversations within the project are also hard-deleted (they have their own soft-delete at the conversation level, but cascade from a hard-deleted project overrides this).

---

### 1.3 Field Constraints

| Field | Constraint | Enforcement |
|---|---|---|
| `name` | Required, non-empty | API layer |
| `instructions` | Max ~2000 chars / ~500 tokens | API layer (character limit); token count advisory only in MVP |
| `company_id` | Must belong to the requesting user | API layer (ownership check before write) |

---

### 1.4 UI — Project CRUD (Dinesh)

**Create flow:** "New project" action in the sidebar or main area. Modal or inline form: name (required) + instructions (optional textarea). Company is auto-set to the active company — not user-selectable at create time. User can change company afterward via project settings.

**Edit flow:** Project settings page (or modal): name, instructions, company assignment (dropdown of user's companies).

**Instruction textarea:** Show a soft token counter. Target ≤500 tokens. No hard block in MVP — just a visual indicator. At ~2000 characters, show "Instructions are getting long — keep them focused for best results."

**Delete:** Confirm dialog with "This will also delete all conversations in this project." Destructive action — red confirm button.

**Company reassignment:** Shown as a dropdown of the user's companies. When changed, show inline notice: "All conversations and memory in this project will move to [new company name]."

---

## Part 2 — Conversations

### 2.1 What a Conversation Is

A Conversation is a threaded sequence of user and AI messages. It belongs to a Company and optionally to a Project.

**Two scopes:**

| Scope | `project_id` | Context stack |
|---|---|---|
| Project conversation | Set | Full 9 layers (Layers 1–4 from project + agent layers if invoked + RAG) |
| Company conversation | Null | Layers 1–2 (user + company) + agent layers if invoked. No project context. |

Conversations are the primary entry point to the AI. Users return to past conversations via the sidebar.

### 2.2 API Contract — Conversation CRUD

**Base path:** `/api/v1/conversations`
**Auth:** All endpoints require `get_current_user`.
**Schema ref:** `docs/db-schema-spec.md` §5 (`conversations` table)

#### `POST /api/v1/conversations`

Create a conversation.

**Request body:**
```
{
  "company_id": uuid (required),
  "project_id": uuid (optional — null for company-level conversation),
  "title": string (optional — auto-generated from first message if omitted)
}
```

**Behavior:**
- Verify `company_id` belongs to the requesting user. Return 403 if not.
- If `project_id` is provided, verify it belongs to the user and belongs to `company_id`. Return 403/404 as appropriate.
- Set `user_id` from the authenticated user.
- `active_agent_id` defaults to null — agent is set when the user invokes one.
- `title` defaults to null — it is generated after the first message (see § 2.6 Title Generation).
- Return 201 with the created conversation row.

**Response body (201):**
```
{
  "id": uuid,
  "user_id": uuid,
  "company_id": uuid,
  "project_id": uuid | null,
  "title": string | null,
  "active_agent_id": uuid | null,
  "created_at": ISO timestamp,
  "updated_at": ISO timestamp
}
```

**Errors:**
- 403 — `company_id` or `project_id` does not belong to the user
- 404 — `project_id` not found
- 422 — validation failure

---

#### `GET /api/v1/conversations`

List conversations for the authenticated user.

**Query params:**
- `company_id` (optional, uuid) — filter by company (returns both project and company-level conversations for that company)
- `project_id` (optional, uuid) — filter to a specific project's conversations
- `include_deleted` (optional, bool, default `false`) — include soft-deleted conversations

**Behavior:**
- Default: excludes soft-deleted conversations (`deleted_at IS NULL`).
- Ordered by `updated_at DESC` (most recently active first).
- Verify ownership of any supplied `company_id` or `project_id`.

**Response body (200):**
```
{
  "conversations": [
    {
      "id": uuid,
      "company_id": uuid,
      "project_id": uuid | null,
      "title": string | null,
      "active_agent_id": uuid | null,
      "created_at": ISO timestamp,
      "updated_at": ISO timestamp
    }
  ]
}
```

---

#### `GET /api/v1/conversations/{conversation_id}`

Fetch a single conversation with its messages.

**Response body (200):**
```
{
  "id": uuid,
  "company_id": uuid,
  "project_id": uuid | null,
  "title": string | null,
  "active_agent_id": uuid | null,
  "created_at": ISO timestamp,
  "updated_at": ISO timestamp,
  "messages": [
    {
      "id": uuid,
      "role": "user" | "assistant" | "system",
      "content": string,
      "agent_definition_id": uuid | null,
      "model": string | null,
      "sequence": int,
      "created_at": ISO timestamp
    }
  ]
}
```

**Behavior:**
- Messages ordered by `sequence ASC`.
- Excludes system messages from the response (role = `system` rows are for internal use only — not shown to the user).
- Returns 404 if conversation not found or not owned by the user.
- Returns 404 if conversation is soft-deleted (unless the client explicitly calls the admin path).

---

#### `PATCH /api/v1/conversations/{conversation_id}`

Update a conversation.

**Request body (all fields optional):**
```
{
  "title": string,
  "active_agent_id": uuid | null
}
```

**Behavior:**
- `title`: user-renamed title. Overwrites the auto-generated title.
- `active_agent_id`: setting to null deactivates the agent. Setting to a new UUID activates/switches the agent. If a new agent is set, verify the agent is accessible to the user (`visibility = 'public'` OR `owner_id = user_id`). Return 403 if not.
- Return 200 with updated conversation row (without messages).

---

#### `DELETE /api/v1/conversations/{conversation_id}`

Soft-delete a conversation.

**Behavior:**
- Sets `deleted_at = now()`. Does not delete messages or summaries.
- The conversation disappears from the sidebar.
- Active Memory entries sourced from this conversation (`source_conversation_id`) are not affected — they persist independently.
- Return 204.

**Note on hard delete:** No hard-delete endpoint in MVP. DB data is retained indefinitely (no cleanup job for conversations in MVP). If the parent project is hard-deleted, the cascade removes the conversation rows from DB.

---

### 2.3 API Contract — Messages

**Base path:** `/api/v1/conversations/{conversation_id}/messages`

#### `POST /api/v1/conversations/{conversation_id}/messages`

Send a user message and stream an AI response.

This endpoint is the primary generation trigger. It is handled by Big Head (generation pipeline), not Dinesh. It is documented here for the complete picture.

**Request body:**
```
{
  "content": string (required, non-empty),
  "model_id": uuid (optional — override for this message; falls back to user default)
}
```

**Behavior:**
1. Persist the user message to the `messages` table with `role = 'user'`, `sequence = next`.
2. Assemble the 9-layer context stack (see `docs/prd.md` §10 Context Stack).
3. Route to LLM via LiteLLM using the user's BYOK key for the selected model.
4. Stream the response via SSE.
5. On stream completion, persist the assistant message with `role = 'assistant'`, `sequence = next`, `model = model_string`, `agent_definition_id = active_agent_id` (or null).
6. Update `conversations.updated_at`.
7. If this is the first user message and the conversation has no title, trigger the title generation background job (see § 2.6).
8. If the message count crosses a multiple of 10, trigger the memory proposal background job (Sprint 5 concern — stub in Sprint 3).
9. If message count crosses the compression threshold, trigger rolling summary (see § 2.7).

**Response:** SSE stream. Each event is a content delta chunk. On completion, a final event signals done. See `docs/build-order.md` Sprint 3 for SSE proxy architecture.

**Errors:**
- 400 — empty content
- 402 — no BYOK key configured for the selected model's provider
- 404 — conversation not found or soft-deleted
- 503 — LLM provider error (surface to user with provider-specific message if possible)

---

#### `GET /api/v1/conversations/{conversation_id}/messages`

Fetch messages for a conversation. Already covered by the conversation detail endpoint (`GET /api/v1/conversations/{conversation_id}`) — this standalone endpoint is optional and can be omitted in Sprint 3 if it creates redundant work.

---

### 2.4 Message Threading Rules

Messages are append-only. The `sequence` field is an integer starting at 0, incremented by the API on each message insert. It is the ordering key — do not rely on `created_at` for ordering (clock skew in background writes).

**Message roles:**
- `user` — sent by the human
- `assistant` — generated by the AI (may include agent attribution via `agent_definition_id`)
- `system` — internal (context assembly output, stored for debugging; never returned to the frontend)

**Agent attribution per message:** When an agent is active during generation, the assistant message is stored with `agent_definition_id` set. When no agent is active, `agent_definition_id = null`. This field enables the UI to show agent-attribution markers in the chat thread (Sprint 4 feature — stub the column now).

**Agent switch behavior:** When the user switches agents mid-conversation (`PATCH /api/v1/conversations/{id}` with a new `active_agent_id`), the full conversation history is preserved. Subsequent messages are generated with the new agent's context (Layers 5–7, 9). Prior messages retain their original `agent_definition_id` — the attribution markers in the UI reflect which agent generated each message.

---

### 2.5 Conversation Scoping Rules

The context stack assembled for generation differs by conversation scope:

| Layer | Project conversation | Company conversation |
|---|---|---|
| L1 — User bio | Always | Always |
| L2 — Company description | Always (active company) | Always (active company) |
| L3 — Project instructions | Yes (`instructions` from `projects`) | No |
| L4 — Project Active Memory | Yes (Sprint 5) | No |
| L5 — Agent system prompt | If agent invoked | If agent invoked |
| L6 — Agent Active Memory | If agent invoked (Sprint 5) | If agent invoked (Sprint 5) |
| L7 — Matched framework | If agent invoked (Sprint 4) | If agent invoked (Sprint 4) |
| L8 — Project KB RAG | Yes (Sprint 2) | No |
| L9 — Agent KB RAG | If agent invoked (Sprint 4) | If agent invoked (Sprint 4) |

In Sprint 3, the implementation ships Layers 1–4 + 8 for project conversations and Layers 1–2 for company conversations. Agent layers (5–7, 9) are wired in Sprint 4.

**Determining scope at message send time:** The scope is determined by whether `conversations.project_id` is null. This is set at conversation creation and is immutable after creation. To start a company-level conversation, create with `project_id = null`. To start a project conversation, create with `project_id = <project_id>`.

---

### 2.6 Title Generation

Conversation titles are auto-generated from the first user message. This runs as a background job triggered immediately after the first user message is persisted.

**Trigger:** After the first user message (sequence = 0) is stored and before the streaming response completes (or as a non-blocking background job after).

**LLM call:** Short prompt asking the model to produce a concise title (≤60 chars) from the first message. Use the user's BYOK key with their default model (or the cheapest available model). This is a non-critical background call — failure is silent (title stays null; user can rename manually).

**On success:** `PATCH conversations SET title = '<generated title>'`.

**User override:** The user can rename any conversation via `PATCH /api/v1/conversations/{id}` with a new `title`. Once a user has set a title manually, the auto-generation does not overwrite it. Tracking this: if the title is already set when the background job runs, skip the update. (In practice, the job only runs once on first message, so re-runs are not an issue unless the job fails and is retried.)

**Empty title fallback:** If the title generation job fails or the conversation has no messages yet, the title is null and the sidebar renders it as "New conversation" (display-only, not stored).

---

### 2.7 Conversation History Compression (Rolling Summary)

As conversations grow, older messages are compressed into a rolling summary to stay within the model's context window. This is implemented in Sprint 3 by Big Head.

**Trigger:** After each assistant message is stored, check if `messages where conversation_id = ? and role != 'system'` count > threshold. Threshold is implementation-defined (start at 20 messages — Gilfoyle to confirm based on context window math in Sprint 3 ADR).

**Mechanism:**
1. Identify messages older than the most recent N messages (N = messages to keep verbatim; start at 10 recent).
2. Check if a summary already covers those messages (`conversation_summaries.messages_covered_up_to`).
3. If new messages need summarizing, call the LLM with the un-summarized messages: "Summarize the following conversation segment, preserving key facts, decisions, and open questions."
4. Store result in `conversation_summaries` (see `docs/db-schema-spec.md` §7).
5. At context assembly time, inject the latest summary in place of the compressed messages, followed by the N most recent verbatim messages.

**BYOK key:** Summary generation uses the user's BYOK key with their default model.

**Fallback on BYOK failure:** If no BYOK key is available or the call fails, truncate oldest messages without summarization. Show an inline notification: "Older messages were trimmed to fit context limits." (MEMORY.md 2026-03-21: "Conversation compression fallback: truncate oldest messages without summarization on BYOK key failure.")

**Storage:** `conversation_summaries` rows are append-only. The most recent summary row is used at context assembly time. Old summary rows are retained (audit trail, no cleanup in MVP).

---

### 2.8 UI — Sidebar + Chat (Dinesh)

#### Sidebar (left column)

The sidebar lists all non-deleted conversations for the active company, grouped as follows:

```
[Active Company Name]
  General                          ← company-level conversations
    [conversation title or "New conversation"]
    [conversation title]
  [Project Name A]                 ← project conversations
    [conversation title]
  [Project Name B]
    [conversation title]
```

**Ordering within each group:** `updated_at DESC` — most recently active conversation floats to the top.

**Active state:** The currently open conversation is highlighted.

**Actions per conversation item (hover or context menu):**
- Rename — inline edit of the title
- Delete — soft-delete with confirm dialog: "Delete this conversation? This cannot be undone." (Note: this is a soft-delete — data is retained in DB, but the user sees it as permanent.)

**"New conversation" button:** Creates a new conversation. Context determines scope:
- If the user is inside a project, the new conversation is created with `project_id` set.
- If the user is in the company-level view, the new conversation is created with `project_id = null`.

#### Chat thread

- Messages rendered in sequence order, user messages on the right, AI messages on the left (or standard top-to-bottom thread — match the dark theme per PRD design direction).
- Streaming: AI response streams in word-by-word (or chunk-by-chunk per SSE events).
- Agent attribution marker: when `agent_definition_id` is set on an assistant message, show the agent's name as a small label above or below the message. (Sprint 4 full implementation — in Sprint 3, stub the display without the label since agents aren't wired yet.)
- Model selector: visible in the chat input area. Shows all admin-enabled `generation` models. Models without a matching user BYOK key are visible but greyed out with tooltip "Add an API key to enable." (See `docs/prd.md` §2 — "Model selector UX".)
- Empty state: when a new conversation is opened with no messages, show a placeholder prompt area with "Start a conversation…".

---

## Part 3 — Cross-Cutting Rules

### 3.1 Ownership and RLS

All API endpoints enforce ownership at the application layer before writes. Supabase RLS provides a second line of defense. Both must hold:

- Projects: `user_id = auth.uid()` enforced in RLS and verified in API before any write.
- Conversations: `user_id = auth.uid()` enforced in RLS.
- Messages and summaries: access is scoped through conversation ownership (subquery pattern — see `db-schema-spec.md` §6).

### 3.2 Soft-Delete Filter

Conversations use soft-delete. All list and fetch endpoints must filter `WHERE deleted_at IS NULL` unless the `include_deleted` param is explicitly set. The RLS policy also enforces this by default.

### 3.3 `updated_at` on Conversations

`conversations.updated_at` must be bumped whenever a new message is added. This is what keeps the most recently active conversation at the top of the sidebar. Either:
- The generation endpoint explicitly UPDATEs `conversations.updated_at = now()` after storing each message, OR
- A DB trigger fires on INSERT to `messages` and updates the parent conversation's `updated_at`.

Both approaches are valid. Gilfoyle to specify the preferred pattern in the Sprint 3 ADR. Dinesh implements per that decision.

### 3.4 Cascade Behavior on Deletion

| Parent deleted | Effect on conversations |
|---|---|
| Company (hard delete) | Cascade delete all projects → cascade delete all conversations |
| Project (hard delete) | Cascade delete all conversations (hard) |
| Conversation (soft delete) | Messages and summaries retained. Active Memory entries from this conversation retained (they have `ON DELETE SET NULL` on `source_conversation_id`). |

---

## Part 4 — Decisions Needed

No blocking decisions identified. All major questions are resolved in MEMORY.md. Confirming:

| Decision | Source |
|---|---|
| Soft-delete for conversations (not hard) | MEMORY.md 2026-03-21 |
| Company reassignment moves everything | MEMORY.md 2026-03-21 |
| Two conversation scopes (project vs company-level) | MEMORY.md 2026-03-21 |
| Compression fallback = truncation without summary | MEMORY.md 2026-03-21 |
| Title auto-generated from first message | MEMORY.md 2026-03-21 |
| No hard-delete endpoint in MVP | MEMORY.md 2026-03-21 |
| Active agent = one at a time, stored on conversation | MEMORY.md 2026-03-21 |

One question for Gilfoyle to resolve in the Sprint 3 ADR:

- **Compression threshold:** How many total messages trigger rolling summary, and how many recent messages are kept verbatim? This depends on typical model context windows and the assembled context stack size. Spec uses placeholder values (20 total / 10 recent) — Gilfoyle to confirm.

---

## Open Questions

1. **Compression threshold** — see above. Blocking for Sprint 3 generation ADR only; not blocking for Sprint 2 implementation.
2. **Title generation model** — should this use a fixed cheap model (e.g., Haiku) via platform key, or the user's BYOK default model? Using BYOK means title gen fails until the user sets a key. Using a platform key avoids that. Recommend: platform key (Haiku) for title generation to ensure it always works. **Needs Brandon decision** before Sprint 3.

---

## Assumptions

- Knowledge Base creation (per project) is handled in the KB spec, not here. This spec does not define the KB API — it only references that a project owns a KB.
- Active Memory CRUD (per project) is handled in the Active Memory spec (Sprint 2 Jared deliverable). This spec defines the field exists and its context stack layer but not the write/read API.
- Agent invocation (`active_agent_id` on a conversation) is surfaced here in the data contract but the full agent side-panel UI is specified in the Agents spec (Sprint 2 Jared deliverable).
