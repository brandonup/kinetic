# Kinetic — Domain Model

**Status:** Draft
**Last updated:** 2026-03-21
**Owner:** Brandon (CEO)

---

## Purpose

This document defines every first-class entity in Kinetic, its key attributes, and how entities relate to each other. All specs, PRDs, and implementation work reference this document. Update this first when a naming or structural decision changes — never in a downstream doc first.

---

## Entities

### User
The person using Kinetic. Has a personal profile that is always present in every prompt.

| Attribute | Description | MVP |
|---|---|---|
| Name | Full name | Yes |
| Short bio | Professional summary (500–1000 chars, optional) | Yes |
| API keys | User-provided keys for LLM providers: Anthropic, OpenAI, Google, Groq. Encrypted at rest. Required for generation. | Yes |
| Default model | The user's preferred model for generation. Can be overridden per query. | Yes |

**Owns:** AgentDefinitions (as owner), AgentInstances (as invoker), Company list, Projects (through Companies).
**Prompt behavior:** Always injected in full. Small enough that RAG is not needed. ~100 tokens (MVP).

**User Profile page includes:**
- Name and short bio (with linked upload to auto-fill)
- API key management (add/edit/delete keys for each provider)
- Default model selection

---

### Company
A company the User is associated with. Users can have multiple; one is active at any time.

| Attribute | Description | MVP |
|---|---|---|
| Name | Company name | Yes |
| Short description | What the company does (500–1000 chars, optional) | Yes |

**Belongs to:** User.
**Has many:** Projects, Contacts.
**Prompt behavior:** Active company is always injected in full. Inactive companies are not injected. Small enough that RAG is not needed. ~100 tokens (MVP).

---

### Contact [POST-MVP]
A person the user interacts with in the context of a Company — a client stakeholder, colleague, partner, or other relationship. Holds relationship context that feeds pre-meeting briefings and the Thought Stream.

| Attribute | Description |
|---|---|
| Name | Contact's full name |
| Role / title | Their position |
| Company | The Company this contact belongs to |
| Relationship notes | Free-form context: personal details, communication preferences, rapport notes (e.g., "son plays baseball", "prefers email over Slack") |
| Last interaction | Timestamp of most recent meeting, email, or note |
| Associated projects | Projects this contact is involved in |

**Belongs to:** Company.
**Has many:** Thought Stream entries (via association).
**Prompt behavior:** Not directly injected. Contact context surfaces via Thought Stream entries tagged with `contact_id` — when a query or upcoming meeting involves a contact, their relationship notes and associated Thought Stream entries are retrieved through semantic search and scoping filters.

---

### Project
An in-app workspace for a specific initiative or body of work. The primary working context.

| Attribute | Description |
|---|---|
| Name | Project name |
| Company | The Company this project belongs to (user-assigned) |
| Instructions | Static, user-authored rules for how to work in this project (e.g., tone, constraints, approach). Never auto-updated. |
| Active Memory | Dynamic, AI-maintained facts about the project — decisions made, current status, open questions, constraints. Grows over time. ≤1000 tokens. |
| Knowledge Base | Attached Knowledge Base for this project (see Knowledge Base entity) |
| Documents | In-app docs created and edited within the project |

**Belongs to:** Company (one Company per Project; user-assigned at creation).
**Has one:** Active Memory, Knowledge Base.
**Prompt behavior:**
- Instructions → always injected (~500 tokens)
- Active Memory → always injected (≤1000 tokens)
- Knowledge Base → RAG retrieval (relevant chunks only)

---

### AgentDefinition
The shared, reusable blueprint for an AI persona. Contains everything about the agent's identity — system prompt, knowledge base, frameworks. Can be private, shared with specific users, or public.

