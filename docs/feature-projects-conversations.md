# Feature Spec — Projects + Conversations

**Status:** Draft
**Author:** Jared
**Date:** 2026-03-22
**Ticket:** KIN-241
**Audience:** Dinesh (interaction flows), Big Head (workflow pipelines), Gilfoyle (architecture review)

---

## Overview

This spec covers the Projects feature and the Conversations feature as a unified unit. They are deeply coupled: a Project is the organizing container, and Conversations are its primary interaction artifact. Implementing one without the other produces a dead surface.

**Blocked by this spec:** KIN-241 unblocks both Dinesh and Big Head for Sprint 2. Neither should start implementation until this spec is approved.

---

## Referenced Documents

- DB schema: `docs/db-schema-spec.md` — tables: `projects`, `conversations`, `messages`, `conversation_summaries`, `active_memory_entries`
- RAG architecture: `docs/rag-architecture.md` — KB attachment and retrieval behavior
- Domain model: `docs/domain-model.md` — entity definitions, context stack, relationships
- PRD: `docs/prd.md §4` (Projects) and `§5` (Conversations)

---

## Part 1 — Projects

### What It Is

A Project is an in-app workspace for a specific initiative. It belongs to one Company, holds user-authored instructions, owns an Active Memory, owns a Knowledge Base, and groups all related Conversations. Projects are the primary working context for most user sessions.

### Data Model

Uses the `projects` table (see `db-schema-spec.md §4`). Key columns:

- `name` — required
- `company_id` — set to the user's active company at creation; editable afterward
- `user_id` — denormalized for RLS; must stay in sync with the owning company's user
- `instructions` — optional free-form text, ~500 tokens max; Layer 3 of the context stack

No `deleted_at` column — projects are hard-deleted in MVP (conversations are soft-deleted separately).

### Behaviors

#### Creation

1. User creates a project from the project list or company view.
2. `company_id` is auto-set to `users.active_company_id` at the time of creation.
3. A `knowledge_bases` row is created automatically, linked to this project (`project_id` set, `agent_definition_id` null). The project always has a KB — it starts empty.
4. Project is immediately navigable. Instructions are optional — the project works without them.

#### Instructions

- User-authored, static text. Never auto-updated by the AI.
- Saved as `projects.instructions`.
- No character limit enforced at the DB layer, but the UI should soft-warn at ~500 tokens (~2000 characters) since this is the intended max for context injection.
- Instructions are always injected as Layer 3 of the 9-layer context stack whenever the project is active.

#### Company Reassignment

- User can change the project's company to any of their other companies.
- On reassignment: all conversations, Active Memory entries, and the attached KB (and all its documents/chunks) transfer to the new company. This is a cascade on `company_id` — nothing is orphaned or deleted.
- The `user_id` on `projects`, `conversations`, and `active_memory_entries` does not change on reassignment (it remains the same user). Only `company_id` updates.

#### Project List View

- Shows all projects under the active company.
- Grouped under the company in the sidebar or a project index page.
- Displays project name, last activity (last message timestamp from most recent conversation, if any).

#### Editing and Deletion

- User can rename a project and edit its instructions at any time.
- Project deletion: hard-delete in MVP. Cascades to conversations (and their messages), active_memory_entries, and knowledge_bases (which cascades to documents and chunks). User should see a confirmation warning noting the action is permanent.

### Context Stack Contribution

| Layer | Source | Size |
|---|---|---|
| Layer 3 | `projects.instructions` | ~500 tokens |
| Layer 4 | Project Active Memory (`active_memory_entries` scoped by `project_id`) | ≤1000 tokens |
| Layer 8 | Project KB RAG chunks | Up to `RAG_MAX_TOKENS` (15% of model context window, floor 2048) |

Layers 3 and 4 are always injected when a project conversation is active. Layer 8 is query-dependent (retrieved at generation time).

### User Stories

