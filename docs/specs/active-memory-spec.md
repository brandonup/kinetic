# Active Memory Spec (KIN-268)

**Status:** Draft
**Author:** Jared
**Date:** 2026-03-22
**Sprint target:** Spec approved Sprint 2. Implementation Sprint 5 (Dinesh + Big Head).
**Schema ref:** `docs/db-schema-spec.md` §16 (`active_memory_entries`), §17 (`memory_proposals`), § Configuration Parameters
**PRD ref:** `docs/prd.md` §4 (Projects — Active Memory field), §6 (Agents — AgentInstance Active Memory)

---

## Purpose

Active Memory is the dynamic, AI-curated layer of a user's context. Unlike project instructions (user-authored, static), Active Memory compounds over time — it captures decisions, preferences, and facts that emerge from conversations and persists them into future sessions.

Active Memory exists in two scopes:

| Scope | Context layer | Token cap | Parent entity |
|---|---|---|---|
| Project Active Memory | L4 | 1,000 tokens | `projects` |
| Agent Instance Active Memory | L6 | 500 tokens | `agent_instances` |

Both scopes share the same data model (`active_memory_entries`), the same write triggers, and the same UI patterns. The token caps differ.

---

## Part 1 — Entry Data Model

### 1.1 Table

`active_memory_entries` (see `docs/db-schema-spec.md` §16):

| Column | Notes |
|---|---|
| `id` | UUID PK |
| `user_id` | Denormalized for RLS |
| `project_id` | Nullable. Set for project scope. |
| `agent_instance_id` | Nullable. Set for agent instance scope. |
| `content` | The memory text. Required, non-empty. |
| `source_conversation_id` | Nullable. Set when entry was AI-proposed or user-saved from a conversation. Null for manually authored entries. |
| `created_at` | Immutable — the entry's birth date |
| `updated_at` | Updates when content is edited |

**Polymorphic constraint:** Exactly one of `project_id` or `agent_instance_id` must be set (never both, never neither).

### 1.2 Token Counting

**Method:** Character-proxy approximation: `ceil(char_length(content) / 4)`. This avoids a tiktoken dependency on the hot write path.

**Rationale:** The cap values (1,000 and 500 tokens) are approximate — a 4:1 char/token ratio produces conservative estimates that keep the in-context injected text well within limits. Exact tokenization is not required here.

**Cap values (from `db-schema-spec.md` § Configuration Parameters):**
- `ACTIVE_MEMORY_CAP_PROJECT` = 1,000 tokens
- `ACTIVE_MEMORY_CAP_AGENT` = 500 tokens

**Token count calculation:** Before any write, fetch all existing entries for the scope:
```
SELECT SUM(ceil(char_length(content)::float / 4)) FROM active_memory_entries
WHERE project_id = ? AND user_id = ?   -- or agent_instance_id = ?
```
If `current_tokens + ceil(char_length(new_content) / 4) > cap`, reject the write.

### 1.3 Entry Length Limits

No per-entry minimum. Recommended maximum: 500 characters (~125 tokens). The UI shows a soft warning above 400 characters: "Keep entries short for best injection quality."

There is no per-entry hard limit — the token cap at the scope level is the enforcement mechanism.

---

## Part 2 — Write Triggers

Active Memory has three write paths. **All paths require user confirmation before writing.** There are no automatic writes.

### Trigger 1 — User-Initiated ("Save to memory")

The user can manually save a memory entry at any time during a conversation.