| Attribute | Description |
|---|---|
| Name | Agent name (e.g., "Strategist", "Devil's Advocate", "Nate Jones") |
| System prompt | The core persona definition — how this agent thinks, what it prioritizes, how it communicates. User-authored, optionally auto-generated from a corpus. |
| Knowledge Base | Attached Knowledge Base (optional). Used for thought leader agents or domain-specific grounding. |
| Type | `custom` (user-authored) or `thought_leader` (corpus-seeded with auto-generated system prompt) |
| Visibility | `private` (owner only), `shared` (explicitly granted invokers), or `public` (any Kinetic user). Default: `private`. |
| Transparency | `transparent` (invokers can see system prompt + frameworks) or `opaque` (invokers can invoke but not inspect internals). Default: `transparent`. |
| Owner | The User who created and maintains the definition |
| Editors | Users who can modify the definition (system prompt, KB, frameworks) but not manage permissions |
| Invokers | Users who can invoke the agent and get their own AgentInstance |

**Owns:** Frameworks, Knowledge Base (optional).
**Has many:** AgentInstances (one per invoking user).
**Prompt behavior:**
- System prompt → always injected when agent is invoked (~500 tokens)
- Knowledge Base → RAG retrieval when agent is invoked
- Frameworks → classifier-selected injection (see Framework Selection Architecture)

**Agent Profile page includes:**
- Agent instructions (system prompt) — view and edit
- Knowledge Base — browse documents, upload new docs, manage folders and tags
- Framework library — browse, edit, add, delete, pin/exclude frameworks

**Thought Leader Agent Flow (V1):**
1. Owner uploads corpus to AgentDefinition's Knowledge Base
2. System auto-generates system prompt from corpus
3. Owner edits and approves system prompt
4. Owner (or AI) extracts frameworks from corpus → stored as Framework entities
5. Owner reviews, edits, adds, or deletes frameworks
6. Owner sets visibility (private/shared/public) and transparency (transparent/opaque)
7. At query time: system prompt injected, classifier selects framework, KB queried via RAG

---

### AgentInstance
The per-user runtime state for an AgentDefinition. Created automatically the first time a user invokes a shared or public agent. Holds everything specific to this user's relationship with the agent.

| Attribute | Description |
|---|---|
| User | The user this instance belongs to |
| AgentDefinition | The definition this instance is derived from |
| Active Memory | AI-curated facts about this user's relationship with the agent — learned patterns, preferences, interaction history. ≤500 tokens. |
| Thought Stream | Per-user interaction archive (see Thought Stream entity). Scoped by company + project, with opt-in cross-company search. |
| Framework overrides | Pinned or excluded frameworks for this user's sessions |
| Settings | Per-user config (e.g., cross-company retrieval opt-in) |
| Cross-company retrieval | Whether this instance can search its Thought Stream across all companies. Default: `off` (scoped to active company). Opt-in per query. |

**Belongs to:** User (one) and AgentDefinition (one).
**Has one:** Active Memory, Thought Stream (scoped).
**Prompt behavior:**
- Active Memory → always injected when agent is invoked (≤500 tokens)
- Thought Stream → semantic search when agent is invoked (scoped to active company + project by default)

**Instance lifecycle:**
- Created automatically on first invocation of a shared/public agent
- For private agents, the owner's instance is created when the agent is created
- Instance data (memory, thought stream) is private to the user — never visible to other users or the AgentDefinition owner
- If a user loses invoker access, their instance is retained but inactive (can be reactivated if access is restored or deleted by the user)

---

### Thought Stream [POST-MVP]
A pgvector-backed semantic search layer for lightweight, time-stamped context. A single table scoped to Project or AgentInstance via foreign keys (not separate structures per scope). Handles context that's too granular for a document upload but too voluminous to keep in Active Memory.

This is Kinetic's ambient intake layer — thoughts arrive from any channel (UI, email forward, meeting auto-extraction, quick capture) and get routed here.

| Attribute | Description |
|---|---|
| id | Primary key (uuid) |
| user_id | Owner |
| company_id | Scoping — which client (nullable for unscoped/inbox items) |
| project_id | Scoping — which project (nullable for unscoped/inbox items) |
| agent_instance_id | Scoping — which agent instance (nullable; only set for agent-level thoughts) |
| content | The raw thought/note/extract |
| embedding | pgvector semantic search (vector) |
| source_type | `manual_capture`, `meeting_extract`, `email_extract`, `ai_generated`, `quick_capture` |
| entity_type | `decision`, `task`, `relationship_note`, `idea`, `constraint`, `status_update`, `deliverable`, `follow_up` |
| contact_id | Associated Contact, if relevant (nullable) |
| promoted | Has this been incorporated into Active Memory? (boolean) |
| created_at | When captured (timestamp) |

