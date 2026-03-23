# Kinetic MVP — Product Requirements Document

**Status:** Approved
**Author:** Jared
**Date:** 2026-03-21
**Approved:** 2026-03-21
**Project:** Kinetic

---

## Problem Statement

Knowledge workers — especially consultants and founders working across multiple clients — hit the same wall with every AI tool: cold-start. Every session begins from zero. The AI doesn't know who you are, what you're working on, what you've already decided, or how you think. Users waste time re-explaining context, get generic outputs that miss their actual constraints, and lose institutional knowledge between sessions. The workaround is copy-pasting context into prompts manually, which doesn't scale and degrades as projects grow in complexity.

Kinetic solves this by maintaining persistent, layered context — user profile, company, project state, active memory that compounds across sessions, and custom AI agents — and assembling it automatically into every generation. The result is AI that reasons like a well-briefed collaborator from message one.

---

## Proposed Solution

Kinetic is a context-rich AI workspace where every generation is pre-loaded with who you are, what company you're operating in, what project you're focused on, and the perspective of AI agents you've built. Users create custom agents grounded in thought leader corpora (uploaded writing → auto-generated system prompt → curated framework library). A 9-layer context stack assembles the right context per query. Users bring their own API keys and choose their model per query.

---

## Target Users

**Primary:** Consultants and founders working across multiple clients or companies who need AI that understands their full operating context.

**Secondary:** Knowledge workers broadly (executives, PMs, analysts, strategists) who do judgment-heavy work and find generic AI too shallow to be consistently useful.

---

## Success Metrics

| Metric | Type | Target | Timeframe |
|---|---|---|---|
| Users who create at least 1 agent and 1 project | Activation | 60% of signups | First 30 days |
| Return sessions per user per week | Engagement (leading) | ≥3 sessions/week | By week 4 |
| Active Memory entries created per user | Context compounding (leading) | ≥5 entries after 2 weeks | First 14 days |
| Users who upload at least 1 KB document | Feature adoption | 40% of active users | First 30 days |
| NPS among weekly-active users | Outcome (lagging) | ≥40 | 60 days post-launch |
| Churn rate (weekly-active → inactive) | Outcome (lagging) | <15% month-over-month | Ongoing |

---

## MVP Scope

**In scope:** Everything specified in this document. This is the minimum product that ships first.

**Out of scope (post-MVP, still V1 roadmap):**

| Feature | Why deferred |
|---|---|
| Thought Stream (pgvector ambient capture) | Active Memory covers the core memory job. Thought Stream adds complexity without unlocking a must-have user job in MVP. |
| Contacts entity | Requires Thought Stream for full value (relationship context surfacing). |
| Cross-company retrieval opt-in | Depends on Thought Stream. |
| Agent `shared` visibility tier | Private/public covers MVP use cases. Shared adds permissions complexity. |
| Agent permissions (owner/editor/invoker) | Not needed with private/public toggle. Required when `shared` is added. |
| Agent transparency (transparent/opaque) | All agents transparent in MVP. Needed for marketplace IP protection. |
| Pre-meeting auto-briefings | Requires calendar integration. |
| Email-based thought capture | Requires email integration. |
| Meeting transcript auto-extraction | Requires integration pipeline. |
| Agent marketplace (payment layer) | Requires visibility tiers, transparency, payments infrastructure. |

**Out of V1 entirely:** Real-time collaboration, agent autonomy/scheduling, third-party integrations (email, calendar, Notion, Slack), desktop file sync, agent-to-agent interaction, agent marketplace payments.

---

## Feature Areas

### 1. Auth & Admin

**Registration:** Email-only. User provides email → account auto-created. No approval flow, invite codes, or password setup. Login via magic link (email) or OAuth (Google). No password management in MVP.

**User disable rule:** Admin must transfer ownership of all public agents before disabling a user account. The admin panel enforces this — the disable action is blocked until all public agents owned by the user are either transferred to another user or set to private. This prevents orphaned public agents that no one can edit.

**Admin section tabs:**

| Tab | Purpose |
|---|---|
| Users | List users, disable/enable accounts. Two roles only: admin and user. |
| LLM Models | Manage the curated library of available models across three categories: generation, embedding, and reranking. |
| RAG Debug | View retrieval traces for recent queries — which chunks were retrieved, scores, reranking results, and gating decisions. Admin-only diagnostic tool for answering "why did the AI say that?" Not user-facing. |

**LLM Models tab:** Admins maintain a model library that controls which LLM options appear to users throughout the product. Models are organized into three categories:

| Category | MVP exposure | Used for |
|---|---|---|
| `generation` | Yes — surfaced in per-query model selector and user default model setting | Text generation for all user queries |
| `embedding` | Not yet — added when embedding pipeline is admin-configurable | Chunk and query embedding in the RAG pipeline |
| `reranking` | Not yet — added when reranker is admin-configurable | LLM reranking step in the RAG pipeline |

In MVP, users only see `generation` models in the model selector. The `embedding` and `reranking` categories are defined in the data model now to avoid a migration later, but they have no user-facing exposure until those pipeline stages are made admin-configurable.

**Architectural notes for implementers:**

- **In-memory cache with DB persistence.** Model assignments load into memory at startup for fast reads. Writes hit both DB and cache simultaneously. Fallback chain: `DB → env var → hardcoded default` — the app stays up if the DB is unavailable.
- **Client-side model library with pub/sub.** The available model list is cached client-side (localStorage) with a listener pattern. Adding a model in the admin UI instantly updates model dropdowns elsewhere in the product without an API round-trip.
- **Per-entity override.** Individual entities (agents, etc.) can override the global model assignment for their specific use case. Resolution order: `entity override → global assignment`.
- **Admin-only API.** Both management endpoints require admin auth. Every change is audit-logged with the acting user ID.

**User stories:**

- As a new user, I want to sign up with just my email so I can start using Kinetic immediately without a lengthy registration process.
- As an admin, I want to see all registered users and disable accounts so I can manage access.
- As an admin, I want to manage the list of available generation models so I can control which LLMs users can select from.

---

### 2. User Profile

**Fields:**

| Field | Type | Notes |
|---|---|---|
| Name | Text | Required |
| Short bio | Text, 500–1000 chars | Optional. Injected into every prompt as Layer 1. |
| API keys | Encrypted key-value | Anthropic, OpenAI, Google, Groq. At least one required for generation. |
| Default model | Selector | Set from available models based on configured API keys. |