**UI:** A "Save to memory" button in the chat input area (or as a hover action on any AI message). Clicking it opens a small popover/dialog:
- A text field pre-populated with nothing (blank) for free-form entries, OR pre-populated with selected text if the user had selected text in the chat thread before clicking.
- Scope indicator: shows whether this will save to the project AM or agent instance AM (based on what's active in the conversation).
- "Save" button: writes the entry immediately. No approval queue — this is a direct user action.

**Backend:**
- `POST /api/v1/active-memory` — create entry. Validates token cap before write. Returns 422 with `{ "error": "memory_full", "current_tokens": N, "cap": N }` if cap would be exceeded.

**Scope resolution:**
- If the conversation has an active agent (`active_agent_id` is set), the entry goes to the user's `AgentInstance` for that agent.
- Otherwise, the entry goes to the project (if a project conversation) or is disallowed at the company conversation level (company conversations do not have Active Memory).

### Trigger 2 — AI-Proposed at Conversation End

When a conversation ends, the AI reviews the full conversation and proposes a batch of memory updates for user approval.

**Trigger condition:** Fires when the user explicitly ends a conversation OR navigates away to start a new conversation. In practice:
- User clicks "New conversation" in the sidebar → proposals are generated for the conversation being left.
- User clicks an explicit "End & save" button on the conversation (if implemented in the UI — optional).

**Generation:**
1. Background job (`TaskDispatcher`) fires non-blocking after the trigger event.
2. LLM call using the user's BYOK default model. Prompt:

   > "Review this conversation and identify 1–5 facts, decisions, preferences, or working patterns worth remembering in future sessions. Each entry should be a short, standalone sentence. Focus on things that would change how an AI collaborates with this person — not summaries of what was discussed.
   > Format: return a JSON array of strings. Maximum 5 items. If nothing worth remembering, return `[]`."

3. Each returned string becomes a `memory_proposals` row with `trigger_type = 'conversation_end'`, `status = 'pending'`.

**BYOK failure:** If no BYOK key is configured or the call fails, skip silently. No user notification — the proposal path is a best-effort enhancement, not a core write.

### Trigger 3 — Periodic Background Proposals (every 10 messages)

Every 10th message in a conversation (message_count % 10 == 0), the system generates a batch of candidate memory entries for the in-progress conversation.

**Trigger:** Fired from the generation endpoint after the assistant message is persisted. Non-blocking via `TaskDispatcher`.

**Generation:** Same LLM prompt and format as Trigger 2, but restricted to the most recent 10 messages only (not the full conversation).

**Storage:** Each returned string becomes a `memory_proposals` row with `trigger_type = 'periodic'`, `status = 'pending'`.

**Deduplication:** Before inserting, do a case-insensitive content comparison against existing `pending` proposals for the same scope. Skip duplicates.

**BYOK failure:** Skip silently. Same policy as Trigger 2.

---

## Part 3 — Proposal Queue + Review Flow

Proposals from Triggers 2 and 3 are queued in `memory_proposals` (see `docs/db-schema-spec.md` §17) and presented to the user on the next relevant page load.

### 3.1 Persistence

`memory_proposals` rows with `status = 'pending'` persist until the user acts on them. They are not expired or auto-cleaned in MVP.

A pending proposal is scoped to either `project_id` (if the source conversation was a project conversation) or `agent_instance_id` (if an agent was active). Same polymorphic pattern as `active_memory_entries`.

### 3.2 Surfacing Proposals

When the user opens a project (or agent profile), the frontend calls:

`GET /api/v1/active-memory/proposals?project_id=<id>` (or `?agent_instance_id=<id>`)

If pending proposals exist, a non-intrusive banner or panel appears:

> "You have N memory suggestions from recent conversations. [Review →]"

The user can dismiss this and review later — proposals persist.

### 3.3 Review UI

**Proposal review panel:**

```
Memory suggestions from [conversation title / "recent conversation"]

☑ "Prefers concrete examples over abstract frameworks"     [Accept] [Reject]
☑ "Working on Series A fundraise for Acme Corp"            [Accept] [Reject]
☐ "Usually starts with the 'why' before the 'how'"         [Accept] [Reject]

[Accept all] [Reject all]      [Done]
```

- Each proposal shown with its proposed content.
- User can toggle individual proposals, then confirm with "Accept all" / "Reject all" or per-item accept/reject.
- Accepting a proposal: token cap check → if passes, inserts into `active_memory_entries` and sets `memory_proposals.status = 'approved'`.
- Rejecting: sets `memory_proposals.status = 'rejected'`. No write to `active_memory_entries`.
- **Token cap enforcement during review:** If accepting a proposal would exceed the cap, show inline: "Memory is full (N/cap tokens). Remove an entry before accepting this one." The accept button for that item is disabled until space is freed.

---

## Part 4 — CRUD API

### 4.1 Endpoints

**Base path:** `/api/v1/active-memory`
**Auth:** All endpoints require `get_current_user`.

---

#### `GET /api/v1/active-memory`

List Active Memory entries for a scope.

**Query params:**
- `project_id` (uuid, optional)
- `agent_instance_id` (uuid, optional)
- Exactly one must be provided.

**Response (200):**
```json
{
  "entries": [
    {
      "id": "uuid",
      "content": "string",
      "source_conversation_id": "uuid | null",
      "created_at": "ISO timestamp",
      "updated_at": "ISO timestamp"
    }
  ],
  "token_usage": {
    "current_tokens": 340,
    "cap_tokens": 1000
  }
}
```

**Errors:**
- 400 — neither or both scope params provided
- 403 — scope entity does not belong to requesting user

---

#### `POST /api/v1/active-memory`

Create a new entry.

**Request body:**
```json
{
  "content": "string (required, non-empty)",
  "project_id": "uuid | null",
  "agent_instance_id": "uuid | null",
  "source_conversation_id": "uuid | null"
}
```

**Behavior:**
- Exactly one of `project_id` or `agent_instance_id` must be set.
- Token cap check before insert. Return 422 on overflow.
- Return 201 with created entry.

**Errors:**
- 400 — empty content, or both/neither scope params
- 403 — scope entity does not belong to user
- 422 — token cap exceeded: `{ "error": "memory_full", "current_tokens": N, "cap_tokens": N }`

---

#### `PATCH /api/v1/active-memory/{entry_id}`

Update entry content.

**Request body:**
```json
{ "content": "string" }
```

**Behavior:**
- Token cap check: `(total_tokens - old_entry_tokens + new_entry_tokens) <= cap`.
- Return 422 on overflow.
- Return 200 with updated entry.

---

#### `DELETE /api/v1/active-memory/{entry_id}`

Delete an entry.

**Behavior:** Hard delete. Return 204.

---

#### `GET /api/v1/active-memory/proposals`

List pending proposals for a scope.

**Query params:** Same as entries endpoint.

**Response (200):**
```json
{
  "proposals": [
    {
      "id": "uuid",
      "proposed_content": "string",
      "trigger_type": "conversation_end | periodic",
      "conversation_id": "uuid",
      "created_at": "ISO timestamp"
    }
  ]
}
```

---

#### `POST /api/v1/active-memory/proposals/review`

Bulk accept/reject proposals.

**Request body:**
```json
{
  "decisions": [
    { "proposal_id": "uuid", "action": "accept | reject" }
  ]
}
```

**Behavior:**
- Process in order. For each `accept`: token cap check → insert entry → mark proposal `approved`. If cap exceeded, skip and return an error for that proposal_id.
- For each `reject`: mark proposal `rejected`.
- Return 200 with results per proposal_id.

**Response (200):**
```json
{
  "results": [
    { "proposal_id": "uuid", "action": "accepted | rejected | skipped_cap_exceeded" }
  ],
  "token_usage": { "current_tokens": N, "cap_tokens": N }
}
```

---

### 4.2 Admin Endpoints

For debugging, admins can view Active Memory for any user:

`GET /api/v1/admin/active-memory?user_id=<id>&project_id=<id>` — admin role required (403 for non-admins). Read-only. Returns same shape as user endpoint.

---

## Part 5 — UI

**Active Memory editor (in Project settings and Agent Profile page):**

- List of current entries, each showing:
  - Content text (inline editable on click)
  - Source conversation link (if `source_conversation_id` is set) — "From: [conversation title]"
  - Created date
  - Delete button (trash icon)
- Token usage bar: "340 / 1,000 tokens" shown as a progress bar. Turns red above 90%.
- "Add entry" button: opens inline text field.
- Overflow error: if a write would exceed the cap, show: "Memory is full (N/cap tokens). Remove an entry before adding more."

**No sorting controls in MVP.** Entries are shown in `created_at DESC` order (newest first).

---

## Part 6 — Context Assembly Integration

At context assembly time (Sprint 3 stub, Sprint 5 activation):

**Project Active Memory (Layer 4):**
```
PATCH /api/v1/active-memory called → entries for project_id
```

Assembled as:
```
## What I know about this project
- [entry 1 content]
- [entry 2 content]
...
```

**Agent Instance Active Memory (Layer 6):**
```
## What [agent name] knows about working with me
- [entry 1 content]
...
```

If no entries exist for the scope, the layer is omitted (empty string returned by the stub).

---

## Part 7 — Decisions Needed

No blocking decisions. All major behaviors are locked in MEMORY.md. Confirming:

| Decision | Source |
|---|---|
| Triple-trigger (user-initiated + conversation_end + periodic) | MEMORY.md 2026-03-21 |
| Hard cap, no auto-prune, user must prune | MEMORY.md 2026-03-21 |
| Individual rows (not a blob) with source_conversation_id | MEMORY.md 2026-03-21 |
| Periodic interval fixed at 10 messages, not user-configurable | MEMORY.md 2026-03-21 |
| No automatic writes — all writes require user confirmation | MEMORY.md 2026-03-21 |

---

## Open Questions

None. This spec is complete and ready for Gilfoyle pre-implementation review.

---

## Assumptions

- Token counting uses character-proxy (ceil(chars / 4)) rather than exact tiktoken — adequate for approximate caps and avoids a runtime dependency.
- The periodic proposals job fires from the generation endpoint, not a scheduled cron. This requires the chat endpoint to fire the job trigger — Big Head implements the trigger stub in Sprint 3 (`if message_count % 10 == 0 → stub`).
- Company-level conversations do not have Active Memory. No write UI is shown in a company-level conversation.
- Proposals are not expired or cleaned up in MVP. A cleanup job can be added post-MVP if volume becomes an issue.