**Architecture:** Single table, scoped by `company_id`, `project_id`, and `agent_instance_id` columns. Not separate streams — filtering happens at query time.

**Belongs to:** User. Scoped to Company/Project/AgentInstance via foreign keys.
**Prompt behavior:** Never injected directly. At query time, semantic search runs against the Thought Stream filtered to the active scope (company + project, or agent instance). Top-K results are included as supplementary context.

**Intake channels (planned):**
- In-app quick capture UI
- Email forwarding (auto-parsed and routed)
- Post-meeting transcript extraction (auto-generated)
- AI-generated (session-end extraction of key points)
- External (MCP endpoint for capture from Claude, ChatGPT, etc.)

**Triage flow:** Items with null `project_id` or `company_id` land in an inbox state. The AI suggests routing (which company, which project). User confirms or overrides. Once routed, the item is searchable within that scope.

---

### Knowledge Base
A structured, searchable collection of documents. Attached to a Project or an AgentDefinition. The RAG layer.

| Attribute | Description |
|---|---|
| Owner | Project or AgentDefinition (one parent) |
| Documents | Collection of uploaded files and text |
| Folders | User-created folder structure for organizing documents |
| Tags | Labels applied to documents. AI auto-suggests tags and metadata on upload; user can edit. |

**Belongs to:** Project (one) or AgentDefinition (one).
**Has many:** Documents.
**Prompt behavior:** Never injected directly. Queried via semantic search; relevant chunks retrieved and included per generation.

---

### Document
A single piece of content inside a Knowledge Base. The atom of the RAG layer.

| Attribute | Description |
|---|---|
| Title | Document name |
| Content | Full text content |
| File type | Transcript, article, report, code file, PDF, etc. |
| Folder | The folder within the Knowledge Base it lives in (optional) |
| Tags | Labels applied to this document (AI-suggested + user-editable) |
| AI-generated metadata | Summary, key topics, date extracted — auto-generated on upload |
| Source | Upload, paste, or URL (future) |
| Chunks | System-generated; not user-facing |

**Belongs to:** Knowledge Base.
**Prompt behavior:** Chunked and embedded at upload. Relevant chunks retrieved per query — not injected wholesale.

---

### Framework
A named, reusable reasoning tool extracted from a thought leader's corpus. Attached to an AgentDefinition. Injected whole into context when a classifier determines it matches the user's query — never chunked, never retrieved via RAG.

This is what makes a thought leader agent actually *apply* someone's thinking rather than just paraphrase fragments of it.

| Attribute | Description |
|---|---|
| ID | Stable unique identifier (kebab-case, e.g., `coordination-tax-diagnostic`) |
| Name | The framework's name as the author uses it (e.g., "Coordination Tax Audit") |
| Description | One sentence explaining what the framework does |
| Category | Domain tag. Core categories: `strategy`, `org-design`, `decision-making`, `problem-diagnosis`, `product`, `leadership`, `execution`, `evaluation`. AI sub-categories: `ai-prompting`, `ai-architecture`, `ai-adoption`, `ai-governance`. List is open — new categories added as corpora expand. |
| When to apply | **Array** of 3-5 trigger conditions — distinct situations the classifier matches against. Each entry is a discrete, matchable phrase. |
| Principles | The core ideas or rules of the framework |
| Steps | Ordered steps if the framework is procedural (optional) |
| Example application | 2-3 sentences showing the framework applied to a concrete scenario. Helps both the classifier (more matching surface) and the LLM (grounds application vs. recitation). |
| Related frameworks | Array of IDs of other frameworks in the same agent's library that this framework references or builds on |
| Source posts | References to the Knowledge Base documents the framework was extracted from |
| Confidence | `high` (explicitly named and structured by the author) or `medium` (clearly reusable but less formally named) |
| Origin | `extracted` (AI-generated from corpus) or `manual` (user-authored) |