- As a user, I want to create a project under my active company so I can organize my work by initiative.
- As a user, I want to write project instructions that shape every AI response so I can set tone, constraints, and approach once and not repeat it.
- As a user, I want to change a project's company assignment so I can fix mistakes or reorganize.
- As a user, I want to see all my projects for the active company in one place so I can navigate quickly.

---

## Part 2 — Conversations

### What It Is

A Conversation is the primary interaction unit: a threaded sequence of user and AI messages. Conversations belong to a Company and optionally to a Project. They are the entry point for all AI generation in Kinetic.

### Two Conversation Scopes

| Scope | `project_id` | Context injected | When to use |
|---|---|---|---|
| **Project conversation** | Set | Full 9-layer stack: user profile + company + project instructions + project active memory + agent (if invoked) + project KB RAG | Working on a specific initiative |
| **Company conversation** | Null | Layers 1–2 (user profile + active company) + agent layers if invoked. No project context. | General company-level thinking, cross-project questions |

Both types appear in the sidebar. Project conversations are grouped under their project. Company conversations appear in a "General" group under the active company header.

### Data Model

Uses the `conversations` table (see `db-schema-spec.md §5`). Key columns:

- `user_id` — owner
- `company_id` — always set; inherited from the active company at creation
- `project_id` — nullable; null = company-level conversation
- `title` — auto-generated from the first message; user can rename
- `active_agent_id` — FK to `agent_definitions`; nullable; the currently invoked agent
- `deleted_at` — soft-delete; null when visible

Uses the `messages` table (see `db-schema-spec.md §6`). Key columns:

- `conversation_id` — parent conversation
- `role` — `user` or `assistant` (system messages not displayed in UI)
- `content` — message text
- `agent_definition_id` — which agent generated this message (nullable; null = no agent)
- `model` — model string used for generation
- `sequence` — 0-indexed ordering within the conversation

Uses the `conversation_summaries` table (see `db-schema-spec.md §7`) for rolling compression of older messages. Append-only.

### Behaviors

#### Creating a Conversation

1. User starts a new conversation from the sidebar, from a project view, or from the company-level "General" area.
2. When created from within a project: `project_id` is set to that project's ID.
3. When created from the company-level area: `project_id` is null.
4. `company_id` is always set to the user's `active_company_id` at creation time.
5. `title` is null until the first message is sent — the title is auto-generated from the first user message (truncated to ~50 characters, or a short AI-generated summary of the first message).
6. Conversation appears in the sidebar immediately on creation (or on first message send — see Open Questions).

#### Sending Messages

1. User types a message and sends.
2. Backend assembles the context stack based on conversation scope (see Context Stack section below).
3. Generation streams back via SSE. The frontend proxies SSE through a Next.js server route to inject JWT (EventSource limitation).
4. Both the user message and AI response are written to `messages` with sequential `sequence` values.
5. `conversations.updated_at` is updated to now after each message pair.
6. `conversations.active_agent_id` is updated if the agent was switched before this message.

#### Title Auto-Generation

- After the first user message is sent, generate a short title for the conversation.
- Strategy: use the first user message text, truncated to ~60 characters (trim at word boundary). If the message is very short (<10 words), use it verbatim. If the message is long, truncate at the last full word before 60 chars and append "…".
- No LLM call for title generation in MVP — string truncation only. LLM-generated titles are a V1 enhancement.
- User can rename the conversation at any time (inline edit in sidebar).

#### Agent Invocation

Agent state lives on the conversation via `active_agent_id`. The agent side panel allows the user to toggle an agent on or off.

| Action | What happens |
|---|---|
| Activate agent | `conversations.active_agent_id` set to the selected agent's ID. Layers 5–7 (agent system prompt, agent active memory, framework) and Layer 9 (agent KB RAG) are added to the context stack for all subsequent messages in this conversation. |
| Deactivate agent | `conversations.active_agent_id` set to null. Agent layers removed from context stack for subsequent messages. |
| Switch agent | `active_agent_id` updated to new agent. Full conversation history (including prior agent messages) stays visible. New agent sees the full history. Messages are tagged by `agent_definition_id` so the UI can render visual markers at agent switch points. |

