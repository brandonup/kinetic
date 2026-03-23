# Kinetic MVP — Build Order

**Status:** Draft
**Author:** Jared
**Date:** 2026-03-21
**Project:** Kinetic

---

## Purpose

This document sequences the Kinetic MVP build sprint by sprint. It tells every agent what to build, in what order, and with what dependencies. It is the source of truth for sprint prep — Jared reads this before running `Prepare Sprint N`.

**Guiding principle:** Ship a working core early (auth + generation engine), layer features on top. FounderPanel provides significant reuse — Sprint 1 is mostly port-and-adapt, not greenfield.

---

## Agent Ownership

| Agent | Domain |
|---|---|
| **Gilfoyle** | Architecture, ADRs, db-schema-spec.md, code reviews, security |
| **Dinesh** | Interaction flows — all UI + API endpoints the user touches directly |
| **Big Head** | Workflow pipelines — ingestion, RAG retrieval, context stack assembly, generation, background jobs, MCP server |
| **Jìan** | Test plans, test coverage, evals |
| **Jared** | Specs (one sprint ahead of implementation), sprint prep |

**Parallelism rule:** Dinesh and Big Head almost never share files. When both have unblocked work, open them simultaneously.

---

## Skills Reference

Every agent must invoke the relevant skill before starting work. Skills are invoked via the `Skill` tool in the session. The table below maps agent + task type → skill to invoke.

### Jared

| Task type | Skill to invoke |
|---|---|
| Writing any feature spec | `product-management:feature-spec` |
| Writing user stories within a spec | `anthropic-skills:user-story` |
| Breaking a large feature into tickets | `anthropic-skills:epic-breakdown-advisor` |
| Writing an implementation plan | `anthropic-skills:writing-plans` |
| Feature ideation (before any new feature) | `anthropic-skills:brainstorming` |

### Gilfoyle

| Task type | Skill to invoke |
|---|---|
| Writing ADRs or implementation plans | `anthropic-skills:writing-plans` |
| Writing pgvector queries, schema DDL, migration SQL, or any complex SQL | `data:sql-queries` |

### Dinesh

| Task type | Skill to invoke |
|---|---|
| Before starting any implementation ticket | `anthropic-skills:writing-plans` |
| Building any UI component, page, or layout | `anthropic-skills:frontend-design` |
| Writing error messages, empty states, tooltips, button labels, or any microcopy | `design:ux-writing` |
| Before marking any frontend ticket Done | `design:accessibility-review` |

### Big Head

| Task type | Skill to invoke |
|---|---|
| Before starting any implementation ticket | `anthropic-skills:writing-plans` |
| Writing pgvector cosine similarity queries or any complex SQL in the RAG or ingestion pipeline | `data:sql-queries` |

### Jìan

| Task type | Skill to invoke |
|---|---|
| Scaffolding test plans | `anthropic-skills:writing-plans` |
| Reviewing eval methodology or analysis accuracy | `data:data-validation` |
| Analyzing eval scores, precision/recall metrics (framework selection, RAG retrieval) | `data:statistical-analysis` |

---

## FounderPanel Reuse Map

Before writing any net-new code, Dinesh and Big Head must port these components from `~/Projects/founder_panel`. Porting happens in Sprint 1.

| Component | Owner | Notes |
|---|---|---|
| LLM client abstraction (LiteLLM) | Big Head | Swap Qdrant → pgvector throughout |
| Auth service (magic link + OAuth) | Dinesh | Adapt user model for Kinetic schema |
| Model settings (admin model library) | Dinesh | Add `embedding` + `reranking` categories |
| RAG pipeline (ingestion + retrieval) | Big Head | Qdrant → pgvector; update chunk schema |
| Chat service + SSE proxy | Big Head | Adapt for 9-layer context stack |
| shadcn/ui component library | Dinesh | Minimal adaptation needed |
| Admin panel shell | Dinesh | Adapt for Kinetic tabs |
| API client (TypeScript) | Dinesh | Adapt base URL + auth headers |

---

## Sprint Map