**Belongs to:** AgentDefinition (one AgentDefinition has many Frameworks).
**Relationship to Knowledge Base:** Frameworks are extracted *from* Knowledge Base documents but stored separately. They are structured entities, not documents. The source posts field links back to the originating documents.
**Prompt behavior:** Never chunked or embedded as documents. The `when_to_apply` triggers are individually embedded into pgvector for the retrieval step of the selection pipeline. At query time, the multi-signal selection pipeline scores the user's message against all Frameworks for the invoked agent (see **Framework Selection Architecture** below). The top match above a confidence threshold is injected in full as a structured block. If no match exceeds the threshold, no framework is injected. User can manually pin or exclude frameworks via AgentInstance overrides.

---

### Active Memory
Persistent, AI-curated context injected directly into every prompt. Exists at the Project level and the AgentInstance level. Distinct from a Knowledge Base and from the Thought Stream.

Active Memory is the top tier of Kinetic's three-tier memory architecture. It stays small and precise — the AI is responsible for summarizing and pruning as it grows.

| Attribute | Description |
|---|---|
| Owner | Project or AgentInstance |
| Content | Structured facts: decisions, constraints, current status, open questions, patterns, learned user preferences |
| Last updated | Timestamp |
| Update trigger | AI proposes updates at session boundaries by reviewing new Thought Stream entries. User can also manually add/edit. |

**Belongs to:** Project (one) or AgentInstance (one).
**Prompt behavior:** Always injected in full when the owning Project or AgentInstance is active. Project Memory ≤1000 tokens. Agent Instance Memory ≤500 tokens.

**Promotion loop:** The AI periodically reviews new Thought Stream entries and proposes promotions to Active Memory (important decisions, status changes, constraints). Stale Active Memory entries can be demoted back to the Thought Stream archive. This keeps Active Memory current without manual curation.

---

## Three-Tier Memory Architecture

Kinetic uses a three-tier memory model. Each tier serves a different purpose with different storage, retrieval, and size characteristics.

| Tier | Name | What it holds | Storage | Retrieval | Size constraint |
|---|---|---|---|---|---|
| 1 | **Active Memory** | Curated facts: decisions, status, constraints, learned patterns | Structured text | Always injected (deterministic) | ≤1000 tokens (project), ≤500 tokens (agent instance) |
| 2 | **Thought Stream** | Captured thoughts, meeting extracts, email snippets, quick notes, interaction history | pgvector | Semantic search, scoped by company + project or agent instance | Unlimited rows |
| 3 | **Knowledge Base** | Uploaded documents: transcripts, reports, articles, corpus material | pgvector (chunked + embedded) | RAG — top-K chunks per query | No hard limit per KB |

**Design principle: capture like Open Brain (low friction, append-only, semantic), serve context like Kinetic (structured, layered, deterministic).**

- Tier 1 is deterministic — you always know what's in the prompt. No retrieval variance.
- Tier 2 handles scale — hundreds of thoughts and extracts over months, searchable without bloating the prompt.
- Tier 3 handles depth — full documents too large for direct injection.
- The promotion loop between Tier 2 → Tier 1 creates a natural curation cycle without manual maintenance.

---

## Relationships

```
User
├── has many Companies
│   ├── each Company has many Projects
│   │   ├── Project has one Active Memory
│   │   ├── Project has one Knowledge Base
│   │   │   └── Knowledge Base has many Documents
│   │   └── Project has many in-app Docs
│   └── each Company has many Contacts
├── has many AgentDefinitions (as owner)
│   ├── AgentDefinition has many Frameworks
│   ├── AgentDefinition has one Knowledge Base (optional)
│   │   └── Knowledge Base has many Documents
│   │       └── Framework.source_posts → links back to Documents
│   ├── AgentDefinition has visibility (private/shared/public)
│   └── AgentDefinition has many AgentInstances (one per invoking user)
└── has many AgentInstances (as invoker)
    ├── AgentInstance has one Active Memory
    └── AgentInstance has one Thought Stream (scoped by company + project)

Thought Stream (single table)
├── scoped by user_id (always)
├── scoped by company_id (nullable — null = inbox)
├── scoped by project_id (nullable — null = company-level or inbox)
├── scoped by agent_instance_id (nullable — null = project-level thought)
└── scoped by contact_id (nullable — for relationship notes)
```