Agent switches are tracked at the message level via `messages.agent_definition_id`. The UI renders a visual divider or badge in the conversation thread when `agent_definition_id` changes between consecutive assistant messages.

#### Conversation History in Prompt

Recent messages are included in the prompt between deterministic context layers (1–7) and the current user message. This is the conversational memory within a session.

**Rolling summary compression:** As a conversation grows long, older messages are compressed into a rolling summary to manage the context window. The `conversation_summaries` table stores these. The most recent summary + remaining uncompressed messages are used; older messages beyond the summary are dropped from context.

- **Compression trigger:** When the token count of all messages in context exceeds a threshold (Gilfoyle to specify exact threshold during architecture pass).
- **Compression model:** Uses the user's BYOK key and default model (or first available).
- **Compression fallback:** If the BYOK key is unavailable, truncate oldest messages without summarization. Notify the user inline with a banner: "Some earlier messages were truncated to fit context. [Add an API key to enable compression.]"
- Compression does not affect `messages` rows — it only populates `conversation_summaries`. Message history is always fully accessible by scrolling.

#### Periodic Memory Proposals

Every 10 messages in a conversation (fixed at `MEMORY_PROPOSAL_INTERVAL = 10`), the system generates a batch of Active Memory proposals for the user to review. These are written to `memory_proposals` (see `db-schema-spec.md §17`) and surfaced in the UI as a review prompt.

- Trigger: `(message count) mod 10 = 0` for assistant messages (not user messages).
- Scope: proposals target the project-level Active Memory if this is a project conversation, or the agent instance-level Active Memory if an agent is invoked. Both can be proposed in the same batch.
- The proposals are queued, not automatically applied. User reviews and approves/rejects each individually.
- If a user hasn't reviewed prior proposals, new proposals are appended to the pending queue. The queue badge in the UI shows the total pending count.

#### Soft-Delete

- User can delete a conversation from the sidebar context menu.
- Soft-delete: `conversations.deleted_at` is set to now. The conversation disappears from the sidebar.
- Hard-delete: never in MVP. The row is retained in the DB.
- Active Memory entries sourced from a soft-deleted conversation (`active_memory_entries.source_conversation_id`) are not affected — they persist independently.
- Messages in soft-deleted conversations are not deleted. No cleanup needed — the data is retained for potential recovery.

### Context Stack Assembly (per generation)

The full context stack assembled at generation time, depending on conversation scope:

#### Project Conversation

| Layer | Source | Notes |
|---|---|---|
| 1 | `users.bio` | Always present |
| 2 | `companies.description` | Active company |
| 3 | `projects.instructions` | Always present if set |
| 4 | Project Active Memory | `active_memory_entries` WHERE `project_id = [this project]` |
| 5 | Agent system prompt | `agent_definitions.instructions` — only if `active_agent_id` is set |
| 6 | Agent active memory | `active_memory_entries` WHERE `agent_instance_id = [user's instance]` — only if agent invoked |
| 7 | Matched framework | Framework selection pipeline result — only if agent invoked and a framework matches |
| (Conversation history) | `messages` + `conversation_summaries` | Recent messages; older messages compressed |
| 8 | Project KB RAG | `knowledge_base_chunks` WHERE `project_id = [this project]` |
| 9 | Agent KB RAG | `knowledge_base_chunks` WHERE `agent_definition_id = [active agent]` — only if agent invoked and agent has KB |
| — | Current user message | The message being sent |

#### Company Conversation

| Layer | Source | Notes |
|---|---|---|
| 1 | `users.bio` | Always present |
| 2 | `companies.description` | Active company |
| 5 | Agent system prompt | Only if `active_agent_id` is set |
| 6 | Agent active memory | Only if agent invoked |
| 7 | Matched framework | Only if agent invoked |
| (Conversation history) | `messages` + `conversation_summaries` | |
| 9 | Agent KB RAG | Only if agent invoked and agent has KB |
| — | Current user message | |