| Sprint | Theme | Weeks |
|---|---|---|
| 1 | Foundation — Port + Schema | W1 |
| 2 | Core Entities — Users, Companies, Projects | W2 |
| 3 | Conversations + Generation Engine | W3 |
| 4 | Agents + Framework Selection Pipeline | W4 |
| 5 | Active Memory + Linked Upload | W5 |
| 6 | MCP + Framework Library UI + Admin | W6 |
| 7 | Polish + Integration + Launch Prep | W7 |

---

## Sprint 1 — Foundation: Port + Schema

**Goal:** Working scaffold with auth, FounderPanel ports complete, canonical DB schema written, document ingestion running.

| Agent | Feature / Work | Tier | Skills | Notes |
|---|---|---|---|---|
| **Gilfoyle** | Write `docs/db-schema-spec.md` for all MVP entities | Complex | `writing-plans`, `data:sql-queries` | Canonical schema for all agents. No implementation starts without this. Covers: User, Company, Project, Conversation, Message, AgentDefinition, AgentInstance, KnowledgeBase, Document, Chunk, Framework, ActiveMemoryEntry, McpToken |
| **Gilfoyle** | ADR: Infrastructure choices (Supabase, pgvector, FastAPI, Next.js, LiteLLM, BackgroundTasks) | Standard | `writing-plans` | Locks stack. References FounderPanel precedents. |
| **Dinesh** | Port: Auth service from FounderPanel (magic link + OAuth) | Standard | `writing-plans` | Adapt User model to Kinetic schema. No password flows. |
| **Dinesh** | Port: Frontend scaffold (Next.js App Router, shadcn, admin shell) | Standard | `writing-plans`, `frontend-design`, `design:ux-writing` | App Router only. Remove FounderPanel-specific routes. Apply dark/teak theme per PRD design direction. |
| **Big Head** | Port: LLM client abstraction (LiteLLM) | Standard | `writing-plans`, `data:sql-queries` | Swap any Qdrant references → pgvector stubs. Verify all 4 providers (Anthropic, OpenAI, Google, Groq) route through it. |
| **Big Head** | Port: Document ingestion pipeline | Complex | `writing-plans`, `data:sql-queries` | Extract → fixed-size chunk (~500 tokens, ~50 overlap) → embed (`text-embedding-3-large`, platform key) → pgvector index. Auto-retry 3x with backoff. Stage tracking per document. |
| **Jìan** | Auth test coverage | Standard | `writing-plans`, `data:data-validation` | Registration, magic link flow, OAuth callback, session validation, admin vs user role enforcement |
| **Jared** | Projects + Conversations spec | Standard | `product-management:feature-spec`, `anthropic-skills:user-story` | Ship by end of W1 so Sprint 2 can start implementation |

**Dependencies in:** None — this is the root sprint.

**Handoffs out:**
- `db-schema-spec.md` unlocks all implementation work. Nothing else ships without it.
- Ingestion pipeline unlocks RAG retrieval work in Sprint 2.
- Auth unlocks everything.

---

## Sprint 2 — Core Entities: Users, Companies, Projects

**Goal:** A user can log in, set up their profile and API keys, create a company, create a project, and upload documents to a KB. No generation yet.

