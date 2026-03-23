# Sprint 1 — Foundation: Port + Schema — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver the canonical DB schema spec and infrastructure ADR that unlock all Sprint 1 implementation work. Resolve pending architecture decisions. Create and hand off Linear tickets for Dinesh, Big Head, Jìan, and Jared.

**Architecture:** Gilfoyle owns two artifacts (db-schema-spec.md, ADR-001) and five pending decisions from `docs/prd.md` § Decisions Needed. Schema spec covers all MVP entities (~15 tables). ADR locks the stack choices already made in PRD sessions — formalizes them with tradeoff analysis.

**Tech Stack:** Supabase (PostgreSQL 15 + pgvector + Auth + Storage), FastAPI (Python 3.11+), Next.js 14 (App Router + TypeScript), LiteLLM, shadcn/ui + Radix UI + Tailwind CSS.

---

## Task 1: Resolve Pending Architecture Decisions

Before writing the schema or ADR, resolve the five open decisions from `docs/prd.md` § Decisions Needed. Document each decision in the schema spec or ADR as appropriate.

**Decisions to make (with recommended positions):**

### 1a. Document deletion strategy
- **Decision:** Soft-delete with deferred cleanup.
- **Rationale:** Consistent with conversation soft-delete (PRD §5). Add `deleted_at` (nullable timestamp) to `knowledge_base_documents`. Chunks remain until a scheduled cleanup job removes them (batch, off-peak). Soft-delete is reversible; hard-delete of chunks is expensive (HNSW reindex).
- **Document in:** `db-schema-spec.md` (schema pattern) + ADR-001 (as a consequence).

### 1b. RAG token budget split (Project KB vs Agent KB)
- **Decision:** Dynamic split based on retrieval scores, not a fixed ratio.
- **Rationale:** Fixed splits waste budget when one scope has no results. Score-based: rank all chunks from both scopes by similarity, fill budget greedily from the top. Simple, adaptive, no config needed.
- **Document in:** `db-schema-spec.md` § Configuration Parameters note.

### 1c. RAG_MAX_TOKENS — percentage + floor
- **Decision:** 15% of selected model's context window, minimum floor 2,048 tokens.
- **Rationale:** At 200K context (Claude), 15% = 30K tokens — generous. At 8K context (small models), 15% = 1,200 — below floor, so floor kicks in at 2,048. Prevents RAG from starving deterministic layers on small models or flooding on large ones.
- **Document in:** `db-schema-spec.md` § Configuration Parameters + ADR-001.

### 1d. Background task dispatch abstraction
- **Decision:** Thin `TaskDispatcher` protocol with `dispatch(func, *args)` interface. MVP impl: `FastAPITaskDispatcher` wrapping `BackgroundTasks`. Migration to Celery/RQ = swap one class.
- **Rationale:** PRD requires "one-file change" migration path. A protocol + single implementation achieves this without over-engineering.
- **Document in:** ADR-001 (infrastructure pattern).

### 1e. Text extraction library
- **Decision:** `unstructured` (Python library) for PDF, DOCX, PPTX, XLSX, CSV, TXT, MD, RTF, JSONL.
- **Rationale:** Single library covers all 12 formats in the PRD. Alternative: per-format libraries (pdfplumber + python-docx + python-pptx + openpyxl) — more control but 4x integration surface. `unstructured` is the standard for document ETL in RAG pipelines. FounderPanel used per-format libs; Kinetic can consolidate.
- **Document in:** ADR-001 (dependency choice).

**Step 1:** Draft the five decisions above as structured entries.
**Step 2:** Get Brandon's approval on all five before proceeding to Task 2.

---

## Task 2: Write `docs/db-schema-spec.md`

The canonical schema for all MVP entities. Every table, column, type, constraint, index, and RLS policy. Single source of truth — no other doc defines DDL.

**Reference docs:**
- `docs/prd.md` — entity definitions, field lists, all §§
- `docs/domain-model.md` — relationships, attributes
- `docs/rag-architecture.md` — chunk/document tables, index strategy, debug logs
- `docs/feature-linked-upload.md` — no schema impact (extraction is transient)
- `projects/kinetic/MEMORY.md` — locked decisions

**Tables to define (in dependency order):**