Layers 3, 4, and 8 (project context) are absent in company conversations.

### Sidebar Layout

The left sidebar is the primary navigation surface for conversations.

**Structure:**

```
[Active Company Name]
  General
    [Company Conversation 1]
    [Company Conversation 2]
  + New general conversation

  [Project A Name]
    [Conversation 1]
    [Conversation 2]
  + New conversation in Project A

  [Project B Name]
    [Conversation 1]
  + New conversation in Project B
```

- Projects are listed under the active company. Changing the active company updates the sidebar to show that company's projects and conversations.
- Within each project group, conversations are sorted by `updated_at` descending (most recent first).
- Company conversations are listed under "General" with the same sort.
- Soft-deleted conversations are hidden from the sidebar.
- On initial load, the most recent conversation (across all projects) is selected.

### Conversation Management Actions

| Action | Trigger | Behavior |
|---|---|---|
| Rename | Inline edit in sidebar or conversation header | Updates `conversations.title` |
| Delete | Context menu in sidebar | Sets `conversations.deleted_at = now()`; removes from sidebar |
| New conversation | "+ New conversation" button | Creates a new conversation row with the appropriate `project_id` scope |
| Switch conversation | Click in sidebar | Loads the selected conversation's messages and restores agent state |

### User Stories

- As a user, I want to see my past conversations in the sidebar so I can pick up where I left off.
- As a user, I want to start a new conversation in a project and have the AI already know my project context without me explaining it.
- As a user, I want to start a company-level conversation when I'm not working on a specific project so I can think through company-wide questions.
- As a user, I want the AI to remember what we discussed earlier in the conversation, even if the conversation is long.
- As a user, I want to rename a conversation so I can find it later.
- As a user, I want to delete a conversation I no longer need so my sidebar stays clean.
- As a user, I want to invoke an agent in my conversation and see clearly which agent is responding.
- As a user, I want to review AI-proposed memory updates so I can keep my Active Memory accurate without managing it manually.

---

## Part 3 — Implementation Guidance (for Dinesh and Big Head)

### Dinesh — Interaction Flows

Dinesh owns the **frontend interactions and API endpoints** for this feature. Scope:

1. **Project CRUD endpoints** — create, read (list + detail), update (name, instructions, company), delete
2. **Conversation CRUD endpoints** — create, list (by project and company), soft-delete, rename
3. **Message send endpoint** — accepts user message, triggers context stack assembly + generation, streams response via SSE
4. **Context stack assembly** — builds the ordered prompt from the database for each generation; consults `conversations.project_id` and `conversations.active_agent_id` to determine which layers to include
5. **Agent invocation endpoints** — toggle agent on/off, switch agent; update `conversations.active_agent_id`
6. **Title auto-generation** — string-truncation logic triggered after first message
7. **Sidebar rendering** — grouped project/conversation list, sorted by `updated_at` desc, filtered for `deleted_at IS NULL`

### Big Head — Workflow Pipelines

Big Head owns the **background workflow pipelines** that run during or after conversations. Scope:

1. **Rolling summary compression** — background task triggered when message token count exceeds threshold; writes to `conversation_summaries`; handles BYOK key failure with truncation fallback
2. **Periodic memory proposal generation** — triggered every 10 assistant messages; generates proposed `active_memory_entries` content via LLM; writes pending rows to `memory_proposals`; surfaces proposals to the user for review
3. **Memory proposal review endpoints** — accept/reject individual proposals; on accept, writes to `active_memory_entries` (enforcing token cap); on reject, marks `proposal_status = 'rejected'`

### Cross-Cutting Notes