| Agent | Feature / Work | Tier | Skills | Notes |
|---|---|---|---|---|
| **Gilfoyle** | ADR: RAG retrieval pipeline (query embed → vector search → MMR → threshold → inject) | Standard | `writing-plans`, `data:sql-queries` | Zero LLM calls in retrieval path. Config flags for V1 enhancements. |
| **Gilfoyle** | Review Dinesh auth + frontend scaffold | Fast | — | Code review only |
| **Dinesh** | User Profile CRUD | Standard | `writing-plans`, `frontend-design`, `design:ux-writing`, `design:accessibility-review` | Name, bio (500–1000 chars), API keys (AES-256-GCM at rest, never returned decrypted), default model selector |
| **Dinesh** | Company CRUD + switcher | Standard | `writing-plans`, `frontend-design`, `design:ux-writing` | Name, description, create/edit, active company switcher in nav |
| **Dinesh** | Project CRUD | Standard | `writing-plans`, `frontend-design`, `design:ux-writing` | Name, company FK (auto-set to active), instructions field (~500 tokens) |
| **Dinesh** | Admin Users tab | Standard | `writing-plans`, `frontend-design` | List users, enable/disable. Disable blocked until public agents transferred or set to private. |
| **Dinesh** | Admin LLM Models tab | Standard | `writing-plans`, `frontend-design` | Port from FounderPanel model settings. Three categories: `generation`, `embedding`, `reranking`. Only `generation` user-facing in MVP. In-memory cache + DB. |
| **Big Head** | RAG retrieval pipeline | Complex | `writing-plans`, `data:sql-queries` | Embed query → cosine similarity vector search → MMR → similarity threshold → citation assembly → inject. No LLM calls. Config-flag stubs for V1 enhancements (query rewriting, FTS, LLM reranker, recency scoring). |
| **Jìan** | Ingestion pipeline tests | Standard | `writing-plans`, `data:data-validation` | Happy path, retry logic, stage tracking, token limit rejection (>1M tokens), file size rejection (>25MB) |
| **Jìan** | RAG retrieval pipeline tests | Standard | `writing-plans`, `data:data-validation`, `data:statistical-analysis` | MMR selection, threshold gating, citation assembly |
| **Jared** | Agents spec (AgentDefinition/AgentInstance) | Standard | `product-management:feature-spec`, `anthropic-skills:user-story` | Ship by end of W2 |
| **Jared** | Active Memory spec (triple-trigger, token cap, entry structure) | Standard | `product-management:feature-spec`, `anthropic-skills:user-story` | Ship by end of W2 |

**Dependencies in:** `db-schema-spec.md` approved (Sprint 1 Gilfoyle).

**Handoffs out:**
- User Profile + API keys unlocks BYOK routing in Sprint 3.
- RAG retrieval pipeline unlocks KB injection in Sprint 3.

---

## Sprint 3 — Conversations + Generation Engine

**Goal:** A user can start a conversation in a project, send a message, and get a streaming response grounded in Layers 1–4 (user, company, project instructions, project active memory stub). Context stack is live. RAG injection from Project KB is live.

| Agent | Feature / Work | Tier | Skills | Notes |
|---|---|---|---|---|
| **Gilfoyle** | ADR: Context stack assembly + generation endpoint architecture | Standard | `writing-plans`, `data:sql-queries` | 9-layer assembly logic, conversation history rolling summary, SSE streaming + auth proxy, BYOK key routing |
| **Gilfoyle** | ADR: Conversation entity + history compression | Standard | `writing-plans` | Rolling summary every N messages, BYOK fallback truncation |
| **Dinesh** | Conversation CRUD + chat UI | Complex | `writing-plans`, `frontend-design`, `design:ux-writing`, `design:accessibility-review` | Left sidebar (grouped by project + "General"), chat thread, soft-delete, rename, auto-title from first message. Project vs company scope. |
| **Dinesh** | Model selector UI | Standard | `writing-plans`, `frontend-design`, `design:ux-writing` | Shows all admin-enabled generation models. Models without matching user BYOK key are visible but greyed out. |
| **Dinesh** | SSE proxy (Next.js server route) | Standard | `writing-plans` | Port from FounderPanel. Injects JWT before forwarding to FastAPI. Backend accepts token via query param. |
| **Big Head** | Context stack assembly (Layers 1–4 + 8) | Complex | `writing-plans`, `data:sql-queries` | Deterministic layers: user profile, active company, project instructions, project active memory (stub — empty until Sprint 5). RAG retrieval injection for project KB (Layer 8). |
| **Big Head** | Generation endpoint + SSE streaming | Complex | `writing-plans` | Assemble context → route to LLM via LiteLLM → stream response → store messages. BYOK key routing. Per-query model selection. |
| **Big Head** | Conversation history compression | Standard | `writing-plans` | Rolling summary every 10 messages. Background job via FastAPI BackgroundTasks. BYOK key for summary call. Truncation fallback on BYOK failure. |
| **Jìan** | User Profile + Company + Project CRUD tests | Standard | `writing-plans`, `data:data-validation` | CRUD, field validation, company switcher state, project-company FK |
| **Jìan** | Context stack unit tests | Standard | `writing-plans`, `data:data-validation` | Layer assembly order, presence conditions (project vs company conversation), token budget |
| **Jared** | Framework Library spec | Standard | `product-management:feature-spec`, `anthropic-skills:user-story` | Ship by end of W3 |
| **Jared** | Linked Upload spec | Standard | `product-management:feature-spec`, `anthropic-skills:user-story` | Ship by end of W3. References `docs/feature-linked-upload.md`. |