| # | Table | Source | Notes |
|---|---|---|---|
| 1 | `users` | PRD §1–2 | Supabase Auth `auth.users` + custom `public.users` profile table |
| 2 | `user_api_keys` | PRD §2 | One row per provider per user. AES-256-GCM encrypted `key_ciphertext`. Never returned decrypted. |
| 3 | `companies` | PRD §3 | `user_id` FK. `name`, `description`. |
| 4 | `projects` | PRD §4 | `company_id` FK. `name`, `instructions`, `company_id`. |
| 5 | `conversations` | PRD §5 | `project_id` (nullable), `company_id`, `user_id`. `deleted_at` for soft-delete. |
| 6 | `messages` | PRD §5, §10 | `conversation_id` FK. `role` (user/assistant/system), `content`, `agent_id` (nullable), `model_id`. |
| 7 | `conversation_summaries` | PRD §10 | Rolling compression. `conversation_id` FK, `summary_text`, `messages_covered_up_to`. |
| 8 | `agent_definitions` | PRD §6 | `owner_id`, `name`, `instructions`, `type` (custom/thought_leader), `visibility` (private/public). |
| 9 | `agent_instances` | PRD §6 | `user_id` + `agent_definition_id` (unique together). Auto-created on first invocation. |
| 10 | `knowledge_bases` | PRD §7 | Polymorphic parent: `project_id` (nullable) XOR `agent_definition_id` (nullable). Check constraint. |
| 11 | `knowledge_base_folders` | PRD §7 | `knowledge_base_id` FK, `name`, `parent_folder_id` (self-ref for nesting). |
| 12 | `knowledge_base_documents` | RAG arch | Full column set from `docs/rag-architecture.md` § Storage. Add `deleted_at`, `folder_id`, `tags`. |
| 13 | `knowledge_base_chunks` | RAG arch | Full column set from `docs/rag-architecture.md` § Storage. Scoping columns. HNSW index. |
| 14 | `frameworks` | PRD §8, domain model | `agent_definition_id` FK. All fields from domain model § Framework. JSONB for `when_to_apply`, `principles`, `steps`, `source_posts`, `related_frameworks`. |
| 15 | `framework_trigger_embeddings` | Domain model § Framework Selection | One row per trigger phrase per framework. `framework_id`, `trigger_text`, `embedding vector(3072)`. Cosine similarity search target. |
| 16 | `active_memory_entries` | PRD §9 | Polymorphic: `project_id` XOR `agent_instance_id`. `content`, `created_at`, `source_conversation_id` (nullable). |
| 17 | `memory_proposals` | PRD §9 | Queued proposals from periodic/end-of-conversation generation. `conversation_id`, `project_id`/`agent_instance_id`, `proposed_content`, `status` (pending/approved/rejected), `created_at`. |
| 18 | `mcp_tokens` | PRD §11 | `user_id`, `token_hash` (bcrypt — never store plaintext), `name` (user label), `revoked_at`, `created_at`. |
| 19 | `llm_models` | PRD §1 | Admin model library. `provider`, `model_id`, `display_name`, `category` (generation/embedding/reranking), `enabled`, `context_window`, `created_at`. |
| 20 | `retrieval_debug_logs` | RAG arch § Debug | Full column set from RAG arch. Auto-purge after 30 days. |
| 21 | `mcp_rate_limits` | PRD §11 | Per-user daily cap. `user_id`, `date`, `request_count`. Admin override: `mcp_rate_limit_overrides` table or column on `users`. |

**Schema spec document structure:**

```
# Kinetic MVP — Database Schema Specification
## Conventions (naming, types, RLS pattern, soft-delete pattern, audit columns)
## Tables (one H3 per table: columns, constraints, indexes, RLS policy)
## Enums
## Cross-Cutting Patterns (soft-delete, polymorphic ownership, encrypted fields)
## Configuration Parameters
## Migration Notes
```

**Steps:**

**Step 1:** Create `docs/db-schema-spec.md` with header + conventions section.
**Step 2:** Write tables 1–5 (auth + core entities).
**Step 3:** Write tables 6–7 (conversation + messages + summaries).
**Step 4:** Write tables 8–9 (agent definition + instance).
**Step 5:** Write tables 10–13 (knowledge base + documents + chunks + folders).
**Step 6:** Write tables 14–15 (frameworks + trigger embeddings).
**Step 7:** Write tables 16–17 (active memory + proposals).
**Step 8:** Write tables 18–21 (mcp tokens, llm models, debug logs, rate limits).
**Step 9:** Write cross-cutting patterns, enums, config params, migration notes.
**Step 10:** Self-review: cross-reference every entity in `docs/domain-model.md` and every field in `docs/prd.md` against the schema. Flag any gaps.
**Step 11:** Commit: `docs: add canonical db-schema-spec for all MVP entities`

---

## Task 3: Write `docs/adr-001-infrastructure-choices.md`

Formalizes the stack choices already locked in PRD sessions. Uses `templates/adr-template.md`.

**Decisions to lock:**

