# MEMORY.md — Kinetic MVP

Living decisions log. Append-only. Entries are dated and attributed.

---

## Doc Index

| File | Description | Owner | Status |
|------|-------------|-------|--------|
| `docs/prd.md` | Product Requirements Document — full MVP scope | Jared | Active |
| `docs/domain-model.md` | Domain model — all entities and relationships | Jared | Active |
| `docs/db-schema-spec.md` | Canonical DB schema — 21 tables, full column definitions | Gilfoyle | Active |
| `docs/rag-architecture.md` | RAG retrieval pipeline architecture | Gilfoyle | Active |
| `docs/adr-001-infrastructure-stack.md` | ADR-001: Infrastructure stack (Supabase, pgvector, FastAPI, Next.js 14, LiteLLM) | Gilfoyle | Active |
| `docs/adr-002-rag-retrieval-pipeline.md` | ADR-002: RAG retrieval pipeline architecture | Gilfoyle | Active |
| `docs/adr-003-context-stack-generation.md` | ADR-003: Context stack assembly + generation endpoint | Gilfoyle | Active |
| `docs/adr-004-conversation-compression.md` | ADR-004: Conversation history compression thresholds | Gilfoyle | Active |
| `docs/adr-005-agents-framework-selection.md` | ADR-005: AgentDefinition/AgentInstance architecture + framework selection pipeline | Gilfoyle | Active |
| `docs/specs/kin-257-projects-conversations-spec.md` | Projects + Conversations spec | Jared | Active |
| `docs/specs/agents.md` | Agents spec (AgentDefinition + AgentInstance) | Jared | Active |
| `docs/specs/active-memory-spec.md` | Active Memory spec — triple-trigger, token caps, CRUD API | Jared | Active |
| `docs/specs/mcp-spec.md` | MCP server spec — auth, scoping, rate limiting, token UI | Jared | Active |
| `docs/feature-linked-upload.md` | Linked Upload feature doc (all three surfaces) | Jared | Active |
| `docs/specs/framework-library-spec.md` | Framework Library spec — browse, edit, delete, JSON upload merge | Jared | Active |
| `docs/specs/linked-upload-spec.md` | Linked Upload spec — all three surfaces (User Profile, Company, Agent) | Jared | Active |

---

## Locked Decisions

### Infrastructure (2026-03-22)

- **Database:** Supabase (PostgreSQL + pgvector). Not Qdrant at MVP scale.
- **Backend:** FastAPI (Python 3.11+). Port from FounderPanel patterns.
- **Frontend:** Next.js 14 (App Router). Tailwind + shadcn/ui.
- **LLM routing:** LiteLLM. Handles BYOK key injection and model normalization.
- **Background tasks:** FastAPI BackgroundTasks (in-process). Celery/RQ post-MVP via abstraction layer.
- **Auth:** Supabase Auth (JWT). RLS on all tables.

### RAG pipeline (2026-03-22)

- Zero-LLM retrieval path in MVP: embed → cosine similarity → MMR → threshold → cite → inject.
- No query expansion or HyDE at MVP scale.
- Similarity threshold: 0.75. MMR lambda: 0.7. Top-k: 5.

### Conversation compression (2026-03-22)

- Rolling summary compression triggered when message count exceeds threshold.
- Threshold, verbatim window, and model choice locked in ADR-004.

### Context stack (2026-03-21)

- 9-layer assembly. Sprint 3 activates L1–L4 + L8. Sprint 4 activates L5–L7 + L9.
- Layer ordering locked in ADR-003.
- SSE auth: frontend proxies SSE through Next.js server route to inject JWT (EventSource limitation). Backend accepts token via query param or header.

### Agents (2026-03-22)

- AgentDefinition/AgentInstance entity split. AgentDefinition = shared blueprint. AgentInstance = per-user runtime state, auto-created on first invocation.
- Agent visibility: private (owner only) or public (any authenticated user).
- Agent types: custom, thought_leader.
- One agent active per conversation at a time in MVP.
- Agent switch preserves full conversation history. Messages sent before activation have no agent scope in metadata.
- Framework selection: 4-step pipeline at query time. Output is single best-matching framework, injected whole as L7.

### Active Memory (2026-03-22)

- Triple-trigger write system locked in active-memory-spec.md.
- Token cap enforced at write time. Char-proxy method (ceil(chars/4)).
- Proposal queue: background job, per-conversation, debounced.

### Framework Library (2026-03-21)

- Framework upload: merge behavior — matching `id` = update, new = add, missing = retain.
- Per-framework enable/disable toggle.
- JSON upload is the primary authoring surface in MVP.

### MCP (2026-03-21)

- Kinetic operates as MCP **server**. External clients (Claude Desktop, Cursor) drive generation.
- MCP returns assembled context only — no generation.
- Auth: bearer token per user, generated in-app. Multiple tokens per user, individually revocable.
- Scoping params: `project_id`, `agent_id`, `company_id` — optional and combinable.
- Platform embedding key used for MCP RAG calls (not BYOK), regardless of user BYOK settings.
- AgentInstance active memory (L6) is excluded from MCP context in MVP.
- Rate limit: 1,000 req/user/day (default). Admin-configurable per user.
- MCP token UI lives in User Profile → MCP Tokens section.
- Ships Sprint 6. Spec (KIN-286) gates Gilfoyle ADR in Sprint 5.

### Project company reassignment (2026-03-22)

- Block reassignment if project has any content (conversations, Active Memory, KB documents).

---

## Sprint Log

| Sprint | Focus | Status |
|--------|-------|--------|
| Sprint 1 | Infrastructure, auth, KB ingestion pipeline | Done |
| Sprint 2 | Admin panel, Company CRUD, Project CRUD | Done |
| Sprint 3 | Conversations, generation engine, context stack L1–4+8 | In Progress |
| Sprint 4 | Agents (AgentDefinition CRUD, AgentInstance, invocation UI), framework selection, context stack L5–7+9 | Planned |
| Sprint 5 | Active Memory, Linked Upload | Planned |
| Sprint 6 | MCP server, Framework Library UI | Planned |