**Dependencies in:** API keys functional (Sprint 2 Dinesh). RAG retrieval pipeline approved (Sprint 2 Gilfoyle).

**Handoffs out:**
- Working generation engine unlocks Agent invocation in Sprint 4.
- Context stack assembly unlocks Layers 5–7 + Layer 9 in Sprint 4.

---

## Sprint 4 — Agents + Framework Selection Pipeline

**Goal:** A user can create an agent, invoke it in a conversation, and get framework-augmented responses. AgentDefinition/AgentInstance split live. Layers 5–7 + 9 active in generation.

| Agent | Feature / Work | Tier | Skills | Notes |
|---|---|---|---|---|
| **Gilfoyle** | ADR: AgentDefinition/AgentInstance architecture + framework selection pipeline | Complex | `writing-plans`, `data:sql-queries` | Entity split, AgentInstance auto-create logic, framework embedding strategy (per-trigger vectors), 4-step pipeline (embed → expertise boost → Haiku reranker → inject whole) |
| **Gilfoyle** | Code review Sprint 3 generation engine | Standard | — | Focus on BYOK key handling, SSE auth, context assembly order |
| **Dinesh** | AgentDefinition CRUD | Standard | `writing-plans`, `frontend-design`, `design:ux-writing` | Name, instructions (~500 tokens), visibility toggle (private/public), type (`custom` / `thought_leader`), KB attachment, Agent Profile page |
| **Dinesh** | AgentInstance — auto-create on first invocation | Standard | `writing-plans` | Created on first user invocation. Per-user, per-agent. Active memory placeholder (empty). Framework override stubs. |
| **Dinesh** | Agent invocation UI | Standard | `writing-plans`, `frontend-design`, `design:ux-writing`, `design:accessibility-review` | Side panel toggle in chat. One agent at a time. Agent name + visual indicator when active. Switch agent mid-conversation (full history preserved, `agent_id` tag per message). |
| **Big Head** | Framework selection pipeline | Complex | `writing-plans`, `data:sql-queries` | Per-trigger vector embedding at upload. 4-step at query time: (1) cosine similarity on trigger vectors, (2) expertise boost + recency boost (tie-breaking), (3) Haiku reranker on top-5 (~50 output tokens, platform key), (4) inject winner whole. No match → no injection. |
| **Big Head** | Context stack — Agent layers (5–7 + 9) | Standard | `writing-plans`, `data:sql-queries` | Add agent system prompt (L5), agent active memory (L6, stub), matched framework (L7), agent KB RAG (L9) to assembly. Company-level conversation: no L3/4/8. |
| **Jìan** | Conversation + generation engine tests | Standard | `writing-plans`, `data:data-validation` | BYOK routing, model selector, SSE message integrity, conversation history compression |
| **Jìan** | Agent CRUD + invocation tests | Standard | `writing-plans`, `data:data-validation` | AgentInstance auto-create, agent switch, history tag integrity |
| **Jared** | Active Memory triple-trigger spec (finalize) | Fast | `product-management:feature-spec` | Confirm spec is unambiguous before Sprint 5 implementation |
| **Jared** | MCP spec | Standard | `product-management:feature-spec`, `anthropic-skills:user-story` | Ship by end of W4 |

**Dependencies in:** Generation endpoint live (Sprint 3 Big Head). Context stack Layers 1–4 + 8 working.

**Handoffs out:**
- Framework pipeline unlocks Framework Library UI (Sprint 6).
- AgentInstance entity unlocks Active Memory write flows (Sprint 5).

---

## Sprint 5 — Active Memory + Linked Upload