---

## Context Stack

How the final prompt is assembled for every generation. Full V1 uses 10 layers; **MVP ships with 9 layers** (Thought Stream is deferred — see note below).

### Model Selection

The user chooses which LLM to use for generation. Model selection is per-query — the user can switch models at any time during a session.

| Setting | Where it lives | Behavior |
|---|---|---|
| Default model | User profile | Used when no per-query override is selected |
| Per-query override | Chat UI (model selector) | User picks a specific model before sending a query. Overrides the default for that query only. |

Supported providers (BYOK — Bring Your Own Key): Anthropic, OpenAI, Google, Groq. Available models depend on which API keys the user has configured. The context stack assembly is model-agnostic.

### Direct Injection (always present, deterministic)
| Layer | Source | Max size |
|---|---|---|
| 1. User profile | User entity | ~100 tokens |
| 2. Active company context | Active Company entity | ~100 tokens |
| 3. Project instructions | Project.Instructions | ~500 tokens |
| 4. Project active memory | Project.ActiveMemory | ≤1000 tokens |
| 5. Agent system prompt(s) | Invoked AgentDefinition(s) | ~500 tokens each |
| 6. Agent active memory | Invoked AgentInstance(s).ActiveMemory | ≤500 tokens each |

### Semantic Search (query-dependent, pgvector)
| Layer | Source | Behavior | MVP |
|---|---|---|---|
| 7. Thought stream | ThoughtStream | Semantic search against user query. Top-K results injected as supplementary context. | **[DEFERRED — post-MVP]** |
| 7 (MVP) / 8 (V1). Matched framework | Invoked AgentDefinition(s).Frameworks | 4-step selection pipeline: embedding retrieval → expertise boost → LLM reranker → inject winner whole. | Yes |

> **[DEFERRED · Thought Stream]** Layer 7 (Thought Stream) ships post-MVP. In MVP, the matched framework is Layer 7. When Thought Stream ships, it becomes Layer 7 and framework selection shifts to Layer 8.

### RAG Retrieval (query-dependent, chunked)
| Layer | Source | Behavior |
|---|---|---|
| 8 (MVP) / 9 (V1). Project knowledge | Project.KnowledgeBase | Top-K chunks relevant to current query |
| 9 (MVP) / 10 (V1). Agent knowledge | Invoked AgentDefinition(s).KnowledgeBase | Top-K chunks relevant to current query |

**MVP final prompt** = layers 1–6 (injected) + layer 7 (framework) + layers 8–9 (RAG) + user message.
**Full V1 final prompt** = layers 1–6 (injected) + layers 7–8 (Thought Stream + framework) + layers 9–10 (RAG) + user message.

---

## Framework Selection Architecture

How Layer 7 (MVP) / Layer 8 (full V1) decides which framework (if any) to inject. This is a multi-signal pipeline, not a single classifier.

### Design Principles

- **Category is for browsing, not matching.** The category list is open — users create agents with different backgrounds and expertise, so categories grow organically. Category is useful for admin UI (filtering, organizing) but is too coarse for runtime selection. Multiple frameworks share a category; the discriminative signal is in `when_to_apply`.
- **`when_to_apply` is the primary matching surface.** Triggers are written in user voice — how someone actually phrases a problem. This is deliberate: embedding similarity works best when the index text sounds like the query text.
- **Agent expertise boosts, never gates.** An agent's background/expertise influences ranking but never prevents a framework from matching. A strategy-focused agent still gets `coordination-tax-audit` if the user's query clearly calls for it — but when scores are close, the agent's domain breaks the tie.

### Pipeline Steps

**Step 1 — Embedding Retrieval (primary)**
At index time, each `when_to_apply` trigger is individually embedded using a text embedding model. At query time, the user's message is embedded and scored against all trigger vectors for the invoked agent's frameworks via cosine similarity. Returns top-K candidates (K=5).

Why per-trigger embedding (not per-framework): A single framework may match 3-5 very different phrasings. Embedding each trigger separately gives finer-grained matching than embedding a concatenated blob.

