# Kinetic — Decisions Archive

_Archived from MEMORY.md on 2026-03-28. These are locked decisions that rarely need to be referenced during implementation. Consult when touching a decision boundary._

---

## Key Decisions Locked

| Date | Decision |
|---|---|
| 2026-03-20 | Web app (not desktop). In-app project spaces called "Projects" — no local folder sync in V1. |
| 2026-03-20 | Agents are manually invoked personas (system prompt + RAG). No autonomous or scheduled agents in V1. |
| 2026-03-20 | Thought leader flow: upload corpus → auto-generate system prompt → user edits → RAG index. |
| 2026-03-20 | Multi-company support from the start. One active company at a time. Targets consultants and founders. |
| 2026-03-20 | Knowledge Base is a first-class entity. Supports folders + tags. AI auto-suggests tags and metadata on upload. Attached to Project or AgentDefinition. |
| 2026-03-20 | Framework is a first-class entity attached to AgentDefinition. Named reasoning tools extracted from thought leader corpus (or user-authored). Classifier-selected at query time and injected whole — never chunked. User can override via AgentInstance. Auto-extracted in V1 via extraction script; UI management in product. |
| 2026-03-20 | Framework schema refined after test run: `when_to_apply` is an array of discrete trigger phrases (not prose). Added fields: `id` (stable unique), `category` (domain tag), `example_application` (concrete scenario), `related_frameworks` (links between frameworks). Pass 1 prompt tightened to exclude checklists, build guides, process templates, and product-specific patterns. |
| 2026-03-20 | Framework category list is OPEN (not closed). Users create agents with different backgrounds/expertise, so categories grow organically. Category is for browsing/admin, not runtime matching. |
| 2026-03-20 | Framework selection is a 4-step pipeline: (1) embedding similarity on per-trigger vectors, (2) trigger-count boost for tie-breaking (frameworks where multiple triggers score above threshold get boosted — replaces original category-match boost; KIN-302), (3) LLM reranker (Haiku) on top-5 for precision, (4) inject winner whole. No vector DB needed at current scale (~750 vectors max). |
| 2026-03-20 | Distribution: SaaS. |
| 2026-03-21 | Three-tier memory architecture (full V1): Active Memory + Thought Stream + Knowledge Base. MVP ships with two tiers: Active Memory + Knowledge Base. Thought Stream deferred to post-MVP. |
| 2026-03-21 | Agent split into AgentDefinition (shared blueprint: system prompt, KB, frameworks) and AgentInstance (per-user state: active memory, framework overrides). |
| 2026-03-21 | AgentDefinition visibility: MVP = `private`/`public` toggle (private default). Post-MVP adds `shared` (explicit invokers). |
| 2026-03-21 | MCP agent access: AgentDefinitions exposed via MCP for external AI clients (Claude, ChatGPT, Cursor). Exposes system prompt + KB (RAG) + frameworks (selection pipeline). Does NOT expose AgentInstance data (active memory). Read-only — no write-back to Kinetic. Per-user connector URLs, revocable. |
| 2026-03-21 | BYOK (Bring Your Own Key): Users provide their own API keys for LLM providers — Anthropic, OpenAI, Google, Groq. Keys encrypted at rest. BYOK keys used for generation only — embedding and pipeline LLM calls use platform-owned keys. |
| 2026-03-21 | Per-query model selection: Users choose which model to use per query via a UI selector. Default model set in user profile. Context stack is model-agnostic. |
| 2026-03-21 | Agent Profile page: shows agent instructions (system prompt), knowledge base (browse/upload docs), and framework library (browse/edit/add/delete). |
| 2026-03-21 | All agents transparent in MVP — no transparency setting needed. Opaque option deferred to marketplace. |
| 2026-03-21 | Framework upload flow for MVP: extraction runs outside Kinetic (separate script). User uploads the resulting structured JSON file into the agent's framework library. No in-app extraction pipeline in MVP. |
| 2026-03-21 | User profile simplified for MVP: Name + short bio (optional) + API keys + default model. Full structured fields (background, working style, strengths) deferred. |
| 2026-03-21 | Company profile simplified for MVP: Name + short description (optional). Full structured fields deferred. |
| 2026-03-21 | Conversation entity added: belongs to Project, has messages, timestamped. Displayed in left column (Claude-style chat history). |
| 2026-03-21 | Admin section in MVP: user registration and user management. Registration is email-only, auto-created. Login via Google OAuth only. No magic link (unreliable on free Supabase tier), no passwords in MVP. |
| 2026-03-21 | Admin LLM Models tab: manages model library across three categories (generation, embedding, reranking). Only `generation` models are user-facing in MVP. In-memory cache + DB persistence; client-side pub/sub for instant UI updates; per-entity override pattern; admin-only API with audit logging. See `docs/prd.md §1`. |
| 2026-03-21 | AgentInstance data is private to the invoking user. Definition owner cannot see aggregate instance data. |
| 2026-03-21 | Active Memory write UX: dual-trigger — user-initiated ("save to memory") + AI-proposed batch at conversation end with user approval. No automatic writes. Deferred proposals queued for next visit. |
| 2026-03-21 | Conversation scope: two levels — project conversations (full 9-layer stack) and company conversations (Layers 1–2 + agent layers if invoked, no project context). |
| 2026-03-21 | Agent invocation: side panel toggle, one agent at a time in MVP. User can switch mid-conversation. Multi-agent post-MVP. |
| 2026-03-21 | Company ↔ Project: auto-set to active company at creation, changeable later. |
| 2026-03-21 | Agent corpus scope: one corpus per agent. Blended perspectives via separate agents. |
| 2026-03-21 | MCP authentication: revocable bearer token, generated per-user in-app, passed as header. MCP generation handled by external client — Kinetic returns context only. Server-side pipeline calls (framework reranker, query embedding) use platform-owned key — no BYOK required for MCP pipeline. |
| 2026-03-21 | MVP context stack is 9 layers (no Thought Stream). User bio 500–1000 chars. |
| 2026-03-21 | LLM client abstraction (e.g., LiteLLM) required to normalize Anthropic/OpenAI/Google/Groq APIs into a single interface. Enables BYOK + per-query model switching without per-provider integration paths. |
| 2026-03-21 | Background processing: in-process (FastAPI BackgroundTasks) for MVP. Gilfoyle to add thin abstraction layer so migration to Celery/RQ later is a one-file change. |
| 2026-03-21 | PRD written. See `docs/prd.md`. |
| 2026-03-21 | Frontend stack locked: Next.js 14 (App Router) + TypeScript + Radix UI + shadcn/ui + Tailwind CSS. Same stack as FounderPanel for code reuse. |
| 2026-03-21 | Vector DB: pgvector (Supabase extension) for MVP. Qdrant is a migration option later if scale demands. Current scale (~5 users, ~2M words) is well within pgvector limits. |
| 2026-03-21 | Codebase lineage: Kinetic implementation ports components from FounderPanel (`/Users/brandonupchuch/Projects/founder_panel`). Backend: LLM client, auth, model settings, RAG pipeline (Qdrant→pgvector), ingestion, chat service. Frontend: shadcn components, API client, SSE proxy, admin panel structure. |
| 2026-03-21 | Conversation history in prompt: recent messages sit between context layers (1–7) and current message. Rolling summary compression for older messages to manage context window. |
| 2026-03-21 | SSE auth: frontend proxies SSE through Next.js server route to inject JWT (EventSource limitation). Backend accepts token via query param or header. |
| 2026-03-21 | Document ingestion retry: auto-retry up to 3x with exponential backoff per stage. After 3 failures, user sees retry button. Admin can view failed docs across all users. |
| 2026-03-21 | Admin RAG Debug tab: retrieval traces for recent queries (chunks retrieved, scores, gating decisions). Admin-only diagnostic tool. |
| 2026-03-21 | Embedding key: platform-owned OpenAI key for `text-embedding-3-large`. Users not charged for embedding or pipeline LLM calls. BYOK is generation-only. |
| 2026-03-21 | MVP RAG retrieval: zero LLM calls. Embed query → vector search → MMR → similarity threshold → cite → inject. Full V1 enhancements (query rewriting, FTS, LLM reranking, recency scoring) addable via config flags. See `docs/rag-architecture.md`. |
| 2026-03-21 | MVP ingestion: extract → fixed-size chunking (~500 tokens, ~50 overlap) → embed → index. No chunk enrichment, no semantic chunking in MVP. V1 enhancements via config flags. |
| 2026-03-21 | Active Memory overflow: hard cap, write rejected with error, user must prune. Token count shown in editor. |
| 2026-03-21 | Model selector UX: shows all admin-enabled models; models without matching user key are visible but disabled (greyed out). |
| 2026-03-21 | Framework reranker + RAG query embedding use platform-owned key. Only per-query LLM call in MVP pipeline is Haiku reranker for framework selection (~50 tokens). |
| 2026-03-21 | Linked upload extended to Agent Profile page: upload corpus → AI generates agent name + system prompt → user reviews/edits → saves. See `docs/feature-linked-upload.md`. |
| 2026-03-21 | Linked upload + conversation compression use BYOK key (user's default model or first available). Linked upload gated on having at least one API key configured. |
| 2026-03-21 | RAG_MAX_TOKENS: dynamic percentage of selected model's context window. Gilfoyle to determine percentage + minimum floor. |
| 2026-03-21 | Active Memory write UX: triple-trigger — user-initiated, AI-proposed at explicit conversation end, periodic background generation every N messages. No browser unload dependency. |
| 2026-03-21 | Framework upload: merge behavior (matching `id` = update, new = add, missing = retain). Per-framework validation with partial import. Format matches extraction script output. |
| 2026-03-21 | MCP rate limiting: per-user daily cap (default 1,000 req/day), liberal, admin-configurable. HTTP 429 on exceed. |
| 2026-03-21 | Agent switch preserves full conversation history. Messages tagged with `agent_id` for UI markers. |
| 2026-03-21 | PRD pre-execution review complete. All 12 issues resolved. See `docs/prd.md` Decisions Locked table. |
| 2026-03-21 | AgentDefinition update propagation: immediate — all invokers get updated system prompt + frameworks on next query. No versioning in MVP. Revisit when `shared` visibility ships. |
| 2026-03-21 | Project company reassignment: everything moves — conversations, Active Memory, and KB all transfer to the new company. |
| 2026-03-21 | API keys per provider: one per provider (Anthropic, OpenAI, Google, Groq). Multiple keys per provider deferred. |
| 2026-03-21 | PRD approved. See `docs/prd.md`. |
| 2026-03-21 | KB upload size limits: 25 MB per document, 1M token ingestion limit per document (mirrors FounderPanel). No per-KB/per-user storage quota in MVP. |
| 2026-03-21 | User disable: admin must transfer ownership of public agents before disabling a user. Disable blocked until agents transferred or set to private. |
| 2026-03-21 | Conversation soft-delete in MVP. Hidden from sidebar, retained in DB. No hard-delete. |
| 2026-03-21 | Periodic memory proposal interval: fixed at every 10 messages. Not user-configurable in MVP. |
| 2026-03-21 | Conversation compression fallback: truncate oldest messages without summarization on BYOK key failure. Notify user inline. |
| 2026-03-21 | Active Memory entries are individual rows with `created_at` + `source_conversation_id`. Not a single text blob. |
| 2026-03-21 | MVP MCP access for public agents: any authenticated user can access. Private agents = owner only. Full permissions model ships with `shared` visibility post-MVP. |
| 2026-03-22 | Document deletion: soft-delete with deferred cleanup. `deleted_at` timestamp; chunks cleaned up after 7 days. |
| 2026-03-22 | RAG token budget split: dynamic score-based (rank all chunks by similarity, fill greedily). No fixed ratio. |
| 2026-03-22 | RAG_MAX_TOKENS: 15% of selected model's context window, minimum floor 2048 tokens. |
| 2026-03-22 | Background tasks: TaskDispatcher protocol + FastAPITaskDispatcher. Migration to Celery/RQ = one-file swap. |
| 2026-03-22 | Text extraction: `unstructured` library (covers all 12 PRD formats). See ADR-001. |
| 2026-03-22 | DB schema spec written. 21 tables. See `docs/db-schema-spec.md`. |
| 2026-03-22 | ADR-001 written. Stack locked. See `docs/adr-001-infrastructure-choices.md`. |
| 2026-03-22 | ADR-002 written. RAG retrieval pipeline architecture documented. Zero-LLM MVP path, MMR config rationale, RAG_MAX_TOKENS formula, V1 enhancement enablement order. See `docs/adr-002-rag-retrieval-pipeline.md`. |
| 2026-03-22 | ADR-003 written. AgentDefinition/AgentInstance architecture: two-table split, auto-creation, immediate propagation, JSONB overrides, framework trigger embeddings, bcrypt MCP tokens, generate-instructions flow, bulk upload merge. See `docs/adr-003-agents-architecture.md`. |
| 2026-03-22 | Conversation title generation uses BYOK key (user's default model). If no key configured, title stays null — renders as "New conversation". No platform key used. |
| 2026-03-23 | Linked upload extraction endpoints (`/api/{company,agent}/{id}/upload-document`) do NOT validate ownership of the path param. Intentional: endpoint is compute-only (no DB write, no read of protected data). Ownership is validated by the save PATCH endpoint. Sprint 4 agent save endpoint must enforce ownership check. |
| 2026-03-23 | Development workflow changed from parallel-autonomous to sequential-supervised. One implementation agent at a time, Brandon coordinates, agents check in after each ticket. Gilfoyle review is a hard gate. Pre-implementation spec check mandatory. See `conventions.md § Development Workflow Model` and `linear-workflow.md § Session Start`. |
| 2026-03-24 | MCP access control uses 404 for cross-tenant denials (anti-enumeration). No 403. Spec §6 updated. Approved by Gilfoyle + Brandon. |
| 2026-03-24 | MCP framework selection is 3-step for MVP (embed → boost → gate). Haiku reranker (step 3 of full pipeline) deferred — add when usage data shows mis-selection. Spec §4.4 updated. |
| 2026-03-24 | Framework library curated from 383 → 184 (ICP-relevant only). Cut all AI-technical content. File: `nbj_extractor/frameworks_curated.json`. See `research/2026-03-24-framework-injection-format-research.md` for injection format evidence. |
| 2026-03-24 | Framework enrichment tickets created: KIN-351 (user-language triggers, P0), KIN-352 (nate_would_say + guidance, P0), KIN-353 (Nate system prompt, P0 — Jared), KIN-354 (collision pair triggers, P1), KIN-357 (stepless enrichment, P1), KIN-356 (scaffold schema migration, P2). |

**Decisions deferred to post-MVP (still in V1 roadmap):**

| Decision | Status |
|---|---|
| Thought Stream (pgvector ambient capture) | Deferred post-MVP |
| Contact entity (relationship context under Company) | Deferred post-MVP |
| Cross-company retrieval opt-in on agent instances | Deferred post-MVP (depends on Thought Stream) |
| Agent `shared` visibility tier | Deferred post-MVP |
| Agent permissions (owner/editor/invoker) | Deferred post-MVP (depends on shared visibility) |
| Agent transparency (transparent/opaque) | Deferred post-MVP |

---

## Doc Index

| Doc | Location | Status |
|---|---|---|
| Product Brief | `docs/product-brief.md` | Draft (updated 2026-03-21) |
| Jobs to Be Done | `docs/jobs-to-be-done.md` | Draft (updated 2026-03-21) |
| Domain Model | `docs/domain-model.md` | Draft (updated 2026-03-21) |
| MVP Scope | `docs/mvp-scope.md` | Draft (new 2026-03-21) |
| RAG Architecture | `docs/rag-architecture.md` | Draft (new 2026-03-21) |
| Feature: Linked Upload | `docs/feature-linked-upload.md` | Draft (new 2026-03-21) |
| Memory System Spec | `docs/memory-system-spec.md` | Not started |
| PRD | `docs/prd.md` | Approved (2026-03-21) |
| Active Memory Spec | `docs/specs/active-memory-spec.md` | Draft (new 2026-03-22) |
| DB Schema Spec | `docs/db-schema-spec.md` | Draft (new 2026-03-22) |
| ADR-001: Infrastructure | `docs/adr-001-infrastructure-choices.md` | Proposed (new 2026-03-22) |
| ADR-002: RAG Retrieval Pipeline | `docs/adr-002-rag-retrieval-pipeline.md` | Proposed (new 2026-03-22) |
| ADR-003: Agents Architecture | `docs/adr-003-agents-architecture.md` | Proposed (new 2026-03-22) |
| ADR-006: MCP Server | `docs/adr-006-mcp-server.md` | Accepted (2026-03-23) |
| MCP Spec | `docs/specs/mcp-spec.md` | Approved (updated 2026-03-24) |
| Admin RAG Debug Tab Spec | `docs/specs/rag-debug-tab-spec.md` | Approved (2026-03-24) |
| Generation Engine Spec | `docs/specs/generation-engine-spec.md` | Draft (new 2026-03-26) |
| Build Order | `docs/build-order.md` | Draft (2026-03-21) |
| Sprint 1 Plan | `docs/plans/2026-03-21-sprint1-foundation.md` | Active (new 2026-03-22) |
| Framework MVP Strategy | `nbj_extractor/framework-mvp-strategy.md` | Draft — not executed (2026-03-23) |
| Framework Extraction Learnings | `nbj_extractor/LEARNINGS.md` | Active (updated 2026-03-23) |
| Framework Defect Log | `nbj_extractor/defect-log.md` | Active (2026-03-23) |