**Goal:** Active Memory writes and proposals work across all three triggers. Linked Upload live on all three surfaces (User Profile, Company, Agent). Context compounds across sessions.

| Agent | Feature / Work | Tier | Skills | Notes |
|---|---|---|---|---|
| **Gilfoyle** | Review Active Memory background job design | Fast | — | Verify no auto-writes without user confirmation. Review BYOK key policy for proposals. |
| **Gilfoyle** | Review Linked Upload LLM flow + BYOK gating | Fast | — | Gated on at least one API key configured. File discarded after extraction. |
| **Dinesh** | Active Memory UI | Standard | `writing-plans`, `frontend-design`, `design:ux-writing`, `design:accessibility-review` | View/edit entries (full CRUD). Token cap display (current/max). User-initiated "Save to memory" action in chat. Proposal review panel (approve all / reject all / toggle individual). |
| **Dinesh** | Linked Upload — User Profile + Company | Standard | `writing-plans`, `frontend-design`, `design:ux-writing` | Upload → extract name + bio / name + description → review → save. File discarded. BYOK key required. |
| **Dinesh** | Linked Upload — Agent Profile | Standard | `writing-plans`, `frontend-design`, `design:ux-writing` | Upload → extract agent name + generate system prompt (thinking style, communication patterns, principles, expertise) → review + edit → save. File discarded. |
| **Big Head** | Active Memory — periodic background proposals | Standard | `writing-plans` | Every 10 messages, generate proposals server-side and queue them. Proposals presented on next project/agent open. Interval fixed at 10 messages (not user-configurable). |
| **Big Head** | Active Memory — AI-proposed at conversation end | Standard | `writing-plans` | User clicks "end conversation" or starts new conversation → AI reviews full conversation → proposes batch updates → user sees review panel. |
| **Big Head** | Active Memory — token cap enforcement | Standard | `writing-plans`, `data:sql-queries` | Hard cap: ≤1000 tokens (project), ≤500 tokens (agent instance). Write rejected if cap exceeded. Error: "Memory is full ([current]/[max] tokens)." No auto-prune. |
| **Big Head** | Active Memory — entry structure | Standard | `writing-plans`, `data:sql-queries` | Individual rows with `created_at` + `source_conversation_id` (nullable for user-authored). Not a blob. |
| **Jìan** | Framework selection pipeline evals | Complex | `writing-plans`, `data:statistical-analysis`, `data:data-validation` | Eval set: known queries → expected framework matches. Precision/recall on top-5 candidates. Reranker correctness. |
| **Jìan** | Active Memory tests | Standard | `writing-plans`, `data:data-validation` | Triple-trigger coverage, token cap enforcement, proposal queue persistence, entry CRUD |
| **Jìan** | Linked Upload tests | Standard | `writing-plans`, `data:data-validation` | All 3 surfaces, BYOK gate, file-discarded-after-extraction assertion, partial extraction handling |
| **Jared** | MCP spec — finalize | Fast | `product-management:feature-spec` | Confirm per-request scoping table, access control rules, rate limiting defaults |
| **Jared** | Admin RAG Debug spec | Standard | `product-management:feature-spec`, `anthropic-skills:user-story` | Ship by end of W5 |

**Dependencies in:** AgentInstance entity live (Sprint 4 Dinesh). Context stack Layers 5–7 live (Sprint 4 Big Head).

**Handoffs out:**
- Active Memory entries now feed into Layers 4 and 6 of the live context stack.
- Linked Upload agent surface unlocks full thought leader agent flow.

---

## Sprint 6 — MCP + Framework Library UI + Admin Completion

**Goal:** MCP server live (users can connect Claude Desktop/Cursor). Framework Library fully manageable via UI. Admin panel complete (LLM Models, RAG Debug). Security audit done.