| Choice | Selected | Alternative considered |
|---|---|---|
| Database | Supabase (PostgreSQL 15 + pgvector) | Standalone Postgres + Qdrant, PlanetScale |
| Vector storage | pgvector (HNSW) | Qdrant (dedicated), Pinecone, Weaviate |
| Backend | FastAPI (Python 3.11+) | Django, Express.js |
| Frontend | Next.js 14 (App Router) + TypeScript | Remix, SvelteKit |
| Component library | Radix UI + shadcn/ui + Tailwind | MUI, Chakra |
| LLM abstraction | LiteLLM | Direct provider SDKs, Vercel AI SDK |
| Background jobs | FastAPI BackgroundTasks (MVP) + TaskDispatcher abstraction | Celery, RQ, Temporal |
| Text extraction | `unstructured` | Per-format libraries (pdfplumber + python-docx + python-pptx) |
| Auth | Supabase Auth (magic link + OAuth) | Auth0, Clerk, custom JWT |
| File storage | Supabase Storage | S3 direct, Cloudflare R2 |

**Steps:**

**Step 1:** Create `docs/adr-001-infrastructure-choices.md` using template.
**Step 2:** Write Context section (FounderPanel lineage, MVP constraints, team of AI agents).
**Step 3:** Write Decision + Alternatives table for each choice.
**Step 4:** Write Consequences (positive, negative, neutral).
**Step 5:** Write Risks + Review Triggers.
**Step 6:** Commit: `docs: add ADR-001 infrastructure choices`

---

## Task 4: Create Linear Tickets for Sprint 1

After schema spec and ADR are written, create Linear tickets per `docs/build-order.md` Sprint 1.

**Tickets to create:**

| Title | Assignee | Labels | Priority | Estimate | blockedBy |
|---|---|---|---|---|---|
| `[Gilfoyle] Write db-schema-spec.md` | Gilfoyle | architecture, Feature | 2 (High) | 3 | — |
| `[Gilfoyle] ADR-001: Infrastructure choices` | Gilfoyle | architecture, Feature | 2 (High) | 2 | — |
| `[Dinesh] Port: Auth service from FounderPanel` | Dinesh | implementation, Feature | 2 (High) | 2 | schema spec |
| `[Dinesh] Port: Frontend scaffold (Next.js App Router, shadcn, admin shell)` | Dinesh | implementation, Feature | 2 (High) | 2 | — |
| `[Big Head] Port: LLM client abstraction (LiteLLM)` | Big Head | implementation, Feature | 2 (High) | 2 | — |
| `[Big Head] Port: Document ingestion pipeline` | Big Head | implementation, Feature | 2 (High) | 3 | schema spec |
| `[Jìan] Auth test coverage` | Jìan | qa, Feature | 3 (Normal) | 2 | auth port |
| `[Jared] Projects + Conversations spec` | Jared | product, Feature | 3 (Normal) | 2 | — |

**Steps:**

**Step 1:** Invoke `linear-automation` skill.
**Step 2:** Look up team ID, status IDs, label IDs, and user IDs.
**Step 3:** Create Gilfoyle tickets (move to `In Progress` — this is current work).
**Step 4:** Create Dinesh, Big Head, Jìan, Jared tickets (set to `Todo`).
**Step 5:** Set `blockedBy` relationships where noted.
**Step 6:** Comment on schema spec ticket: "Starting now. Covers all MVP entities from PRD + domain model + RAG architecture."

---

## Task 5: Update MEMORY.md

After all deliverables are complete, update `projects/kinetic/MEMORY.md` with new decisions.

**Entries to add:**
- Document deletion: soft-delete + deferred cleanup
- RAG token budget: dynamic score-based split
- RAG_MAX_TOKENS: 15% of context window, floor 2048
- Background tasks: TaskDispatcher protocol
- Text extraction: `unstructured` library
- Schema spec written — see `docs/db-schema-spec.md`
- ADR-001 written — see `docs/adr-001-infrastructure-choices.md`

**Step 1:** Add entries to MEMORY.md § Key Decisions Locked.
**Step 2:** Add doc entries to § Doc Index.
**Step 3:** Commit: `docs: update MEMORY.md with Sprint 1 decisions`

---

## Execution Order

```
Task 1 (decisions) → Task 2 (schema spec) → Task 3 (ADR) → Task 4 (Linear tickets) → Task 5 (MEMORY.md)
```

Tasks 2 and 3 can partially overlap (ADR doesn't depend on schema), but schema is the higher-priority deliverable since it blocks all implementation.

---

## Done-When

- [ ] All five pending decisions resolved and documented
- [ ] `docs/db-schema-spec.md` covers all MVP entities with columns, types, constraints, indexes, RLS policies
- [ ] `docs/adr-001-infrastructure-choices.md` follows template, locks all stack choices
- [ ] Linear tickets created for all Sprint 1 agents with correct dependencies
- [ ] MEMORY.md updated with new decisions and doc index entries
- [ ] No entity in `docs/domain-model.md` is missing from the schema spec
- [ ] No field in `docs/prd.md` is missing from the schema spec
