# Agents Spec — AgentDefinition + AgentInstance

**Status:** Draft
**Owner:** Jared
**Last updated:** 2026-03-22
**Ticket:** KIN-242
**Ref:** `docs/domain-model.md` §AgentDefinition, §AgentInstance · `docs/prd.md` §6 · `docs/db-schema-spec.md` §8–11

---

## 1. Overview

Agents in Kinetic are split into two entities:

- **AgentDefinition** — the shared blueprint. Owned by one user. Contains system prompt, Knowledge Base, and Framework Library. Can be private or public.
- **AgentInstance** — per-user runtime state. Created automatically on first invocation. Holds Active Memory and framework overrides for that user.

One AgentDefinition → many AgentInstances (one per invoking user).

---

## 2. AgentDefinition

### Fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | uuid | Yes | PK |
| `owner_id` | uuid (FK users) | Yes | Creator and manager |
| `name` | string, ≤100 chars | Yes | Display name (e.g., "Strategist", "Nate Jones") |
| `instructions` | text | Yes | The system prompt. User-authored or auto-generated from corpus. ~500 tokens target. |
| `type` | enum `custom \| thought_leader` | Yes | `custom` = user-authored instructions. `thought_leader` = corpus-seeded with auto-generated system prompt. |
| `visibility` | enum `private \| public` | Yes | Default: `private`. `shared` deferred post-MVP. |
| `knowledge_base_id` | uuid (FK knowledge_bases) | No | Optional. Attached KB for RAG retrieval (Layer 9). |
| `mcp_enabled` | boolean | Yes | Whether this agent is accessible via MCP. Default: `false`. |
| `created_at` | timestamptz | Yes | Auto |
| `updated_at` | timestamptz | Yes | Auto |

### Constraints

- `name` must be unique per `owner_id`.
- `instructions` required and non-empty before the agent can be used or set to `public`.
- Visibility can only be set to `public` if `instructions` is non-empty.

### Update propagation

AgentDefinition updates (instructions, KB, frameworks) are **immediate** — all invokers see the updated state on their next query. No versioning in MVP. Revisit when `shared` visibility ships post-MVP.

---

## 3. AgentInstance

Created automatically on first invocation of an AgentDefinition by a user.

### Fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | uuid | Yes | PK |
| `agent_definition_id` | uuid (FK agent_definitions) | Yes | The parent definition |
| `user_id` | uuid (FK users) | Yes | The invoking user |
| `active_memory` | text | No | AI-curated facts for this user's relationship with the agent. ≤500 tokens. Default: null (empty). |
| `active_memory_updated_at` | timestamptz | No | Last write timestamp |
| `framework_overrides` | jsonb | No | Pinned or excluded framework IDs. Schema: `{ pinned: string[], excluded: string[] }`. Default: `{}`. |
| `created_at` | timestamptz | Yes | Auto |
| `updated_at` | timestamptz | Yes | Auto |

### Constraints

- One AgentInstance per `(agent_definition_id, user_id)` pair. Unique constraint enforced at DB level.
- `active_memory` hard cap: 500 tokens. Write rejected with error if exceeded. Token count displayed in editor.
- Instance data is **private to the invoking user**. The definition owner cannot access or aggregate instance data.

### Lifecycle

| Event | Behavior |
|---|---|
| First invocation | AgentInstance auto-created with null active memory and empty framework overrides |
| Owner's private agent | Owner's AgentInstance created when the agent is created |
| User loses access | Instance retained but inactive. Reactivated if access restored, or user can delete. |

---

## 4. Agent Profile Page

Route: `/agents/:agentId`
Access: Owner only (MVP — private agents). Any Kinetic user for public agents (read-only if not owner).

### Sections

**Instructions tab**
- Displays `instructions` field (system prompt) in a text editor
- Owner can edit and save
- For `thought_leader` agents: "Regenerate from corpus" button triggers auto-generation flow (see §7)
- Non-owners see instructions (agents are `transparent` in MVP — opaque deferred)

**Knowledge Base tab**
- Browse documents in the agent's KB (folders + tags)
- Upload new documents (triggers ingestion pipeline)
- Delete documents
- If no KB attached: prompt to create one

**Framework Library tab**
- List of all frameworks for this agent
- Per-framework: name, description, category, confidence badge, edit/delete actions
- Upload frameworks via JSON file (MVP — extraction runs externally)
- Edit individual frameworks inline (name, description, when_to_apply, principles, steps)
- Pin/exclude frameworks per-session (stored in AgentInstance.framework_overrides)

**Settings tab**
- Visibility toggle: `private` / `public`
- MCP: enable/disable, show/copy MCP connector URL (if enabled)
- Danger zone: delete agent (owner only; blocked if agent is public and has invokers — must transfer first)

---

## 5. Agent Invocation UX

### How invocation works

1. User opens a conversation (project or company level).
2. An **Agent Selector** is accessible via a side panel toggle or dropdown in the chat UI.
3. User selects an agent from their owned + public agents list.
4. Agent is activated: system prompt (L5), agent active memory (L6), framework pipeline (L7), agent KB (L9) are added to the context stack.
5. Visual indicator appears in the chat header: agent name + avatar/badge. Every AI response generated while an agent is active is tagged with `agent_id`.
6. User can deactivate the agent (returns to base context) or switch to a different agent.