**Linked Upload (auto-fill):** User can upload a document (LinkedIn PDF, resume, bio — `.pdf`, `.docx`, `.doc`, `.txt`, max 10MB) to auto-populate Name and Short Bio. The system extracts fields via LLM, presents them for review, and the user edits before saving. The uploaded file is discarded after extraction — it is not added to any Knowledge Base. See `docs/feature-linked-upload.md` for full extraction logic and edge cases.

**Linked Upload LLM key policy:** Linked upload extraction uses the user's BYOK key. The system selects a generation model matching the user's configured keys (using the user's default model, or the first available model if no default is set). **Linked upload is only available after the user has configured at least one API key.** Before key setup, the upload button is hidden or disabled with a tooltip: "Add an API key to enable auto-fill." This applies to all three linked upload surfaces (User Profile, Company Profile, Agent Profile).

**User stories:**

- As a user, I want to upload my LinkedIn PDF and have my profile auto-filled so I don't have to write my bio from scratch.
- As a user, I want to manage my API keys in one place so I can use different LLM providers.
- As a user, I want to set a default model so I don't have to pick one every time I send a message.

---

### 3. Companies

**Fields:**

| Field | Type | Notes |
|---|---|---|
| Name | Text | Required |
| Short description | Text, 500–1000 chars | Optional. Injected into every prompt as Layer 2 when this company is active. |

Users can create multiple companies. One company is active at a time; the user switches between them via a company switcher in the main UI. Active company context is injected into every prompt.

**Linked Upload (auto-fill):** Same pattern as User Profile. Upload a business plan, pitch deck, or one-pager (`.pdf`, `.docx`, `.doc`, `.pptx`, `.ppt`, `.txt`, `.md`, max 25MB) to auto-populate Company Name and Short Description. File discarded after extraction. See `docs/feature-linked-upload.md`.

**User stories:**

- As a consultant, I want to create separate company profiles for each client so my AI knows which client context to use.
- As a user, I want to switch active companies quickly so I can context-switch between clients without losing my personal profile or agent library.
- As a user, I want to upload a business plan and have the company profile auto-filled so I don't type everything manually.

---

### 4. Projects

A project is an in-app workspace for a specific initiative. Projects belong to a company.

**Creation:** When a user creates a project, it is automatically assigned to the currently active company. The company assignment can be changed later.

**Fields and components:**

| Component | Type | Behavior |
|---|---|---|
| Name | Text | Required |
| Company | FK (auto-set) | Auto-set to active company at creation. Editable afterward. |
| Instructions | Free-form text, ~500 tokens | Optional. Static, user-authored rules for how to work in this project. Always injected as Layer 3. Never auto-updated. |
| Active Memory | Structured text, ≤1000 tokens | AI-curated dynamic facts. Always injected as Layer 4. See §9 Active Memory. |
| Knowledge Base | Document collection | Upload docs for RAG retrieval. See §7 Knowledge Base. |
| Conversations | List | Past conversations shown in a left column. See §5 Conversations. |

**User stories:**

- As a user, I want to create a project under my active company so I can organize my work by initiative.
- As a user, I want to write project instructions that shape every AI response in this project so I can set tone, constraints, and approach once.
- As a user, I want to change a project's company assignment so I can fix mistakes or reorganize.

---

### 5. Conversations

Conversations are the core interaction unit. A conversation is a threaded sequence of messages between the user and the AI.

**Scope:** Conversations can exist at two levels:

| Level | Context injected | When to use |
|---|---|---|
| **Project conversation** | Full 9-layer stack (user + company + project + agent if invoked) | Working on a specific initiative |
| **Company conversation** | Layers 1–2 (user profile + active company) + agent layers if invoked. No project instructions, project active memory, or project KB. | General company-level thinking, not tied to a project |

Conversations are listed in a left column (Claude-style chat history), grouped by project. Company-level conversations appear in a separate "General" group under the active company.

**Conversation entity:**

| Attribute | Type | Notes |
|---|---|---|
| Title | Text | Auto-generated from first message; user can rename |
| Project | FK (nullable) | Null for company-level conversations |
| Company | FK | Always set — inherited from active company |
| Messages | Ordered list | User and AI messages, timestamped |
| Agent invoked | FK to AgentDefinition (nullable) | The agent active in this conversation, if any |
| Created at | Timestamp | |
| Updated at | Timestamp | Last message time |

**Conversation management:** Users can rename conversations and soft-delete them. Soft-delete hides the conversation from the sidebar but retains it in the database. No hard-delete in MVP. Active Memory entries sourced from a soft-deleted conversation are not affected — they persist independently.

**User stories:**

- As a user, I want to see my past conversations in a sidebar so I can pick up where I left off.
- As a user, I want to start a company-level conversation when I'm not working on a specific project so I can think through company-wide questions with my full company context.
- As a user, I want to rename conversations so I can find them later.
- As a user, I want to delete a conversation I no longer need so my sidebar stays clean.

---

### 6. Agents (AgentDefinition / AgentInstance)

Agents are custom AI personas the user builds and invokes. The architecture splits into two entities:

**AgentDefinition** — the shared blueprint (what the agent *is*):

| Component | Type | Notes |
|---|---|---|
| Name | Text | Required. e.g., "Strategist", "Devil's Advocate", "Nate Jones" |
| Instructions | Free-form text, ~500 tokens | The system prompt — persona definition. Always injected as Layer 5 when invoked. |
| Knowledge Base | Document collection | Optional. For thought leader agents or domain-specific grounding. RAG-retrieved as Layer 9. |
| Framework Library | Structured entities | Reasoning tools. Uploaded as JSON. Classifier-selected as Layer 7. See §8 Framework Library. |
| Visibility | Toggle | `private` (default, owner only) or `public` (any Kinetic user) |
| Type | Enum | `custom` (user-authored) or `thought_leader` (corpus-seeded) |
| MCP connection | URL | Per-user connector URL for external AI clients. See §11 MCP. |

**AgentInstance** — the per-user runtime state (the agent's memory *of you*):

| Component | Type | Notes |
|---|---|---|
| Active Memory | Structured text, ≤500 tokens | AI-curated facts about this user's relationship with the agent. Always injected as Layer 6 when agent is invoked. |
| Framework overrides | Config | Pinned or excluded frameworks for this user's sessions. |

An AgentInstance is created automatically the first time a user invokes an agent. For private agents, the owner's instance is created when the agent is created.

**Agent corpus scope:** One corpus per agent. A thought leader agent is grounded in one person's writing/transcripts. Users who want a blended perspective invoke two agents in separate conversations.

**One agent at a time (MVP).** The user can invoke one agent per conversation. Multiple simultaneous agents are planned for post-MVP.

**Agent invocation UX:** A side panel or agent selector in the chat UI allows the user to toggle an agent on for the current conversation. When an agent is active, the UI clearly indicates which agent is responding (agent name, visual indicator). The user can deactivate the agent or switch to a different agent mid-conversation.

| Action | Behavior |
|---|---|
| Activate agent | Agent's system prompt, active memory, framework pipeline, and KB are added to context stack (Layers 5–7, 9) |
| Deactivate agent | Layers 5–7, 9 removed from context stack. Conversation continues with base context only. |
| Switch agent | Previous agent deactivated, new agent activated. Both agents' instances retain their own active memory independently. Full conversation history (including prior agent's responses) remains visible to the new agent. |

**Thought Leader Agent Flow:**

1. Owner uploads thought leader's corpus to the agent's Knowledge Base.
2. System auto-generates a system prompt from the corpus content.
3. Owner reviews and edits the system prompt.
4. Owner extracts frameworks from the corpus using an external script (outside Kinetic).
5. Owner uploads the extracted frameworks as a structured JSON file into the agent's Framework Library.
6. Owner reviews, edits, adds, or deletes individual frameworks.
7. Owner sets visibility (private/public).

**Linked Upload (auto-fill):** Same pattern as User Profile and Company Profile. Upload a thought leader's writing sample, transcript, interview, article, or book excerpt (`.pdf`, `.docx`, `.doc`, `.txt`, `.md`, max 25MB) to auto-populate Agent Name and Instructions (system prompt). The system analyzes the writing for thinking style, communication patterns, core principles, and areas of expertise, then generates a system prompt that instructs the LLM to reason like this person. File discarded after extraction — if the user wants the document for RAG, they upload it separately to the agent's KB. See `docs/feature-linked-upload.md`.

**Agent Profile page includes:**

- Agent Name and Instructions (system prompt) — view, edit, and linked upload to auto-fill from a writing sample
- Knowledge Base — browse documents, upload new docs, manage folders and tags
- Framework Library — browse, edit, add, delete individual frameworks
- Visibility toggle

**User stories:**

- As a user, I want to create a custom agent with my own system prompt so I can get AI responses shaped by a specific persona.
- As a user, I want to upload a thought leader's writing and have a system prompt auto-generated so I can build an agent that thinks like them without writing the prompt from scratch.
- As a user, I want to invoke an agent in my conversation and clearly see that I'm now talking to that agent so I know which perspective is shaping the response.
- As a user, I want to switch agents mid-conversation so I can get different perspectives on the same problem.
- As a user, I want to make an agent public so other Kinetic users can invoke it and benefit from the perspective I've built.

---

### 7. Knowledge Base & RAG

A Knowledge Base is a structured, searchable document collection attached to a Project or an AgentDefinition. It is the RAG layer.

**Upload:** User uploads documents to a KB. Supported formats: `.pdf`, `.docx`, `.doc`, `.pptx`, `.ppt`, `.txt`, `.md`, `.csv`, `.xlsx`, `.xls`, `.rtf`, `.jsonl`. Max file size: **25 MB per document** (mirrors FounderPanel). Ingestion token limit: **1,000,000 tokens per document** — documents exceeding this are rejected with an error. No per-KB or per-user storage quota in MVP (constrained by Supabase service limits). Documents are processed asynchronously through the MVP ingestion pipeline: text extraction → optional document-level summary → fixed-size chunking (~500 tokens, ~50 token overlap) → embedding (`text-embedding-3-large`, platform-owned key) → pgvector indexing.

**Processing status:** Each document shows its status in the UI: `pending → extracting → chunking → embedding → completed`. Failures are tracked per stage with error message and retry option.

**Ingestion retry & error handling:** Each document tracks its current processing stage, error stage (which step failed), error message, and retry count. On failure, the system auto-retries up to 3 times with exponential backoff. After 3 failures, the document is marked `failed` and the user sees a "Retry" button in the UI to manually re-trigger ingestion from the failed stage (not from scratch). Admin can also view failed documents across all users in the admin panel.

**Organization:** Knowledge Bases support user-created folders and tags. AI auto-suggests tags and metadata on upload; user can edit.

**Retrieval (MVP — simplified, zero LLM calls):** At query time, the RAG pipeline runs independently per active scope (Project KB as Layer 8, Agent KB as Layer 9). The MVP pipeline: embed user query → vector search (cosine similarity, top-K candidates) → MMR selection (relevance/diversity balance) → similarity threshold (minimum cosine similarity for injection) → citation assembly → context injection. No LLM calls in the retrieval path — zero latency overhead.

**V1 retrieval enhancements (deferred, addable via config flags):** Query rewriting (LLM-generated variants for better recall), full-text search (hybrid vector + FTS for exact term matching), LLM reranking (precision filtering for large KBs), recency scoring (boost recent documents), and 3-tier confidence gating. Each is independently toggleable. See `docs/rag-architecture.md` for the full V1 pipeline spec and all config flags.

**Chunking:** Documents are chunked at ingestion (fixed-size chunks with overlap into discrete rows with individual embeddings). At query time, the pipeline retrieves and injects the top-K most relevant *chunks*, not whole documents. Nothing is re-chunked at injection time. Semantic chunking (split by meaning boundaries) is a V1 enhancement (`SEMANTIC_CHUNKING_ENABLED`).

**Embedding cost model:** Embedding uses a platform-owned OpenAI API key (`text-embedding-3-large`). Users are not charged for embedding. BYOK keys are for generation only. This ensures KB functionality works regardless of which provider keys a user has configured.

See `docs/rag-architecture.md` for full pipeline details, storage schema, configuration parameters, and debug tracing.

**Citations:** Each AI response that uses KB content includes expandable source references: document title, type, section, snippet, and similarity score.

**User stories:**

- As a user, I want to upload documents to my project so the AI can reference them when answering my questions.
- As a user, I want to see which documents the AI used in its response so I can verify the sources.
- As a user, I want to organize documents in folders and tags so I can manage a growing knowledge base.

---

### 8. Framework Library

Frameworks are named, structured reasoning tools attached to an AgentDefinition. They represent reusable thinking patterns extracted from a thought leader's corpus (or user-authored). Frameworks are distinct from KB documents — they are structured entities, not chunks.

**Upload flow (MVP):** Framework extraction runs outside Kinetic via a separate script. The user uploads the resulting structured JSON file into the agent's Framework Library. No in-app extraction pipeline in MVP.

**Upload format:** The JSON file must conform to the following structure (matching the output of the extraction script at `nbj_extractor/`):

```json
{
  "source": "string — identifier for the corpus source",
  "extraction_date": "YYYY-MM-DD",
  "total_posts_scanned": "integer",
  "total_frameworks": "integer",
  "frameworks": [
    {
      "id": "kebab-case-unique-id",
      "name": "Framework Name",
      "type": "distinction | taxonomy | diagnostic | reframe | failure_catalog | evaluation_criteria | procedure",
      "description": "One-sentence description",
      "category": "strategy | org-design | decision-making | ... (open list)",
      "when_to_apply": ["trigger phrase 1", "trigger phrase 2", "..."],
      "principles": ["principle 1", "principle 2", "..."],
      "steps": ["step 1", "step 2", "..."],
      "confidence": "high | medium",
      "source_posts": [{"id": "string", "title": "string", "date": "ISO 8601 datetime"}],
      "date": "ISO 8601 datetime — date of the earliest source post",
      "example_application": "2-3 sentence scenario",
      "related_frameworks": ["other-framework-id", "..."],
      "origin": "extracted | manual"
    }
  ]
}
```

**Upload behavior:** Upload **merges** with existing frameworks. Frameworks with matching `id` values are updated (overwritten); frameworks with new `id` values are added. Existing frameworks not present in the upload are retained (not deleted). To remove a framework, the user deletes it individually via the Framework Library UI.

**Validation:** Each framework in the `frameworks` array is validated individually. Required fields: `id`, `name`, `type` (must be one of the 7 defined types), `description`, `when_to_apply` (must be a non-empty array), `principles` (must be a non-empty array), `confidence`, `origin`. Optional fields: `steps` (omitted when empty), `source_posts`, `date`, `example_application`, `related_frameworks`, `category`. Extra fields not listed here are silently ignored on upload. On partial validation failure, valid frameworks are imported and invalid ones are rejected with per-framework error messages displayed to the user (e.g., "Framework 'my-framework' skipped: missing required field 'when_to_apply'").

**Framework schema:** Each framework includes: `id` (stable unique, kebab-case), `name`, `type` (one of: distinction, taxonomy, diagnostic, reframe, failure_catalog, evaluation_criteria, procedure), `description`, `category` (open list), `when_to_apply` (array of 3–5 trigger phrases), `principles`, `steps` (optional — omitted when empty), `date` (optional — ISO 8601 datetime of earliest source post), `example_application`, `related_frameworks`, `source_posts`, `confidence` (high/medium), `origin` (extracted/manual). See `docs/domain-model.md` § Framework for full schema.

**Selection pipeline (Layer 7):** When a user sends a message with an agent invoked, the 4-step selection pipeline runs: (1) embedding similarity on per-trigger vectors, (2) agent expertise boost and recency boost for tie-breaking, (3) LLM reranker (Haiku) on top-5 for precision, (4) inject winner whole. If no match exceeds the confidence threshold, no framework is injected. The framework reranker is the only per-query LLM call in the MVP pipeline (~50 output tokens via Haiku, platform-owned key). This is a precision classifier on a small candidate set — not comparable to the bulk LLM calls cut from the RAG pipeline.

**Recency scoring:** Framework recency (based on `created_at` — when the framework was added to the library) is factored into step 2 as a tie-breaking signal alongside the agent expertise boost. More recently added frameworks score slightly higher when embedding similarity is otherwise close. This ensures that when a user refines or adds new frameworks over time, the updated thinking is preferred over older entries. The recency weight is configurable and applies only when top candidates are within a narrow similarity band; it does not override a significantly stronger semantic match.

See `docs/domain-model.md` § Framework Selection Architecture.

**User overrides (via AgentInstance):** Pin a framework (force injection, skip selection), exclude frameworks (remove from candidate pool), or disable framework injection entirely for the session.

**User stories:**

- As a user, I want to upload a framework JSON file to my agent so its reasoning is grounded in structured thinking tools from the thought leader's work.
- As a user, I want to browse, edit, and delete individual frameworks so I can curate the agent's reasoning toolkit.
- As a user, I want to pin a framework when I know which one I need so I skip the classifier and get the right lens immediately.

---

### 9. Active Memory

Active Memory is persistent, AI-curated context injected directly into every prompt. It exists at two scopes: Project (Layer 4, ≤1000 tokens) and AgentInstance (Layer 6, ≤500 tokens).

Active Memory holds curated facts: decisions made, current status, constraints, open questions, learned patterns and preferences. It stays small and precise — the AI summarizes and prunes as it grows.

**Write UX (triple-trigger model):**

| Trigger | How it works |
|---|---|
| **User-initiated** | A "Save to memory" action in the chat UI. The user highlights or types a fact and adds it directly to Active Memory. Immediate, no approval needed — the user is the author. |
| **AI-proposed at conversation end** | When the user explicitly ends a conversation (clicks "end conversation" button or starts a new conversation in the same project), the AI reviews the conversation and proposes a batch of memory updates: new decisions, changed constraints, status updates. The user sees a review panel with each proposed update. User can approve all, reject all, or toggle individual items. |
| **Periodic proposal generation** | Every 10 messages, the system generates memory proposals in the background and queues them. This ensures memory candidates are captured even in long-running conversations that are never explicitly "ended." Queued proposals are presented the next time the user opens the project or agent, or at the next explicit conversation end — whichever comes first. The interval (10) is fixed in MVP — not user-configurable. |
| **Deferred proposals on navigation** | If the user navigates away (tab close, browser close, route change) without explicitly ending the conversation, any queued proposals from periodic generation are retained. No browser unload event is relied upon — the periodic trigger has already captured candidates server-side. Next time the user opens the project or agent, queued proposals are presented for review. |

**No automatic writes without user confirmation.** Active Memory is always injected — bad content degrades every future response. The user must approve AI-proposed updates.

**Token cap enforcement:** Active Memory has hard caps: ≤1000 tokens for Project, ≤500 tokens for AgentInstance. If a write (user-initiated or AI-proposed) would exceed the cap, the write is rejected and the user sees an error: "Memory is full ([current]/[max] tokens). Edit or remove existing entries to make room." The system does not auto-prune — the user controls what stays and what goes. The token count is displayed in the Active Memory editor so the user can track capacity.

**Entry structure:** Each Active Memory entry is an individual row (not a single text blob) with `created_at` timestamp and `source_conversation_id` (nullable — null for user-authored entries). This enables tracing where a memory came from, when it was captured, and which conversation produced it. The token cap applies to the combined content of all entries.

**Manual editing:** The user can view and directly edit Active Memory content at any time from the Project page (for project memory) or the Agent Profile page (for agent instance memory). Full CRUD — add, edit, delete individual entries.

**User stories:**

- As a user, I want to save an important decision to memory mid-conversation so future sessions automatically know about it.
- As a user, I want the AI to propose memory updates at the end of a conversation so important context is captured without me having to remember everything.
- As a user, I want to review and approve each proposed memory update so I control what gets injected into every future prompt.
- As a user, I want to edit my project's active memory directly so I can correct or remove outdated facts.

---

### 10. Context Stack & Generation Engine

Every user query assembles context from 9 layers, in order. The final prompt = Layers 1–7 (assembled) + user message.

**Always injected (deterministic):**

| Layer | Source | Max size | Present when |
|---|---|---|---|
| 1. User profile | Name + bio | ~100 tokens | Always |
| 2. Active company | Name + description | ~100 tokens | Always |
| 3. Project instructions | Project.Instructions | ~500 tokens | In a project conversation |
| 4. Project active memory | Project.ActiveMemory | ≤1000 tokens | In a project conversation |
| 5. Agent system prompt | AgentDefinition.Instructions | ~500 tokens | Agent invoked |
| 6. Agent active memory | AgentInstance.ActiveMemory | ≤500 tokens | Agent invoked |

**Classifier-selected (query-dependent):**

| Layer | Source | Behavior | Present when |
|---|---|---|---|
| 7. Matched framework | AgentDefinition.Frameworks | 4-step selection pipeline. One framework injected whole. | Agent invoked + match found |

**RAG retrieval (query-dependent, chunked):**

| Layer | Source | Behavior | Present when |
|---|---|---|---|
| 8. Project KB | Project.KnowledgeBase | Top-K relevant chunks via RAG pipeline | In a project conversation with KB docs |
| 9. Agent KB | AgentDefinition.KnowledgeBase | Top-K relevant chunks via RAG pipeline | Agent invoked with KB docs |

**Conversation history in the prompt:** In addition to the 9 context layers, the generation prompt includes recent conversation history — the actual user and AI messages from the current conversation. This provides conversational continuity (the AI remembers what was just discussed). As conversations grow, raw message history is compressed: the system maintains a rolling summary of older messages plus the most recent N turns in full. The summary is regenerated periodically (e.g., every 10 messages) using a background LLM call. This prevents context window overflow in long conversations while preserving conversational coherence. The conversation history sits between the assembled context layers (1–7) and the user's current message in the final prompt.

**Conversation summary LLM key policy:** The rolling summary compression call uses the user's BYOK key, selecting a model matching the user's configured keys (default model preferred, else first available). This is consistent with the linked upload key policy — all generation-class LLM calls in the user's session use their own key. The summary call is lightweight (~200–500 output tokens) and runs asynchronously via FastAPI BackgroundTasks.

**Compression fallback on BYOK failure:** If the compression call fails (rate limit, invalid/revoked key, provider outage), the system truncates the oldest messages from the conversation history without summarization and notifies the user of the issue (e.g., "Conversation history was trimmed — your API key encountered an error"). This is lossy but prevents context window overflow. The notification appears inline in the chat so the user can address the key issue.

**Agent switch and conversation history:** When a user switches agents mid-conversation, the full conversation history (including all prior AI responses from any previously active agent) is preserved in the rolling history and summary. Agent B sees the complete conversation, including Agent A's responses. Each message carries an `agent_id` tag (nullable — null for base/no-agent messages) so the UI can display visual markers showing which agent generated each response.

**Company-level conversations** (no project selected) assemble Layers 1–2 only, plus Layers 5–7 and 9 if an agent is invoked. Layers 3–4 (project instructions and project active memory) and Layer 8 (project KB) are absent because there is no project context. The agent's KB (Layer 9) is still retrieved if an agent is active.

**Per-query model selection:** A model selector in the chat UI lets the user choose which LLM to use for each query. Defaults to the user's preferred model from their profile. The context stack is model-agnostic — the same 9 layers are assembled regardless of which model processes them. The model selector shows all admin-enabled generation models. Models for which the user has not configured a matching API key are visible but disabled (greyed out) — this signals available options without confusing users into thinking they can use models they haven't set up.

**BYOK (Bring Your Own Key):** Users provide their own API keys for supported providers: Anthropic, OpenAI, Google, Groq. Keys are encrypted at rest. Available models depend on which keys the user has configured. At least one key is required for generation. BYOK keys are used for text generation only. Infrastructure LLM calls (embedding, framework reranker) use platform-owned keys — users are not charged for these and do not need specific provider keys for pipeline functionality.

**LLM client abstraction:** All four providers have different API interfaces. A unified LLM client layer (e.g., LiteLLM) sits between Kinetic's generation logic and the provider APIs, normalizing the interface so the rest of the codebase makes a single call regardless of which provider or model is selected. This is what makes per-query model switching and BYOK across multiple providers practical — without it, every provider requires its own integration path. FounderPanel uses LiteLLM for this and it supports all four of Kinetic's target providers (Anthropic, OpenAI, Google, Groq) including Groq's fast inference models.

**SSE streaming & auth:** Responses are streamed to the frontend via Server-Sent Events (SSE). Because the browser's `EventSource` API cannot send custom headers (including Authorization), the frontend proxies SSE requests through a Next.js server-side API route that injects the JWT before forwarding to the FastAPI backend. The backend SSE endpoint accepts the auth token via query parameter (from the proxy) or Authorization header (for direct API clients). This is a known constraint of EventSource — the proxy pattern is proven in FounderPanel.

---

### 11. MCP Context Access

Kinetic exposes its context stack via MCP (Model Context Protocol), allowing external AI tools (Claude Desktop, ChatGPT, Cursor, Slack, etc.) to consume Kinetic's layered context outside Kinetic's UI.

**Connection model:** The user generates a single MCP token from their User Profile page. This token authenticates the user — not a specific agent or project. The user adds Kinetic as one MCP server connection in their external client (one URL + one token). All scoping is controlled per-request via optional parameters.

**Per-request scoping:** Each MCP request accepts three optional parameters: `project_id`, `agent_id`, and `company_id`. The combination determines which context layers are assembled:

| Parameters provided | Company resolution | Context layers returned |
|---|---|---|
| `project_id` only | Inferred from project's parent | L1 (user profile) + L2 (company) + L3 (project instructions) + L4 (project active memory) + L8 (project KB) |
| `agent_id` only | **No company layer** | L1 (user profile) + L5 (agent system prompt) + L6 (agent active memory) + L7 (matched framework) + L9 (agent KB) |
| `project_id` + `agent_id` | Inferred from project's parent | Full 9-layer stack |
| `company_id` only | Explicitly stated | L1 (user profile) + L2 (company) |
| `company_id` + `agent_id` | Explicitly stated | L1 (user profile) + L2 (company) + L5 (agent system prompt) + L6 (agent active memory) + L7 (matched framework) + L9 (agent KB) |
| No parameters | **Rejected** — error: "provide at least one of `project_id`, `agent_id`, or `company_id`" | N/A |

**Company resolution rule:** A `project_id` implies the company (every project belongs to one company). When no `project_id` is provided, the user must pass `company_id` explicitly if they want company context (Layer 2). An `agent_id` alone does not require or inject company context — agents are user-level entities that work across companies.

**Agent memory is automatic:** When `agent_id` is provided, the system resolves the user's AgentInstance for that agent (using the user identity from the token + the `agent_id`). Agent active memory (Layer 6) and framework overrides are included automatically — no additional parameter needed.

**What MCP exposes:**

| Component | Included when | Notes |
|---|---|---|
| User profile | Always | Name + bio (Layer 1) |
| Company context | `project_id` or `company_id` provided | Name + description (Layer 2) |
| Project instructions | `project_id` provided | Layer 3 |
| Project active memory | `project_id` provided | Layer 4 |
| Agent system prompt | `agent_id` provided | Layer 5 |
| Agent active memory | `agent_id` provided | From user's AgentInstance (Layer 6) |
| Matched framework | `agent_id` provided + match found | 4-step selection pipeline runs server-side (Layer 7) |
| Project KB chunks | `project_id` provided + KB docs exist | RAG retrieval runs server-side (Layer 8) |
| Agent KB chunks | `agent_id` provided + KB docs exist | RAG retrieval runs server-side (Layer 9) |

This means an external client can get the same context richness as an in-app conversation — including project state, decisions, memory, and agent reasoning — through a single MCP connection.

**Who provides the LLM for generation?** The external client does. Kinetic's MCP server returns context (assembled layers based on scoping), and the host app (Claude Desktop, ChatGPT, Cursor, Slack, etc.) generates the response using its own model. Kinetic does not perform text generation for MCP requests.

**Server-side pipeline costs (MVP):** Kinetic's MCP server runs lightweight operations before returning context:

| Operation | What it does | Approximate cost | Key used |
|---|---|---|---|
| Framework selection reranker | Haiku scores top-5 framework candidates against the query | ~50 output tokens | Platform-owned |
| RAG vector search | Cosine similarity search against scoped chunk embeddings | No LLM call — pure vector math | N/A |
| Query embedding | Embed the user's query for vector search | One embedding API call | Platform-owned |

All pipeline operations in MVP use the platform-owned key — no BYOK keys are needed for MCP pipeline functionality. MCP access requires at least one API key configured in Kinetic only if the external client needs Kinetic to perform generation (which it does not in MVP — the external client provides its own model). When both `project_id` and `agent_id` are provided, both KB vector searches run, but since these are pure vector operations with no LLM calls, the cost is negligible.

**Authentication:** Revocable bearer token generated from the User Profile page. The token identifies the user — all project, agent, and company access is determined per-request via parameters and validated against the user's permissions. Tokens can be revoked from the User Profile page. A user may generate multiple tokens (e.g., one for Claude Desktop, one for Slack) and revoke them independently.

**Access control:** Each MCP request validates permissions per-parameter. The system checks: does this user have access to the requested agent? To the requested project? If either check fails, the request is rejected. MCP respects the same visibility and ownership settings as in-app access.

**MVP access rule (no permissions model):** In MVP, the only visibility levels are `private` and `public`. Any authenticated user can access any public agent via MCP. Private agents are accessible only by the owner. The full permissions model (owner/editor/invoker) ships with `shared` visibility post-MVP.

**Rate limiting:** MCP requests are rate-limited per-user with a daily cap. The limit is liberal — designed to prevent runaway automation or abuse, not to restrict normal usage. Default: 1,000 requests per user per day. Exceeding the cap returns HTTP 429 with a `Retry-After` header. The cap is configurable per-user by admin (for power users or integrations that need higher throughput). Rate limit status is exposed in response headers (`X-RateLimit-Remaining`, `X-RateLimit-Reset`).

**Read-only (MVP).** MCP access does not write back to Kinetic. External sessions do not update Active Memory (project or agent). Memory is consumed but not updated from external sessions. A write-back endpoint for memory proposals is a candidate post-MVP enhancement.

**User stories:**

- As a user, I want to generate one MCP token and add Kinetic as a single connection in Claude Desktop so all my projects and agents are accessible without managing multiple connections.
- As a user, I want to specify a project ID in my MCP request so the agent has my full project context — instructions, memory, and knowledge base — even outside Kinetic.
- As a user, I want to use an agent via MCP without specifying a project or company so I can get the agent's perspective for general thinking.
- As a user, I want to revoke an MCP token so I can cut off access to a specific client if needed.

---

### 12. Linked Upload

A convenience feature on User Profile, Company Profile, and Agent Profile pages that auto-fills fields from an uploaded document. Fully specified in `docs/feature-linked-upload.md`. Summary:

- **User Profile:** Upload LinkedIn PDF, resume, or bio → AI extracts Name and Short Bio → user reviews and edits → saves. File discarded after extraction.
- **Company Profile:** Upload business plan, pitch deck, or one-pager → AI extracts Company Name and Short Description → user reviews and edits → saves. File discarded after extraction.
- **Agent Profile:** Upload thought leader writing sample, transcript, interview, or article → AI extracts Agent Name and generates Instructions (system prompt) capturing thinking style, communication patterns, core principles, and expertise → user reviews and edits → saves. File discarded after extraction.

The uploaded file is NOT added to any Knowledge Base and is NOT used for RAG. The same upload → extract → review → save pattern applies across all three pages. If the user wants the document available for retrieval, they upload it separately to the relevant Knowledge Base.

---

## Design Direction

**Aesthetic:** Dark UI with teal highlights. The product should feel premium, focused, and tool-like — not playful or consumer. Think high-end developer tooling meets executive workspace.

**Target feel:** Tech-savvy startup founders and business executives. Users who are comfortable in Notion, Linear, or Raycast. They expect density, precision, and a UI that doesn't get in their way.

**Design principles:**
- Dark backgrounds with teal accent colors for interactive elements, highlights, and brand moments
- High information density — these users are not intimidated by complexity
- Minimal chrome, maximum focus on content and conversation
- Typography should feel sharp and editorial, not bubbly or rounded
- Animations should be subtle and purposeful — nothing decorative

---

## UI Structure

| Surface | What it shows |
|---|---|
| **Chat view** | Message thread with model selector and agent selector. Citation references below AI responses. |
| **Left sidebar** | Conversation history grouped by project + "General" group for company-level conversations. Company switcher. Navigation to Projects and Agents. |
| **Agent selector** | Side panel or dropdown to toggle an agent on/off for the current conversation. Shows active agent name and visual indicator when an agent is responding. |
| **User Profile page** | Name, bio (with linked upload), API key management, default model selector, MCP token management (generate/revoke). |
| **Company pages** | Create/edit companies (with linked upload), switch active company. |
| **Project pages** | Create/edit project, Instructions field, KB upload and management, Active Memory view/edit, conversation list. |
| **Agent Profile page** | Instructions (system prompt), KB upload and management, Framework Library (browse/edit/add/delete), visibility toggle. |
| **Admin panel** | Three tabs: Users (list, enable/disable accounts), LLM Models (manage generation/embedding/reranking model library), RAG Debug (retrieval traces for recent queries). |

---

## Security

### API Key Storage and Handling

Users store third-party LLM provider API keys (Anthropic, OpenAI, Google, Groq) in Kinetic. These are high-value credentials — a compromised key can generate significant charges on the user's provider account. The implementation must treat these with the same rigor as passwords.

**Encryption at rest:** Keys are encrypted with AES-256-GCM before writing to the database. The encryption key lives in a secrets manager or environment variable — never in the database alongside the encrypted values. A full database dump reveals no usable credentials.

**Never returned to the client:** After initial save, the API is forbidden from returning the decrypted key in any response. The frontend receives only a masked representation (e.g., `sk-ant-...abc1`). The plaintext key exists in server memory only for the duration of a single API call, then is discarded.

**Never logged:** FastAPI request/response logging must explicitly scrub API key fields. This is a known failure mode — it must be enforced at the logging middleware layer, not left to individual endpoint authors.

**Supabase RLS as a second layer:** Row Level Security policies ensure a user's key rows are only queryable by their own authenticated session. Even if the encryption layer were somehow bypassed, a user cannot access another user's rows.

**Key validation on save:** Before storing, the system makes a lightweight test call to validate the key. This catches paste errors immediately and confirms the key is functional.

**User-controlled deletion:** Users can delete any stored key at any time from their profile. Deletion permanently removes the encrypted record from the database.

**Secrets management decision (Gilfoyle):** The encryption key itself needs a home. Options: environment variable (simpler, sufficient for MVP), or a dedicated secrets manager like Doppler or AWS Secrets Manager (auditable access, supports rotation without a deploy). See the Linear ticket flagged for Gilfoyle.

### What Users Are Told

The user-facing security statement:

> "Your API keys are encrypted with AES-256 before being stored. We never log your keys, and they are never returned to your browser after you save them. Your keys are used only to make API calls on your behalf — they never leave our servers in plaintext. You can delete your keys from your profile at any time."

This is the canonical copy for the settings page tooltip and any FAQ. Do not claim keys are "completely safe" or "impossible to access" — no system makes that guarantee. The statement above is honest and verifiable.

---

## Dependencies

**Technical:**

- Supabase (PostgreSQL + pgvector + Auth + Storage) — database, vector search, authentication, file storage
- FastAPI (Python) — backend web framework; handles routing, auth, and background tasks
- Next.js 14 (App Router) + TypeScript — frontend framework
- Radix UI + shadcn/ui + Tailwind CSS — component library and styling
- LiteLLM — unified LLM client abstracting Anthropic, OpenAI, Google, and Groq APIs into a single interface
- LLM provider APIs (Anthropic, OpenAI, Google, Groq) — generation (via user BYOK keys)
- Embedding model API (`text-embedding-3-large`, OpenAI) — chunk and query embedding (platform-owned key)
- Text extraction library (PDF, DOCX, PPTX parsing) — shared between KB ingestion and linked upload
- MCP server implementation — for external agent access

**Codebase lineage:** Kinetic's implementation starts by porting proven components from FounderPanel (`/Users/brandonupchuch/Projects/founder_panel`), a prior product built on the same stack. Key components being ported: LLM client (LiteLLM wrapper with multi-provider streaming), Supabase Auth + JWT verification, model settings service, SSE streaming infrastructure, RAG retrieval pipeline (adapted from Qdrant to pgvector), document ingestion pipeline, chat service, and the shadcn/ui component library. See the FounderPanel reuse analysis for the full inventory and adaptation notes.

**Product:** None — this is the first release.

**External:** None — BYOK model means no vendor contracts needed for LLM access.

---

## Decisions Locked (This Session)

These decisions were made during PRD development and are now canonical:

| Decision | Detail |
|---|---|
| Active Memory write UX | Triple-trigger: (1) user-initiated ("save to memory"), (2) AI-proposed at explicit conversation end, (3) periodic background proposal generation every N messages. No automatic writes — all AI proposals require user approval. No reliance on browser unload events. |
| Conversation scope | Two levels: project conversations (full 9-layer stack) and company conversations (Layers 1–2 + agent layers if invoked, no project context). |
| Agent invocation UX | Side panel toggle, one agent at a time in MVP. UI clearly shows which agent is active. User can switch agents mid-conversation. Multi-agent planned post-MVP. |
| Company ↔ Project attachment | Auto-set to active company at creation. Changeable later. |
| Agent corpus scope | One corpus per agent. Users who want blended perspectives invoke separate agents. |
| MCP authentication | Revocable bearer token, generated per-user from User Profile page, passed as a header. One token gives access to all the user's projects and agents — scoping is per-request via `project_id`, `agent_id`, and `company_id` parameters. |
| MCP scoping model | Single connection per user. Per-request parameters (`project_id`, `agent_id`, `company_id`) determine which context layers are assembled. `project_id` implies company; `agent_id` alone skips company context; no parameters = rejected. |
| Context stack | 9 layers (no Thought Stream in MVP). |
| User bio length | 500–1000 characters. |
| Background processing | In-process (FastAPI BackgroundTasks) for MVP. Used for Active Memory proposal generation at conversation end and KB document ingestion. No separate queue service. |
| Frontend stack | Next.js 14 (App Router) + TypeScript + Radix UI + shadcn/ui + Tailwind CSS. Same stack as FounderPanel for maximum code reuse. |
| Vector DB | pgvector (Supabase extension) for MVP. Qdrant is a migration option later if scale demands it. At current scale (~5 users, ~2M words max KB), pgvector is sufficient and eliminates a separate service. |
| Codebase lineage | Kinetic implementation starts by porting components from FounderPanel. Backend: LLM client, auth, model settings, RAG pipeline (Qdrant→pgvector adaptation), ingestion pipeline, chat service. Frontend: shadcn component library, API client pattern, SSE proxy, admin panel structure. |
| Conversation history | Recent messages included in prompt between context layers and current message. Rolling summary compression for older messages to manage context window. |
| SSE auth | Frontend proxies SSE through Next.js server route to inject JWT (EventSource cannot send headers). Backend accepts token via query param or header. |
| Embedding key ownership | Platform-owned OpenAI API key for `text-embedding-3-large`. Users are not charged for embedding or pipeline LLM calls. BYOK keys are for generation only. |
| MVP RAG pipeline — simplified | Zero LLM calls in retrieval path. Pipeline: embed query → vector search (cosine similarity) → MMR → similarity threshold → citation assembly → inject. No query rewriting, no FTS hybrid, no LLM reranking, no recency scoring. Full V1 enhancements are addable via config flags. See `docs/rag-architecture.md`. |
| MVP ingestion pipeline — simplified | Text extraction → fixed-size chunking (~500 tokens, ~50 overlap) → embedding → indexing. No chunk-level enrichment, no semantic chunking. Document-level summary optional. V1 enhancements addable via config flags. |
| Active Memory overflow | Hard cap enforced. Writes exceeding cap rejected with error. User must edit/prune before adding. Token count displayed in editor. |
| Model selector UX | Shows all admin-enabled generation models. Models without a matching user API key are visible but disabled (greyed out). |
| Framework reranker key | Framework selection pipeline's Haiku reranker (~50 tokens/query) uses platform-owned key, not BYOK. |
| Linked upload + conversation compression LLM key | BYOK — uses the user's configured key and default model (or first available). Linked upload is gated on having at least one API key configured. |
| RAG_MAX_TOKENS approach | Dynamic — calculated as a percentage of the selected model's context window. Gilfoyle determines percentage and minimum floor. |
| Active Memory trigger reliability | Triple-trigger model: explicit end, periodic background generation (every N messages), and deferred on navigation. No browser unload dependency. |
| Framework upload format | Merge behavior (matching `id` = update, new `id` = add, missing = retain). Per-framework validation with partial import on failure. Format matches extraction script output. |
| MCP rate limiting | Per-user daily cap (default 1,000 requests/day), liberal, admin-configurable per user. HTTP 429 on exceed. |
| Agent switch conversation history | Full conversation history preserved across agent switches. All prior AI responses (from any agent) remain in rolling history. Messages tagged with `agent_id` for UI markers. |
| AgentDefinition update propagation | Immediate — all invokers get updated system prompt + frameworks on next query. No versioning in MVP. Revisit when `shared` visibility ships post-MVP. |
| Project company reassignment | Everything moves — conversations, Active Memory, and KB all transfer to the new company. |
| API keys per provider | One per provider (Anthropic, OpenAI, Google, Groq). Multiple keys per provider deferred post-MVP. |
| KB upload size limits | 25 MB per document, 1M token ingestion limit per document (mirrors FounderPanel). No per-KB or per-user storage quota in MVP. |
| User disable and public agents | Admin must transfer ownership of public agents before disabling a user account. Admin panel enforces this — disable is blocked until all public agents are transferred or set to private. |
| Conversation soft-delete | Users can soft-delete conversations (hidden from sidebar, retained in DB). No hard-delete in MVP. |
| Periodic memory proposal interval | Fixed at every 10 messages. Not user-configurable in MVP. |
| Conversation compression fallback | When BYOK key fails during rolling summary compression (rate limit, invalid key, provider outage), truncate oldest messages without summarization and notify the user of the issue. Lossy but functional — prevents context window overflow. |
| Active Memory entry structure | Each entry is an individual row with `created_at` timestamp and `source_conversation_id`. Not a single text blob. Enables tracing where a memory came from and when it was captured. |

---

## Decisions Needed

| Decision | Owner | Needed By |
|---|---|---|
| RAG token budget: fixed split between Project KB and Agent KB, or dynamic? | Gilfoyle | Before architecture spec |
| RAG_MAX_TOKENS: use a dynamic percentage of the selected model's context window. Gilfoyle to determine the percentage and minimum floor. | Gilfoyle | Before implementation |
| Document deletion: synchronous hard delete or soft-delete with deferred cleanup? | Gilfoyle | Before schema spec |
| Background task dispatch abstraction: write a thin abstraction layer over FastAPI BackgroundTasks now so migration to Celery/RQ later is a one-file change rather than a codebase refactor. | Gilfoyle | Before first background task is implemented |
| Text extraction library selection | Gilfoyle | Before KB ingestion or linked upload implementation |

---

## Open Questions

- [ ] Should company-level conversations count toward any engagement metrics differently than project conversations?