**Step 2 — Agent Expertise Boost + Recency Scoring (tie-breaking)**
Each candidate's similarity score is adjusted based on two signals: (1) alignment between the framework's category/domain and the invoked agent's expertise profile, and (2) framework recency based on `created_at` (when the framework was added to the library). Both are small additive boosts — enough to break ties, not enough to override a strong semantic match. Recency scoring ensures that when a user refines or adds new frameworks over time, the updated thinking is preferred over older entries when similarity scores are otherwise close. The recency weight is configurable and applies only when top candidates are within a narrow similarity band.

**Step 3 — LLM Reranker (precision filter)**
Top-5 candidates (post-boost) are passed to a fast model (e.g., Haiku) with the full user message and the agent's system prompt. The reranker sees each candidate's name, description, and triggers — not the full framework body. It returns the best 1-2 matches with a confidence score.

If the top score is below a threshold, no framework is injected (the user's query doesn't match any framework well enough).

**Step 4 — Injection**
The winning framework is injected whole into the prompt as a structured block at Layer 8.

### Signal Summary

| Signal | Source | Role | When it matters |
|---|---|---|---|
| Semantic similarity | `when_to_apply` embeddings vs. user query | Primary retrieval | Always — this is the workhorse |
| Agent expertise boost | Agent profile × framework category | Tie-breaking | When 2+ frameworks score similarly |
| Recency scoring | Framework `created_at` timestamp | Tie-breaking | When top candidates are within a narrow similarity band — prefers recently added/updated frameworks |
| LLM reranker | Fast model scoring top candidates in context | Precision filter | Prevents false positives from embedding noise |
| User feedback (future) | Thumbs up/down on framework usefulness | Quality improvement | Post-V1 — used to fine-tune trigger phrasing |

### Scale Characteristics

At 505 source posts, expect 50-150 frameworks × 3-5 triggers = 150-750 vectors. This is small enough for in-memory cosine similarity — no vector database needed until well past 1,000 frameworks per agent. The LLM reranker call is cheap (~50 output tokens via Haiku) and only runs on the top-5 candidates.

### User Overrides (via AgentInstance)

Users can bypass the pipeline entirely:
- **Pin a framework:** Force a specific framework to be injected for the session, skipping selection.
- **Exclude frameworks:** Remove specific frameworks from the candidate pool for the session.
- **No framework mode:** Disable Layer 8 injection entirely.

---

## Agent Permissions Model

| Role | Can do |
|---|---|
| **Owner** | Edit system prompt, KB, frameworks. Manage permissions. Set visibility and transparency. Delete. Transfer ownership. |
| **Editor** | Edit system prompt, KB, frameworks. Cannot manage permissions, change visibility, or delete. |
| **Invoker** | Use the agent. Gets their own AgentInstance. Can see definition internals only if transparency = `transparent`. Cannot modify the definition. |

**Visibility levels:**

| Visibility | Who can invoke | Who can edit |
|---|---|---|
| `private` | Only the owner | Only the owner |
| `shared` | Explicitly granted invokers | Owner + editors |
| `public` | Any Kinetic user | Only the owner + editors |

**Transparency levels:**

| Transparency | What invokers see |
|---|---|
| `transparent` | System prompt, frameworks, knowledge base contents — full visibility into how the agent thinks |
| `opaque` | Can invoke the agent and interact with it, but cannot inspect system prompt, frameworks, or KB contents |

---

## MCP Agent Access

AgentDefinitions are accessible via MCP, allowing users to invoke Kinetic agents from external AI tools (Claude, ChatGPT, Cursor, etc.) without being inside Kinetic's UI.

### What MCP exposes (AgentDefinition only)

| Component | Exposed via MCP | Notes |
|---|---|---|
| System prompt | Yes | Injected as system context in the external client |
| Knowledge Base | Yes | RAG retrieval against the agent's KB, returning relevant chunks |
| Frameworks | Yes | Full selection pipeline runs against the user's query; matched framework returned |

### What MCP does NOT expose (AgentInstance)