| Agent | Feature / Work | Tier | Skills | Notes |
|---|---|---|---|---|
| **Gilfoyle** | ADR: MCP server architecture + auth | Standard | `writing-plans`, `data:sql-queries` | Bearer token auth, per-user daily rate limiting, per-request scoping validation, access control checks |
| **Gilfoyle** | Security audit: BYOK key storage + retrieval | Standard | `writing-plans` | AES-256-GCM at rest, never returned decrypted, server-memory-only during LLM call, masked in frontend |
| **Gilfoyle** | Code review Sprint 5 Active Memory + Linked Upload | Standard | — | Review proposal queue persistence and BYOK key handling in background jobs |
| **Dinesh** | Framework Library UI | Complex | `writing-plans`, `frontend-design`, `design:ux-writing`, `design:accessibility-review` | Browse (table with name, category, confidence, trigger count). Edit individual framework (inline form). Delete. JSON upload (merge behavior: matching `id` = update, new = add, missing = retain). Per-framework validation errors displayed. |
| **Dinesh** | MCP token management UI | Standard | `writing-plans`, `frontend-design`, `design:ux-writing` | Generate token (User Profile page). Multiple tokens (one per external client). Revoke individually. Token shown once on generation, then masked. |
| **Dinesh** | Admin RAG Debug tab | Standard | `writing-plans`, `frontend-design` | Retrieval traces for recent queries: chunks retrieved, scores, reranking results, gating decisions. Admin-only. Read-only diagnostic. |
| **Big Head** | MCP server — context assembly per scoping parameters | Complex | `writing-plans`, `data:sql-queries` | Per-request `project_id` / `agent_id` / `company_id` params. Assembly per scoping table in PRD §11. Runs: query embedding, RAG vector search (L8 + L9), framework selection pipeline (L7). Returns assembled context — no generation. Platform-owned key for all pipeline ops. |
| **Big Head** | MCP rate limiting | Standard | `writing-plans` | Per-user daily cap (default 1,000 req/day). HTTP 429 + `Retry-After` + `X-RateLimit-Remaining` / `X-RateLimit-Reset` headers. Admin-configurable per-user. |
| **Big Head** | MCP access control | Standard | `writing-plans` | Validate per-parameter: user owns/can-access requested project, agent, company. Reject with 403 on failure. Respect `private` vs `public` agent visibility. |
| **Jìan** | Active Memory + Linked Upload evals | Complex | `writing-plans`, `data:statistical-analysis`, `data:data-validation` | Memory quality evals: do proposals match conversation content? Linked upload evals: extraction accuracy across doc types. |
| **Jìan** | MCP tests | Standard | `writing-plans`, `data:data-validation` | All scoping combinations, rate limiting (429 on exceed), access control (private agent rejection), token revocation |
| **Jìan** | Framework Library UI tests | Standard | `writing-plans`, `data:data-validation` | Upload merge behavior, validation error display, CRUD operations |
| **Jared** | Sprint 7 prep + spec gap audit | Standard | `product-management:feature-spec` | Review all specs for open questions before final sprint |

**Dependencies in:** AgentDefinition + Framework Library data model (Sprint 4 Gilfoyle). Active Memory live (Sprint 5).

**Handoffs out:**
- MCP server live = external clients can connect.
- Framework Library UI complete = agents fully manageable by users.

---

## Sprint 7 — Polish + Integration + Launch Prep

**Goal:** No new features. Harden, test end-to-end, close UI/UX gaps, verify the whole product works as a system.