- **Token cap enforcement:** Active Memory cap (≤1000 tokens for project, ≤500 for agent instance) is enforced at the application layer, not the DB. Before writing a new `active_memory_entries` row, sum token counts of existing entries for the scope and reject if adding the new entry would exceed the cap. Return a clear error to the user: "Active Memory is full. Remove some entries before adding new ones."
- **Soft-delete filter:** All queries against `conversations` must include `WHERE deleted_at IS NULL` unless explicitly in a recovery context.
- **RLS scoping:** `conversations` and `messages` rows are scoped to `auth.uid() = user_id`. The `messages` table uses a join-based policy (ownership checked via parent conversation). See `db-schema-spec.md` for full RLS definitions.
- **SSE proxy:** The frontend proxies SSE through a Next.js server route to inject JWT. The backend accepts the token via query param or header. See MEMORY.md 2026-03-21 entry on SSE auth.
- **Agent switch markers:** When `messages.agent_definition_id` changes between consecutive assistant messages in a conversation, the UI must render a visual divider indicating the agent switch. This is a UI-layer concern — no extra DB column needed.

---

## Open Questions

1. **Conversation creation timing:** Does a new conversation row get created the moment the user clicks "+ New conversation," or only when the first message is sent? Creating on click is simpler for sidebar UX (the conversation appears immediately with a placeholder title) but creates empty rows if the user cancels. Creating on first send avoids empty rows but requires more client-side state management. **Needs Brandon's call.**

2. **Compression trigger threshold:** At what message token count does rolling summary compression trigger? Gilfoyle to determine during architecture pass. Jared's assumption for now: triggers when messages in context exceed ~50% of the model's context window (after accounting for layers 1–9).

3. **Company conversation Active Memory:** Company conversations (no project) don't have a project active memory. Should there be company-level Active Memory (scoped to the company, not a project)? The current `active_memory_entries` schema only supports `project_id` or `agent_instance_id` as parents — there is no `company_id` scope. This is a gap if company conversations are expected to compound memory over time. **Needs Brandon's call** before Dinesh or Big Head starts on company conversation memory.

4. **Conversation sidebar empty state:** What does the sidebar show when a user has no conversations yet (new user, new project)? Needs UX copy / empty state design. Not a blocker for implementation but needed before review.

---

## Decisions Needed

| # | Question | Who decides | Impact |
|---|---|---|---|
| 1 | Conversation creation timing (on click vs. on first send) | Brandon | Dinesh — affects create endpoint and client-side state |
| 2 | Company-level Active Memory scope | Brandon | Big Head — `active_memory_entries` schema may need a new nullable column if approved |

---

## Assumptions (Locked — Do Not Revisit)

The following are confirmed decisions from `MEMORY.md`. Do not re-open without a new Brandon decision.

| Assumption | Source |
|---|---|
| Two conversation scopes: project and company | MEMORY.md 2026-03-21 |
| Conversation soft-delete in MVP; no hard-delete | MEMORY.md 2026-03-21 |
| Agent invocation: one agent at a time; side panel toggle | MEMORY.md 2026-03-21 |
| Agent switch preserves full conversation history; messages tagged with `agent_definition_id` | MEMORY.md 2026-03-21 |
| Active Memory write: triple-trigger (user-initiated, AI-proposed at conversation end, periodic every 10 messages) | MEMORY.md 2026-03-21 |
| Active Memory entries are individual rows with `created_at` + `source_conversation_id` | MEMORY.md 2026-03-21 |
| Periodic memory proposal interval: fixed at every 10 messages, not user-configurable in MVP | MEMORY.md 2026-03-21 |
| Conversation compression fallback: truncate oldest messages on BYOK key failure, notify user inline | MEMORY.md 2026-03-21 |
| Company ↔ Project: auto-set to active company at creation, changeable later; everything moves on reassignment | MEMORY.md 2026-03-21 |
| SSE auth: frontend proxies through Next.js server route to inject JWT | MEMORY.md 2026-03-21 |
| Title auto-generated from first message; user can rename | MEMORY.md 2026-03-21 |