| Component | Exposed via MCP | Why not |
|---|---|---|
| Active Memory | No | Per-user learned patterns stay inside Kinetic. External clients get the agent's reasoning capability without personalization. |
| Thought Stream | No | Interaction history is Kinetic-internal. External clients don't contribute to or read from the thought stream. |
| Framework overrides | No | Pinned/excluded frameworks are session-level Kinetic state. |

### How it works

1. User generates an MCP connector URL for their AgentDefinition from Kinetic's settings.
2. User adds the connector URL to their external AI client (Claude Desktop, ChatGPT custom GPT config, Cursor, etc.).
3. When the user sends a query in the external client, the MCP server:
   - Injects the agent's system prompt
   - Runs the framework selection pipeline against the query → returns matched framework (if any)
   - Runs RAG retrieval against the agent's Knowledge Base → returns relevant chunks
4. The external client uses these as context alongside its own generation.

### Access control

- MCP access respects the same visibility and transparency settings as in-app access.
- Only users with `invoker` (or higher) permissions on the AgentDefinition can generate a connector URL. **MVP rule (no permissions model):** Any authenticated user can access public agents via MCP. Private agents are accessible only by the owner. The full permissions model (owner/editor/invoker) ships with `shared` visibility post-MVP.
- If transparency = `opaque`, the external client receives the context (system prompt, framework, KB chunks) for use in generation, but the raw content is not displayed to the user separately.
- MCP connector URLs are per-user and can be revoked.

### Implications

- **External clients get the agent's identity, not its memory of you.** This is by design — Active Memory and Thought Stream are Kinetic's competitive advantage. MCP gives you portable reasoning; Kinetic gives you personalized reasoning.
- **Framework selection still runs server-side.** The external client sends the query; Kinetic's MCP server runs the full 4-step pipeline and returns the matched framework. This preserves the quality of framework matching regardless of the client.
- **No write-back to Kinetic.** MCP access is read-only. External sessions don't update the AgentInstance's Active Memory or Thought Stream. If you want context from an external session captured, use the Thought Stream's external capture channel (manual or via a separate MCP capture endpoint).

---

## Naming Conventions

| Term | Definition | Never call it |
|---|---|---|
| Project | In-app workspace | "Folder", "Workspace" |
| Knowledge Base | The RAG document store attached to a Project or AgentDefinition | "Docs", "Files", "Context" |
| Document | A single item inside a Knowledge Base | "File" (internally fine, but user-facing label is Document) |
| Active Memory | The always-injected, AI-curated fact store on a Project or AgentInstance | "Notes", "History", "Log" |
| Thought Stream | The pgvector-backed semantic search layer for lightweight captured context | "Inbox" (inbox is a state within the Thought Stream, not a synonym) |
| Instructions | The static, user-authored project prompt rules | "System prompt" (that's the AgentDefinition term), "Settings" |
| AgentDefinition | The shared, reusable blueprint for an AI persona | "Agent" alone is acceptable in casual use; "Bot", "Assistant", "Model" are not |
| AgentInstance | A user's personal runtime state for an AgentDefinition | "Session", "Copy" |
| Contact | A person entity under a Company | "Client" (that's the Company), "User" (that's the Kinetic user) |
| Framework | A named reasoning tool attached to an AgentDefinition, classifier-selected | "Skill", "Template", "Prompt" |
| Company | A user's associated company | "Client", "Organization" (user-facing: "Company") |

---

## Open Questions

_Questions 1–3 and 7 resolved — see `MEMORY.md`. Question 8 resolved: admin must transfer ownership before disabling user._

4. **Knowledge Base size limits:** What are the practical upload limits per Document and per Knowledge Base? Decision: mirror FounderPanel limits. Gilfoyle to cross-reference FounderPanel during architecture spec. _(Pending Gilfoyle confirmation of exact values.)_

5. **Contact ↔ Thought Stream integration:** [POST-MVP] How are Contacts surfaced in pre-meeting briefings? Deferred with Contact entity and Thought Stream.

6. **Thought Stream inbox triage UX:** [POST-MVP] How does the user confirm or override AI-suggested routing for unscoped thoughts? Deferred with Thought Stream.