| Agent | Feature / Work | Tier | Skills | Notes |
|---|---|---|---|---|
| **Gilfoyle** | Final security audit | Complex | `writing-plans` | API key storage, MCP token lifecycle, BYOK in background jobs, admin-only endpoint enforcement |
| **Gilfoyle** | Performance review | Standard | `data:statistical-analysis` | RAG retrieval latency, framework selection pipeline latency, context assembly time at full stack |
| **Gilfoyle** | Code review pass (Sprint 6) | Standard | — | Focus: MCP server, rate limiting, access control |
| **Dinesh** | Agent switch UI polish | Standard | `frontend-design`, `design:ux-writing`, `design:accessibility-review` | Visual indicators per-message (`agent_id` tag → show agent name marker in chat). Deactivate agent UX. |
| **Dinesh** | Document status UI | Standard | `writing-plans`, `frontend-design`, `design:ux-writing` | Per-document ingestion progress: `pending → extracting → chunking → embedding → completed`. Failed stage shown with retry button. |
| **Dinesh** | Model selector greyed-out states | Fast | `design:ux-writing` | Models without matching BYOK key visible but disabled. Tooltip: "Add an API key to enable." |
| **Dinesh** | KB organization — folders + tags UI | Standard | `writing-plans`, `frontend-design`, `design:ux-writing` | User-created folders, tag management, AI auto-suggest tags on upload. |
| **Big Head** | Document ingestion retry UX | Standard | `writing-plans` | After 3 auto-retry failures, mark `failed`. User "Retry" button re-triggers from failed stage (not from scratch). Admin view: all failed documents across users. |
| **Big Head** | AI auto-suggest tags on KB upload | Standard | `writing-plans` | On document ingestion complete, generate suggested tags + metadata via LLM (BYOK key, lightweight call). Present suggestions to user for approval. |
| **Big Head** | Background job hardening | Standard | `writing-plans` | Ensure BackgroundTasks wrapper is thin enough for Celery/RQ migration in one-file change. Verify no state leakage between jobs. |
| **Jìan** | End-to-end integration tests | Complex | `writing-plans`, `data:data-validation` | Full user journey: sign up → profile → company → project → agent → conversation → KB upload → generation with all 9 layers → active memory write → MCP access |
| **Jìan** | Eval suite finalization | Standard | `data:statistical-analysis`, `data:data-validation` | Framework selection, active memory quality, linked upload extraction, RAG retrieval precision |
| **Jìan** | Security test coverage | Standard | `writing-plans`, `data:data-validation` | BYOK key not returned in responses, MCP access control, admin-only routes, token revocation |
| **Jared** | MVP launch checklist | Fast | — | Verify all MVP entities shipped, all deferred features confirmed not present, all Open Questions resolved |

**Dependencies in:** All previous sprints complete.

**Handoffs out:** Kinetic MVP ships.

---

## Cross-Sprint Dependency Map

```
Sprint 1: db-schema-spec.md ──────────────────────────────────────────── unlocks all
Sprint 1: Auth + ingestion pipeline
          │
Sprint 2: RAG retrieval pipeline ─────────────────── feeds Sprint 3 KB injection
Sprint 2: User Profile (API keys) ────────────────── feeds Sprint 3 BYOK routing
          │
Sprint 3: Generation engine (Layers 1–4 + 8) ──────── feeds Sprint 4 agent injection
Sprint 3: Conversation entity
          │
Sprint 4: AgentDefinition/AgentInstance ─────────────── feeds Sprint 5 Active Memory
Sprint 4: Framework selection pipeline (L7) ──────────── feeds Sprint 6 MCP pipeline
Sprint 4: Context stack Layers 5–7 + 9
          │
Sprint 5: Active Memory (Layers 4 + 6 live) ──────────── Sprint 5 compounds context
Sprint 5: Linked Upload
          │
Sprint 6: MCP server ────────────────── external clients can connect
Sprint 6: Framework Library UI ──────── agents fully manageable
          │
Sprint 7: Hardening → launch
```

---

## Deferred (Post-MVP, V1 Roadmap)

These are confirmed out of MVP scope. Do not re-flag them.

| Feature | Deferred decision |
|---|---|
| Thought Stream | Deferred post-MVP. Active Memory covers core memory job. |
| Contact entity | Depends on Thought Stream. |
| Cross-company retrieval opt-in | Depends on Thought Stream. |
| Agent `shared` visibility | Private/public covers MVP. |
| Agent permissions (owner/editor/invoker) | Depends on shared visibility. |
| Agent transparency (transparent/opaque) | Needed for marketplace. |
| Multi-agent conversations | Post-MVP. One agent at a time in MVP. |
| RAG V1 enhancements | Config-flag stubs shipped in Sprint 2. Enable post-MVP. |
| Semantic chunking | Config-flag stub. Enable post-MVP. |
| Active Memory write-back via MCP | MCP is read-only in MVP. |
| Multiple BYOK keys per provider | One per provider in MVP. |

---

## Open Questions

_None open as of 2026-03-21. All prior open questions resolved — see `MEMORY.md` and `docs/prd.md` § Open Questions._