### One agent at a time (MVP)

Only one agent can be active per conversation in MVP. Multi-agent is post-MVP.

### Agent selector contents

| Section | What's shown |
|---|---|
| My agents | AgentDefinitions owned by the current user (private + public) |
| Public agents | All public AgentDefinitions in Kinetic, excluding the user's own |

Agents without a valid `instructions` field are shown greyed out and cannot be invoked.

---

## 6. Agent Switch Behavior

Switching agents mid-conversation:

1. Previous agent is deactivated.
2. New agent is activated — its system prompt, active memory, frameworks, and KB replace the previous agent's in the context stack.
3. **Full conversation history is preserved.** All prior messages (including responses from the previous agent) remain visible in the UI and are included in the rolling context.
4. Each message carries a nullable `agent_id` field. Messages generated with no agent have `agent_id = null`. The UI renders a visual marker when `agent_id` changes (e.g., "Switched to Nate Jones").
5. Each agent's AgentInstance retains its own active memory independently — switching does not affect either instance's memory state.

---

## 7. Thought Leader Agent Flow

For `type = thought_leader`. MVP flow: extraction runs externally; user uploads results.

**Step 1 — Create agent**
User creates a new agent, selects type `thought_leader`.

**Step 2 — Upload corpus**
User uploads source documents (the thought leader's writing, transcripts, etc.) to the agent's Knowledge Base. Standard ingestion pipeline runs.

**Step 3 — Auto-generate system prompt**
User triggers "Generate instructions from corpus." System sends KB contents (or a summary) + a generation prompt to the user's default LLM (BYOK). Returns a drafted system prompt. Requires at least one API key configured.

**Step 4 — Review and edit**
User reviews the generated instructions in the editor. Can edit freely before saving.

**Step 5 — Upload frameworks**
User uploads a structured JSON file containing extracted frameworks. Format matches the extraction script output. Upload behavior:
- Matching `id` → update existing framework
- New `id` → add to library
- Missing `id` → retain (not deleted)
- Per-framework validation with partial import (invalid entries skipped, valid ones imported)

**Step 6 — Review frameworks**
User browses the Framework Library, edits trigger phrases, adds/removes frameworks as needed.

**Step 7 — Set visibility**
User sets to `public` when ready to share.

---

## 8. Access Rules

### MVP visibility model

| Visibility | Who can invoke | Who can edit |
|---|---|---|
| `private` | Owner only | Owner only |
| `public` | Any authenticated Kinetic user | Owner only |

`shared` visibility (explicit invoker grants) is deferred post-MVP.

### User disable rule

Before an admin can disable a user account, **all public agents owned by that user must be transferred to another user or set to private**. The disable action is blocked in the admin panel until this condition is met. Admin UI must surface the list of blocking agents and provide a transfer/set-private action inline.

---

## 9. MCP Connector

When `mcp_enabled = true`, the agent is accessible via Kinetic's MCP server.

- Owner generates a connector URL from the Agent Profile Settings tab (or User Profile).
- MCP exposes: system prompt, framework selection pipeline, KB RAG retrieval.
- MCP does **not** expose: AgentInstance active memory, framework overrides, Thought Stream.
- Access control: public agents accessible to any authenticated user. Private agents: owner only.
- URLs are per-user, revocable.
- Rate limit: 1,000 MCP requests/day per user (admin-configurable). HTTP 429 on exceed.

Full MCP spec: `docs/prd.md` §MCP.

---

## 10. API Contract

### AgentDefinition endpoints

| Method | Path | Description | Auth |
|---|---|---|---|
| `GET` | `/api/v1/agents` | List agents (owned + public) | User |
| `POST` | `/api/v1/agents` | Create AgentDefinition | User |
| `GET` | `/api/v1/agents/:id` | Get AgentDefinition | Owner / any (if public) |
| `PATCH` | `/api/v1/agents/:id` | Update fields | Owner |
| `DELETE` | `/api/v1/agents/:id` | Delete agent | Owner (blocked if public + has invokers) |
| `POST` | `/api/v1/agents/:id/generate-instructions` | Auto-generate system prompt from KB | Owner |

### AgentInstance endpoints

| Method | Path | Description | Auth |
|---|---|---|---|
| `GET` | `/api/v1/agents/:id/instance` | Get or create AgentInstance for current user | User |
| `PATCH` | `/api/v1/agents/:id/instance` | Update active memory or framework overrides | User |

### Framework endpoints

| Method | Path | Description | Auth |
|---|---|---|---|
| `GET` | `/api/v1/agents/:id/frameworks` | List all frameworks for an agent | Owner / invoker |
| `POST` | `/api/v1/agents/:id/frameworks` | Create single framework | Owner |
| `POST` | `/api/v1/agents/:id/frameworks/upload` | Bulk upload from JSON file (merge behavior) | Owner |
| `PATCH` | `/api/v1/agents/:id/frameworks/:frameworkId` | Update framework | Owner |
| `DELETE` | `/api/v1/agents/:id/frameworks/:frameworkId` | Delete framework | Owner |

### Request / Response shapes

**POST /api/v1/agents**
```json
{
  "name": "string",
  "instructions": "string",
  "type": "custom | thought_leader",
  "visibility": "private | public",
  "mcp_enabled": false
}
```
Returns: full AgentDefinition object.

**PATCH /api/v1/agents/:id/instance**
```json
{
  "active_memory": "string | null",
  "framework_overrides": {
    "pinned": ["framework-id-1"],
    "excluded": ["framework-id-2"]
  }
}
```
Returns: full AgentInstance object.

**POST /api/v1/agents/:id/frameworks/upload**
Request: `multipart/form-data`, field `file` = JSON file.
Returns:
```json
{
  "imported": 12,
  "updated": 3,
  "skipped": 1,
  "errors": [
    { "id": "bad-framework", "reason": "missing required field: name" }
  ]
}
```

---

## 11. Framework User Overrides API (KIN-391)

Framework overrides allow users to customize the framework selection pipeline per-AgentInstance. The overrides are stored on `agent_instances.framework_overrides` (JSONB, per ADR-003 §5).

### 11.1 Override Types

| Override | JSONB field | Behavior |
|---|---|---|
| **Pin** | `pinned: ["framework-id", ...]` | Force-inject the specified framework(s), skip the selection pipeline entirely. If multiple pinned, all are injected. |
| **Exclude** | `excluded: ["framework-id", ...]` | Remove specified frameworks from the candidate pool before the selection pipeline runs. |
| **Disable** | `disabled: true` | Skip framework selection entirely. Layer 7 is empty for all queries. Overrides any pinned/excluded values. |

**Default state:** `{ "pinned": [], "excluded": [], "disabled": false }` (no overrides).

### 11.2 Endpoint

**`PATCH /api/v1/agents/:id/instance`**

The existing instance PATCH endpoint accepts `framework_overrides` as a partial update field. The full JSONB value is replaced on each update (not merged).

**Request body (framework overrides portion):**

```json
{
  "framework_overrides": {
    "pinned": ["framework-id-1"],
    "excluded": ["framework-id-2"],
    "disabled": false
  }
}
```

All fields within `framework_overrides` are optional. If omitted, defaults apply:
- `pinned`: `[]`
- `excluded`: `[]`
- `disabled`: `false`

**Response:** Full AgentInstance object with updated `framework_overrides`.

### 11.3 Validation Rules

1. **Framework existence:** All IDs in `pinned` and `excluded` must exist in the parent AgentDefinition's `frameworks` table. Invalid IDs are rejected with 422:
   ```json
   {
     "error": "invalid_framework_ids",
     "invalid_ids": ["nonexistent-id"],
     "message": "Framework IDs not found in this agent's library."
   }
   ```

2. **No overlap:** A framework ID cannot appear in both `pinned` and `excluded`. Return 422:
   ```json
   {
     "error": "conflicting_overrides",
     "conflicting_ids": ["framework-id"],
     "message": "A framework cannot be both pinned and excluded."
   }
   ```

3. **`disabled` supersedes:** When `disabled: true`, the `pinned` and `excluded` arrays are retained in storage but have no effect. They take effect again when `disabled` is set back to `false`.

4. **Max pinned:** Maximum 3 pinned frameworks. More than 3 would inject excessive context into L7. Return 422 if exceeded.

5. **Ownership check:** The user must have access to the AgentDefinition (owner or public agent) and must be the owner of the AgentInstance (`user_id = auth.uid()`). Return 403 otherwise.

### 11.4 Pipeline Integration

The framework selection pipeline (generation-engine-spec.md §2.3) checks overrides before running:

```python
overrides = agent_instance.framework_overrides

if overrides.get("disabled"):
    # Skip L7 entirely
    return None

if overrides.get("pinned"):
    # Fetch pinned frameworks directly, skip pipeline
    return fetch_frameworks_by_ids(overrides["pinned"])

# Normal pipeline with exclusions
excluded_ids = set(overrides.get("excluded", []))
candidates = get_trigger_embeddings(agent_id, exclude=excluded_ids)
# ... run similarity search, boost, gate
```

### 11.5 UI Integration

**Framework Library tab (Agent Profile page):**
- Each framework row has a pin/exclude toggle (icon buttons).
- A "Disable all frameworks" toggle at the top of the library.
- Current override state is loaded from the user's AgentInstance.
- Changes are saved via `PATCH /api/v1/agents/:id/instance`.

**Chat UI (optional indicator):**
- When an agent has pinned frameworks, show a small indicator in the agent badge: "Pinned: Framework Name."
- When frameworks are disabled, show: "Frameworks disabled."

---

## 12. Open Questions

_None at time of writing. All major decisions locked in MEMORY.md._

---

## Done When

- [ ] Spec reviewed and approved by Brandon
- [ ] Gilfoyle Sprint 4 ADR ticket created and linked to this spec
