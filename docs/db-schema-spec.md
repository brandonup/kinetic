# Kinetic MVP — Database Schema Specification

**Status:** Draft
**Author:** Gilfoyle (updated by Richard 2026-03-29)
**Date:** 2026-03-29
**Project:** Kinetic

---

## Purpose

Canonical schema for all Kinetic MVP entities. Single source of truth — no other document defines DDL. All implementation code must reference this spec for table names, column names, types, and constraints. Inline DDL in other specs is advisory only; this document wins on conflict.

---

## Conventions

### Naming
- **Tables:** `snake_case`, plural (e.g., `users`, `companies`, `knowledge_base_documents`)
- **Columns:** `snake_case` (e.g., `user_id`, `created_at`)
- **Enums:** `snake_case` type name, `snake_case` values (e.g., `document_status` → `pending`, `extracting`)
- **Indexes:** `idx_{table}_{column(s)}` (e.g., `idx_messages_conversation_id`)
- **Foreign keys:** `fk_{table}_{column}` (e.g., `fk_projects_company_id`)
- **Check constraints:** `chk_{table}_{description}` (e.g., `chk_knowledge_bases_single_parent`)

### Standard Columns
Every table includes:
- `id uuid DEFAULT gen_random_uuid() PRIMARY KEY`
- `created_at timestamptz DEFAULT now() NOT NULL`
- `updated_at timestamptz DEFAULT now() NOT NULL` (except append-only tables like `messages`, `retrieval_debug_logs`)

A database trigger sets `updated_at = now()` on every UPDATE for tables that have the column.

### Soft-Delete Pattern
Tables with soft-delete use `deleted_at timestamptz DEFAULT NULL`. Queries must filter `WHERE deleted_at IS NULL` unless explicitly recovering deleted records. Applies to: `conversations`, `knowledge_base_documents`.

### Polymorphic Ownership Pattern
Some entities belong to exactly one of two parents (e.g., a Knowledge Base belongs to a Project OR an AgentDefinition). This is enforced via two nullable FK columns + a CHECK constraint:
```sql
CHECK (
  (project_id IS NOT NULL AND agent_definition_id IS NULL) OR
  (project_id IS NULL AND agent_definition_id IS NOT NULL)
)
```

### Row-Level Security (RLS)
RLS is enabled on all `public` tables. Default policy: deny all. Each table defines explicit SELECT/INSERT/UPDATE/DELETE policies. The authenticated user's ID comes from `auth.uid()`. General rules:
- Users can only access their own data
- Admin role bypasses user-scoping for admin-only tables (`llm_models`, `retrieval_debug_logs`)
- Company/project data is scoped through the `user_id` FK chain
- Public agent definitions are readable by all authenticated users

### Encryption Pattern (API Keys)
User API keys are encrypted with AES-256-GCM before storage. The encryption key is sourced from an environment variable (`API_KEY_ENCRYPTION_KEY`). Stored fields: `key_ciphertext` (bytea), `key_nonce` (bytea), `key_hint` (text — masked preview, e.g., `sk-ant-...abc1`). The plaintext key is never stored, logged, or returned in API responses.

---

## Enums

```sql
CREATE TYPE user_role AS ENUM ('admin', 'user');
CREATE TYPE api_key_provider AS ENUM ('anthropic', 'openai', 'google', 'groq');
CREATE TYPE agent_type AS ENUM ('custom', 'thought_leader');
CREATE TYPE agent_visibility AS ENUM ('private', 'public');
CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system');
CREATE TYPE document_status AS ENUM ('pending', 'extracting', 'chunking', 'embedding', 'completed', 'failed');
CREATE TYPE framework_confidence AS ENUM ('high', 'medium');
CREATE TYPE framework_origin AS ENUM ('extracted', 'manual');
CREATE TYPE proposal_status AS ENUM ('pending', 'approved', 'rejected');
CREATE TYPE proposal_trigger AS ENUM ('conversation_end', 'periodic');
CREATE TYPE llm_model_category AS ENUM ('generation', 'embedding', 'reranking');
CREATE TYPE retrieval_scope AS ENUM ('project_kb', 'agent_kb');
```

---

## Tables

### 1. `users`

Extends Supabase `auth.users`. A trigger creates a row here on auth signup.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK, REFERENCES auth.users(id) ON DELETE CASCADE` | Same ID as auth.users — not auto-generated |
| `name` | `text` | `NOT NULL` | Display name (editable by user) |
| `email` | `text` | `NOT NULL, UNIQUE` | From auth.users.email. Read-only in app (set by trigger). Layer 1 context. |
| `bio` | `text` | `CHECK (char_length(bio) <= 1000)` | Optional. 500–1000 chars. Layer 1 context. |
| `role` | `user_role` | `NOT NULL DEFAULT 'user'` | `admin` or `user` |
| `default_model_id` | `uuid` | `REFERENCES llm_models(id) ON DELETE SET NULL` | User's preferred generation model |
| `active_company_id` | `uuid` | `REFERENCES companies(id) ON DELETE SET NULL` | Currently active company for UI state |
| `disabled_at` | `timestamptz` | `DEFAULT NULL` | Null = active. Set by admin on disable. |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**RLS:**
- SELECT/UPDATE: `auth.uid() = id` (own row) OR role = `admin` (all rows)
- INSERT: via trigger only (on auth.users insert)
- DELETE: denied (use Supabase Auth admin API)

---

### 2. `user_api_keys`

One row per provider per user. Encrypted at rest.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` | |
| `provider` | `api_key_provider` | `NOT NULL` | anthropic, openai, google, groq |
| `key_ciphertext` | `bytea` | `NOT NULL` | AES-256-GCM encrypted key |
| `key_nonce` | `bytea` | `NOT NULL` | GCM nonce (12 bytes) |
| `key_hint` | `text` | `NOT NULL` | Masked preview, e.g., `sk-ant-...abc1` |
| `validated_at` | `timestamptz` | | Last successful validation |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Constraints:**
- `UNIQUE(user_id, provider)` — one key per provider

**RLS:**
- SELECT: `auth.uid() = user_id` — own keys only. Response MUST exclude `key_ciphertext` and `key_nonce` (enforced at API layer, not RLS).
- INSERT/UPDATE/DELETE: `auth.uid() = user_id`

---

### 3. `companies`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` | Owner |
| `name` | `text` | `NOT NULL` | |
| `description` | `text` | `CHECK (char_length(description) <= 1000)` | Optional. Layer 2 context. |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**RLS:**
- SELECT/INSERT/UPDATE/DELETE: `auth.uid() = user_id`

---

### 4. `projects`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `company_id` | `uuid` | `NOT NULL REFERENCES companies(id) ON DELETE CASCADE` | Parent company |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` | Denormalized for RLS |
| `name` | `text` | `NOT NULL` | |
| `instructions` | `text` | | Static, user-authored. ~500 tokens. Layer 3 context. |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**RLS:**
- SELECT/INSERT/UPDATE/DELETE: `auth.uid() = user_id`

---

### 5. `conversations`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` | |
| `company_id` | `uuid` | `NOT NULL REFERENCES companies(id) ON DELETE CASCADE` | Always set — active company at creation |
| `project_id` | `uuid` | `REFERENCES projects(id) ON DELETE CASCADE` | Nullable — null = company-level conversation |
| `title` | `text` | | Auto-generated from first message; user can rename |
| `active_agent_id` | `uuid` | `REFERENCES agent_definitions(id) ON DELETE SET NULL` | Currently invoked agent, nullable |
| `deleted_at` | `timestamptz` | | Soft-delete |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:**
- `idx_conversations_user_company` on `(user_id, company_id)` WHERE `deleted_at IS NULL`
- `idx_conversations_project` on `(project_id)` WHERE `deleted_at IS NULL`

**RLS:**
- SELECT/UPDATE/DELETE: `auth.uid() = user_id` AND filters `deleted_at IS NULL` by default
- INSERT: `auth.uid() = user_id`

---

### 6. `messages`

Append-only. No `updated_at`.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `conversation_id` | `uuid` | `NOT NULL REFERENCES conversations(id) ON DELETE CASCADE` | |
| `role` | `message_role` | `NOT NULL` | user, assistant, system |
| `content` | `text` | `NOT NULL` | |
| `agent_definition_id` | `uuid` | `REFERENCES agent_definitions(id) ON DELETE SET NULL` | Which agent generated this (nullable) |
| `model` | `text` | | Model string used for generation, e.g., `claude-sonnet-4-6` |
| `token_count` | `int` | | Approximate token count of content |
| `sequence` | `int` | `NOT NULL` | Ordering within conversation (0-indexed) |
| `debug_prompt` | `text` | | Full assembled prompt sent to the LLM (written on assistant messages for admin observability, KIN-419) |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:**
- `idx_messages_conversation_seq` on `(conversation_id, sequence)`

**RLS:**
- Access controlled via conversation ownership: `auth.uid() = (SELECT user_id FROM conversations WHERE id = conversation_id)`
- INSERT: same check + conversation not soft-deleted

---

### 7. `conversation_summaries`

Rolling compression summaries. Append-only.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `conversation_id` | `uuid` | `NOT NULL REFERENCES conversations(id) ON DELETE CASCADE` | |
| `summary_text` | `text` | `NOT NULL` | Compressed summary of older messages |
| `messages_covered_up_to` | `int` | `NOT NULL` | Message sequence number this summary covers through |
| `model` | `text` | | Model used to generate summary |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:**
- `idx_conv_summaries_conversation` on `(conversation_id)`

**RLS:**
- Via conversation ownership (same pattern as `messages`)

---

### 8. `agent_definitions`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `owner_id` | `uuid` | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` | Creator/owner |
| `name` | `text` | `NOT NULL` | e.g., "Strategist", "Nate Jones" |
| `slug` | `text` | `NOT NULL DEFAULT ''` | Slugified agent name (lowercase, hyphens, max 60 chars). Used for MCP agent resolution by friendly name. Globally unique — one slug per agent platform-wide. |
| `instructions` | `text` | | System prompt. ~500 tokens. Layer 5 context. |
| `type` | `agent_type` | `NOT NULL DEFAULT 'custom'` | custom or thought_leader |
| `visibility` | `agent_visibility` | `NOT NULL DEFAULT 'private'` | private or public (MVP) |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:**
- `idx_agent_definitions_owner` on `(owner_id)`
- `idx_agent_definitions_visibility` on `(visibility)` WHERE `visibility = 'public'`
- `uq_agent_definitions_slug` UNIQUE on `(slug)`

**RLS:**
- SELECT: `auth.uid() = owner_id` OR `visibility = 'public'`
- INSERT/UPDATE/DELETE: `auth.uid() = owner_id`

---

### 9. `agent_instances`

Per-user runtime state for an AgentDefinition. Auto-created on first invocation.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` | Invoking user |
| `agent_definition_id` | `uuid` | `NOT NULL REFERENCES agent_definitions(id) ON DELETE CASCADE` | |
| `framework_overrides` | `jsonb` | `NOT NULL DEFAULT '{}'` | `{ "pinned": ["framework-id"], "excluded": ["framework-id"] }` |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Constraints:**
- `UNIQUE(user_id, agent_definition_id)` — one instance per user per agent

**RLS:**
- SELECT/INSERT/UPDATE/DELETE: `auth.uid() = user_id`
- Instance data is private to the invoking user — definition owner cannot see it

---

### 10. `knowledge_bases`

Polymorphic parent: belongs to a Project or an AgentDefinition, never both.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `project_id` | `uuid` | `REFERENCES projects(id) ON DELETE CASCADE` | Nullable |
| `agent_definition_id` | `uuid` | `REFERENCES agent_definitions(id) ON DELETE CASCADE` | Nullable |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` | Denormalized for RLS |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Constraints:**
- `chk_knowledge_bases_single_parent`: `CHECK ((project_id IS NOT NULL AND agent_definition_id IS NULL) OR (project_id IS NULL AND agent_definition_id IS NOT NULL))`

**RLS:**
- SELECT: `auth.uid() = user_id` OR (agent KB where agent is public: `agent_definition_id IN (SELECT id FROM agent_definitions WHERE visibility = 'public')`)
- INSERT/UPDATE/DELETE: `auth.uid() = user_id`

---

### 11. `knowledge_base_folders`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `knowledge_base_id` | `uuid` | `NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE` | |
| `parent_folder_id` | `uuid` | `REFERENCES knowledge_base_folders(id) ON DELETE CASCADE` | Self-ref for nesting. Null = root. |
| `name` | `text` | `NOT NULL` | |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:**
- `idx_kb_folders_kb` on `(knowledge_base_id)`

**RLS:**
- Via knowledge_base ownership chain

---

### 12. `knowledge_base_documents`

Per `docs/rag-architecture.md` § Storage. Includes V1 columns (nullable, unused in MVP).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `knowledge_base_id` | `uuid` | `NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE` | |
| `folder_id` | `uuid` | `REFERENCES knowledge_base_folders(id) ON DELETE SET NULL` | |
| `title` | `text` | `NOT NULL` | Document name |
| `file_type` | `text` | | MIME type or extension |
| `storage_uri` | `text` | | Supabase Storage location |
| `file_size_bytes` | `bigint` | | |
| `token_count` | `int` | | Total tokens (post-extraction) |
| `summary` | `text` | | AI-generated summary (optional in MVP) |
| `key_topics` | `text[]` | | V1 — null in MVP |
| `document_date` | `date` | | V1 — publication date for recency scoring |
| `tags` | `text[]` | `DEFAULT '{}'` | AI-suggested + user-edited |
| `status` | `document_status` | `NOT NULL DEFAULT 'pending'` | Processing pipeline status |
| `error_stage` | `text` | | Which stage failed |
| `error_message` | `text` | | Error details |
| `retry_count` | `int` | `NOT NULL DEFAULT 0` | |
| `deleted_at` | `timestamptz` | | Soft-delete |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:**
- `idx_kb_docs_kb` on `(knowledge_base_id)` WHERE `deleted_at IS NULL`
- `idx_kb_docs_status` on `(status)` WHERE `status != 'completed'` — for retry/admin queries

**RLS:**
- Via knowledge_base ownership chain

---

### 13. `knowledge_base_chunks`

Per `docs/rag-architecture.md` § Storage. Primary vector search target.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `document_id` | `uuid` | `NOT NULL REFERENCES knowledge_base_documents(id) ON DELETE CASCADE` | |
| `knowledge_base_id` | `uuid` | `NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE` | Denormalized for query efficiency |
| `project_id` | `uuid` | | Denormalized scope — set if KB belongs to a Project |
| `agent_definition_id` | `uuid` | | Denormalized scope — set if KB belongs to an AgentDefinition |
| `text` | `text` | `NOT NULL` | Chunk content |
| `embedding` | `extensions.halfvec(3072)` | | pgvector halfvec — 3072 native gemini-embedding-001 dim, half-precision storage (KIN-476) |
| `chunk_summary` | `text` | | V1 — chunk-level enrichment |
| `keywords` | `text[]` | | V1 — chunk-level enrichment |
| `section_path` | `text` | | Heading hierarchy location |
| `page_range` | `text` | | For PDFs |
| `chunk_index` | `int` | `NOT NULL` | Position within document (0-indexed) |
| `tsv` | `tsvector` | | V1 — FTS index column |
| `embedding_model` | `text` | `NOT NULL DEFAULT 'gemini-embedding-001'` | Supports future model migrations (KIN-467, KIN-476) |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:**
- HNSW index on `embedding`:
  - `idx_kb_chunks_embedding_hnsw` on `(embedding extensions.halfvec_cosine_ops)` — single unfiltered index. RPC `match_chunks` filters by scope inside the function body (KIN-476).
- `idx_chunks_document` on `(document_id)`
- `idx_chunks_project` on `(project_id)` WHERE `project_id IS NOT NULL`
- `idx_chunks_agent_def` on `(agent_definition_id)` WHERE `agent_definition_id IS NOT NULL`
- V1: GIN index on `tsv` when `FTS_ENABLED`

**RLS:**
- Via knowledge_base ownership chain. Chunks for public agents are readable by all authenticated users.

---

### 14. `frameworks`

Structured reasoning tools attached to an AgentDefinition.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | DB primary key |
| `agent_definition_id` | `uuid` | `NOT NULL REFERENCES agent_definitions(id) ON DELETE CASCADE` | |
| `framework_id` | `text` | `NOT NULL` | Semantic ID (kebab-case), e.g., `coordination-tax-diagnostic` |
| `name` | `text` | `NOT NULL` | Display name |
| `description` | `text` | | One-sentence description |
| `category` | `text` | | Open list: strategy, org-design, etc. |
| `when_to_apply` | `text[]` | `NOT NULL CHECK (array_length(when_to_apply, 1) >= 1)` | Trigger phrases (3–5 recommended) |
| `principles` | `text[]` | `NOT NULL CHECK (array_length(principles, 1) >= 1)` | Core ideas/rules |
| `steps` | `text[]` | | Optional ordered steps |
| `example_application` | `text` | | 2–3 sentence scenario |
| `related_frameworks` | `text[]` | | Array of framework_id strings |
| `source_posts` | `jsonb` | | `[{"id": "...", "title": "..."}]` |
| `type` | `text` | | Framework type: diagnostic, procedure, taxonomy, etc. |
| `do_not_use_when` | `text[]` | | Negative triggers — when NOT to recommend this framework |
| `confidence` | `framework_confidence` | `NOT NULL` | high or medium |
| `origin` | `framework_origin` | `NOT NULL` | extracted or manual |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Constraints:**
- `UNIQUE(agent_definition_id, framework_id)` — one per semantic ID per agent

**Indexes:**
- `idx_frameworks_agent_def` on `(agent_definition_id)`

**RLS:**
- SELECT: via agent_definition ownership or public visibility
- INSERT/UPDATE/DELETE: `auth.uid() = (SELECT owner_id FROM agent_definitions WHERE id = agent_definition_id)`

---

### 15. `framework_trigger_embeddings`

One row per trigger phrase per framework. Search target for framework selection pipeline step 1.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `framework_db_id` | `uuid` | `NOT NULL REFERENCES frameworks(id) ON DELETE CASCADE` | DB FK to frameworks table |
| `agent_definition_id` | `uuid` | `NOT NULL REFERENCES agent_definitions(id) ON DELETE CASCADE` | Denormalized for scoped queries |
| `trigger_text` | `text` | `NOT NULL` | The trigger phrase being embedded |
| `embedding` | `extensions.halfvec(3072)` | `NOT NULL` | pgvector halfvec — 3072 native gemini-embedding-001 dim (KIN-476) |
| `embedding_model` | `text` | `NOT NULL DEFAULT 'gemini-embedding-001'` | (KIN-467, KIN-476) |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:**
- HNSW index on `embedding`:
  - `idx_fw_trigger_embeddings_hnsw` on `(embedding extensions.halfvec_cosine_ops)` — single unfiltered index. RPC `match_framework_triggers` filters by `agent_definition_id` inside the function body (KIN-476).
- `idx_trigger_embeddings_framework` on `(framework_db_id)`

**RLS:**
- Via agent_definition ownership or public visibility

---

### 16. `active_memory_entries`

Individual memory rows. Polymorphic: belongs to a Project or an AgentInstance.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` | Denormalized for RLS |
| `project_id` | `uuid` | `REFERENCES projects(id) ON DELETE CASCADE` | Nullable |
| `agent_instance_id` | `uuid` | `REFERENCES agent_instances(id) ON DELETE CASCADE` | Nullable |
| `content` | `text` | `NOT NULL` | The memory entry |
| `source_conversation_id` | `uuid` | `REFERENCES conversations(id) ON DELETE SET NULL` | Null for user-authored entries |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Constraints:**
- `chk_active_memory_single_parent`: `CHECK ((project_id IS NOT NULL AND agent_instance_id IS NULL) OR (project_id IS NULL AND agent_instance_id IS NOT NULL))`

**Indexes:**
- `idx_active_memory_project` on `(project_id)` WHERE `project_id IS NOT NULL`
- `idx_active_memory_agent_instance` on `(agent_instance_id)` WHERE `agent_instance_id IS NOT NULL`

**RLS:**
- SELECT/INSERT/UPDATE/DELETE: `auth.uid() = user_id`

**Token cap enforcement:** Application layer enforces ≤1000 tokens (project) and ≤500 tokens (agent instance) across all entries for the scope. Not a DB constraint — requires summing `content` token counts before write.

---

### 17. `memory_proposals`

Queued AI-generated memory proposals awaiting user review.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` | |
| `conversation_id` | `uuid` | `REFERENCES conversations(id) ON DELETE CASCADE` | Source conversation (nullable — null for MCP-sourced proposals) |
| `mcp_message_id` | `uuid` | `REFERENCES messages_mcp(id) ON DELETE CASCADE` | Source MCP invocation (nullable — null for conversation-sourced proposals) |
| `project_id` | `uuid` | `REFERENCES projects(id) ON DELETE CASCADE` | Target scope (nullable) |
| `agent_instance_id` | `uuid` | `REFERENCES agent_instances(id) ON DELETE CASCADE` | Target scope (nullable) |
| `proposed_content` | `text` | `NOT NULL` | |
| `status` | `proposal_status` | `NOT NULL DEFAULT 'pending'` | pending, approved, rejected |
| `trigger_type` | `proposal_trigger` | `NOT NULL` | conversation_end or periodic |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `reviewed_at` | `timestamptz` | | When user acted on it |

**Constraints:**
- `chk_memory_proposals_source`: `CHECK (conversation_id IS NOT NULL OR mcp_message_id IS NOT NULL)` — every proposal must have a source

**Indexes:**
- `idx_memory_proposals_pending` on `(user_id, project_id)` WHERE `status = 'pending'`
- `idx_memory_proposals_agent_pending` on `(user_id, agent_instance_id)` WHERE `status = 'pending'`

**RLS:**
- SELECT/UPDATE: `auth.uid() = user_id`
- INSERT: system/service role only (background tasks)

---

### 18. `mcp_tokens`

Per-user bearer tokens for MCP access. Token plaintext shown once on generation, then only the hash is stored.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` | |
| `token_hash` | `text` | `NOT NULL` | SHA-256 hash of the bearer token |
| `name` | `text` | | User label, e.g., "Claude Desktop" |
| `last_used_at` | `timestamptz` | | |
| `revoked_at` | `timestamptz` | | Null = active |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:**
- `idx_mcp_tokens_user` on `(user_id)` WHERE `revoked_at IS NULL`

**RLS:**
- SELECT/INSERT/DELETE: `auth.uid() = user_id`
- Token lookup by hash is done server-side with service role (not through RLS)

---

### 19. `llm_models`

Admin-managed model library. Three categories; only `generation` is user-facing in MVP.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `provider` | `text` | `NOT NULL` | e.g., `anthropic`, `openai`, `google`, `groq` |
| `model_id` | `text` | `NOT NULL UNIQUE` | e.g., `claude-sonnet-4-6`, `gpt-4o` |
| `display_name` | `text` | `NOT NULL` | e.g., "Claude Sonnet 4.6" |
| `category` | `llm_model_category` | `NOT NULL` | generation, embedding, reranking |
| `enabled` | `boolean` | `NOT NULL DEFAULT true` | |
| `context_window` | `int` | | Token count for context window |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**RLS:**
- SELECT: all authenticated users (model list is public)
- INSERT/UPDATE/DELETE: admin role only

---

### 20. `retrieval_debug_logs`

Per-query retrieval traces for admin debugging. Append-only. Auto-purge after 30 days.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `message_id` | `uuid` | `NOT NULL REFERENCES messages(id) ON DELETE CASCADE` | |
| `scope` | `retrieval_scope` | `NOT NULL` | project_kb or agent_kb |
| `query_text` | `text` | `NOT NULL` | User's original query |
| `query_variants` | `text[]` | | V1 — null in MVP (single query) |
| `vector_candidates` | `jsonb` | | Pre-MMR candidates: `[{chunk_id, score}]` |
| `mmr_selections` | `jsonb` | | Post-MMR selections |
| `rerank_scores` | `jsonb` | | V1 — null in MVP |
| `gating_decision` | `text` | `NOT NULL` | `injected`, `below_threshold`, or `error` (MVP) |
| `injected_chunks` | `jsonb` | | Final chunks: `[{chunk_id, score, text_preview}]` |
| `error_message` | `text` | | Populated on embedding failure; null for successful retrievals |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:**
- `idx_retrieval_debug_logs_created_at` on `(created_at DESC)`

**RLS:**
- SELECT: admin role only
- INSERT: service role (backend writes during generation)

**Maintenance:** Scheduled job deletes rows older than 30 days.

---

### 21. `mcp_rate_limits`

Per-user daily request counter for MCP rate limiting.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` | |
| `date` | `date` | `NOT NULL` | Calendar date |
| `request_count` | `int` | `NOT NULL DEFAULT 0` | Incremented per MCP request |
| `daily_cap` | `int` | `NOT NULL DEFAULT 1000` | Admin-configurable per user |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Constraints:**
- `UNIQUE(user_id, date)`

**Usage:** On each MCP request: `INSERT ... ON CONFLICT (user_id, date) DO UPDATE SET request_count = request_count + 1`. Check `request_count < daily_cap` before processing. Return HTTP 429 when exceeded.

**RLS:**
- SELECT/INSERT/UPDATE: service role only (MCP server operates with service key)

---

### 22. `messages_mcp`

MCP invocation logs. One row per `assemble_context` call. Append-only — no `updated_at`, no soft-delete.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` | From MCP token auth |
| `agent_definition_id` | `uuid` | `REFERENCES agent_definitions(id) ON DELETE CASCADE` | Resolved from slug (null if resolution failed) |
| `agent_instance_id` | `uuid` | `REFERENCES agent_instances(id) ON DELETE CASCADE` | Per-user agent instance (null if resolution failed) |
| `query` | `text` | `NOT NULL` | User's original question |
| `agent_slug` | `text` | `NOT NULL` | Agent slug used (denormalized for admin readability) |
| `context_payload` | `text` | | Full assembled response sent to client |
| `layer_persona` | `text` | | Persona text returned, or null if empty/failed |
| `layer_memory` | `text` | | Active memory text returned, or null if empty |
| `layer_framework` | `text` | | Framework text returned, or null if no match |
| `layer_kb` | `text` | | KB search results returned, or null if no match |
| `layer_status` | `jsonb` | `NOT NULL` | Per-layer status: `"ok"`, `"empty"`, `"error"`, `"skipped"` |
| `latency_ms` | `int` | | Total wall-clock time for assemble_context in ms |
| `embedding_latency_ms` | `int` | | OpenAI embedding call latency in ms (null if skipped) |
| `token_count_estimate` | `int` | | Estimated token count of context_payload (nullable) |
| `error` | `text` | | Top-level error message if invocation failed |
| `mcp_session_id` | `text` | | Mcp-Session-Id header value (nullable) |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Indexes:**
- `idx_messages_mcp_user` on `(user_id)` — admin queries by user
- `idx_messages_mcp_agent_instance` on `(agent_instance_id)` — memory extraction scoped to agent
- `idx_messages_mcp_created` on `(created_at)` — time-range admin queries

**RLS:**
- SELECT: `auth.uid() = user_id` (user can see their own MCP history)
- INSERT: open (service role writes via Edge Function)
- UPDATE/DELETE: denied (append-only)

---

### 23. `scrape_sources`

Configured scraping sources for automated KB content ingestion. One row per source (Substack blog, RSS feed).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `knowledge_base_id` | `uuid` | `NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE` | Target KB for ingested content |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` | Denormalized for RLS |
| `source_type` | `text` | `NOT NULL, CHECK IN ('substack', 'rss')` | Extensible via CHECK update |
| `source_url` | `text` | `NOT NULL` | Substack base URL or RSS feed URL |
| `frequency` | `text` | `NOT NULL, CHECK IN ('daily', 'weekly', 'monthly')` | |
| `credential_ciphertext` | `bytea` | | AES-256-GCM encrypted cookie/token. NULL for public feeds |
| `credential_nonce` | `bytea` | | Encryption nonce. NULL when ciphertext is NULL |
| `is_active` | `boolean` | `NOT NULL DEFAULT true` | Pause/resume without deleting |
| `last_scraped_at` | `timestamptz` | | NULL until first successful run |
| `next_run_at` | `timestamptz` | `NOT NULL` | Set on creation based on frequency. Poller checks this |
| `last_error` | `text` | | NULL on success. Set on failure |
| `consecutive_failures` | `int` | `NOT NULL DEFAULT 0` | Auto-deactivates after 5. Reset on success |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Constraints:**
- `chk_scrape_sources_credential_pair`: both credential columns NULL or both NOT NULL

**Indexes:**
- `idx_scrape_sources_poll` on `(is_active, next_run_at)` WHERE `is_active = true` — poller query
- `idx_scrape_sources_kb` on `(knowledge_base_id)` — list sources for a KB

**RLS:**
- SELECT/INSERT/UPDATE/DELETE: `auth.uid() = user_id`

---

### 24. `scrape_source_posts`

Deduplication tracker for scraped posts. One row per successfully scraped post. No `updated_at` — append-only.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `uuid` | `PK DEFAULT gen_random_uuid()` | |
| `scrape_source_id` | `uuid` | `NOT NULL REFERENCES scrape_sources(id) ON DELETE CASCADE` | |
| `user_id` | `uuid` | `NOT NULL REFERENCES users(id) ON DELETE CASCADE` | Denormalized for RLS |
| `external_id` | `text` | `NOT NULL` | Substack post ID or RSS entry GUID |
| `document_id` | `uuid` | `REFERENCES knowledge_base_documents(id) ON DELETE SET NULL` | Links to ingested KB doc |
| `url` | `text` | | Post URL for reference |
| `title` | `text` | | Post title for display |
| `scraped_at` | `timestamptz` | `NOT NULL DEFAULT now()` | |

**Constraints:**
- `uq_scrape_source_posts_source_external`: UNIQUE on `(scrape_source_id, external_id)`

**RLS:**
- SELECT/INSERT/UPDATE/DELETE: `auth.uid() = user_id`

---

## Configuration Parameters

These are application-level settings, not database columns. Listed here for completeness since they affect query behavior.

| Parameter | Default | Notes |
|---|---|---|
| `RAG_MAX_TOKENS` | 15% of model context window, floor 2048 | Dynamic. Calculated per query based on selected model's `context_window` from `llm_models`. |
| `RAG_TOKEN_BUDGET_SPLIT` | Dynamic (score-based) | All chunks from both scopes ranked by similarity; budget filled greedily from top. No fixed split. |
| `VECTOR_TOP_K` | 20 | Candidates from vector search |
| `MMR_TOP_K` | 8 | Candidates after MMR |
| `MMR_LAMBDA` | 0.6 | Relevance/diversity tradeoff |
| `SIMILARITY_THRESHOLD` | 0.3 | Minimum cosine similarity |
| `ACTIVE_MEMORY_CAP_PROJECT` | 1000 tokens | Hard cap for project active memory |
| `ACTIVE_MEMORY_CAP_AGENT` | 500 tokens | Hard cap for agent instance active memory |
| `MEMORY_PROPOSAL_INTERVAL` | 10 messages | Fixed in MVP |
| `MCP_DEFAULT_DAILY_CAP` | 1000 requests | Default per-user MCP rate limit |
| `ENRICHMENT_ENABLED` | true | Document-level summary on ingestion |

V1 enhancement flags (all `false` in MVP): `QUERY_REWRITE_ENABLED`, `FTS_ENABLED`, `RERANKING_ENABLED`, `RECENCY_ENABLED`, `CHUNK_ENRICHMENT_ENABLED`, `SEMANTIC_CHUNKING_ENABLED`. See `docs/rag-architecture.md` for full parameter list.

---

## Cross-Cutting Patterns

### Soft-Delete with Deferred Cleanup

**Decision:** Documents and conversations use soft-delete (`deleted_at` timestamp). Chunks belonging to soft-deleted documents are not immediately removed — a scheduled cleanup job hard-deletes chunks for documents where `deleted_at` is older than 7 days. This avoids expensive HNSW reindexing during user-facing operations.

**Tables using soft-delete:** `conversations`, `knowledge_base_documents`

### Polymorphic Ownership

Two tables use the polymorphic pattern (two nullable FKs + CHECK constraint):
- `knowledge_bases` — project_id XOR agent_definition_id
- `active_memory_entries` — project_id XOR agent_instance_id

### Denormalized `user_id`

Several tables carry a `user_id` column that could be derived through FK joins (e.g., `projects.user_id` could be derived via `companies.user_id`). This denormalization exists solely for RLS performance — Supabase RLS policies that require joins are significantly slower than direct column checks. The application layer is responsible for keeping denormalized `user_id` consistent.

Tables with denormalized `user_id`: `projects`, `knowledge_bases`, `active_memory_entries`

### Auth User Trigger

A PostgreSQL trigger on `auth.users` INSERT creates the corresponding `public.users` row:

```sql
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.users (id, name, role)
  VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data->>'name', NEW.email), 'user');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
```

---

## RPC Functions (Stored Procedures)

### `match_framework_triggers`

Vector similarity search on framework trigger phrases, scoped to an agent.

```sql
CREATE OR REPLACE FUNCTION public.match_framework_triggers(
  query_embedding text,                        -- JSON-array text, cast to halfvec inside
  p_agent_id uuid,
  match_count integer DEFAULT 20
)
RETURNS TABLE (
  framework_db_id uuid,
  trigger_text text,
  similarity double precision
)
```

**Latest migration:** `20260518000001_kin476_embeddings_3072_halfvec.sql` (KIN-476). Originally added in `20260328000006_add_match_framework_triggers_rpc.sql`; dim and param type changed across `20260407000002_gemini_embeddings_1024.sql` (KIN-467) and KIN-476.
**Param type note (KIN-476):** the parameter is `text`, not `extensions.halfvec(3072)`. PostgREST has no implicit cast from JSON-array to halfvec, so Python callers passing `list[float]` would fail on a halfvec-typed param. The function body declares `q extensions.halfvec(3072) := query_embedding::extensions.halfvec(3072)` and uses `q` in the cosine distance operator. `SET search_path = public, extensions` makes the schema-qualified `extensions.halfvec` resolvable.

### `match_chunks`

Vector similarity search on knowledge base chunks with dynamic scope filtering.

```sql
CREATE OR REPLACE FUNCTION public.match_chunks(
  query_embedding text,                        -- JSON-array text, cast to halfvec inside
  scope_column text,
  scope_value text,
  match_count integer DEFAULT 20
)
RETURNS TABLE (
  id uuid,
  document_id uuid,
  document_title text,
  document_type text,
  text text,
  chunk_index integer,
  section_path text,
  page_range text,
  similarity double precision
)
```

**Usage:** Called by the RAG retrieval pipeline and the local MCP server (`packages/mcp/`). `scope_column` must be one of `agent_definition_id`, `knowledge_base_id`, or `project_id` (validated inside the function); `scope_value` is the corresponding UUID.
**Param type note (KIN-476):** same as `match_framework_triggers` — parameter is `text`, cast to `extensions.halfvec(3072)` inside the function body. Joins `knowledge_base_documents` for `document_title` and `document_type`. Uses `EXECUTE format(...)` for dynamic column filtering.

---

### `mcp_check_and_increment_rate_limit`

Atomic rate-limit check and increment for MCP token-authenticated requests.

```sql
CREATE OR REPLACE FUNCTION public.mcp_check_and_increment_rate_limit(
  p_user_id uuid,
  p_date date
)
RETURNS TABLE (
  allowed boolean,
  request_count int,
  daily_cap int
)
```

**Usage:** Called by the MCP server on every authenticated request. Performs `INSERT ... ON CONFLICT DO UPDATE SET request_count = request_count + 1` on `mcp_rate_limits`, then returns whether the post-increment count is within cap.
**Note:** `SECURITY DEFINER` — called from service-role context, not through RLS.

---

## Migration Notes

### Extension Requirements
```sql
CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector (>= 0.7.0 required — KIN-476 uses halfvec HNSW)
CREATE EXTENSION IF NOT EXISTS pgcrypto;     -- gen_random_uuid()
```

**pgvector version note (KIN-476):** `halfvec` HNSW (up to 4000 dims) was added in pgvector 0.7.0. The KIN-476 migration assumes ≥ 0.7.0. Verify with `SELECT extversion FROM pg_extension WHERE extname='vector'` before applying related migrations. Production Supabase was on 0.8 at the time of KIN-476.

### Migration Order
Tables must be created in dependency order:
1. Enums
2. `users` (+ auth trigger)
3. `llm_models` (referenced by `users.default_model_id`)
4. `user_api_keys`
5. `companies`
6. `projects`
7. `conversations`
8. `messages`, `conversation_summaries`
9. `agent_definitions`
10. `agent_instances`
11. `knowledge_bases`
12. `knowledge_base_folders`
13. `knowledge_base_documents`
14. `knowledge_base_chunks`
15. `frameworks`
16. `framework_trigger_embeddings`
17. `active_memory_entries`, `memory_proposals`
18. `mcp_tokens`, `mcp_rate_limits`
19. `retrieval_debug_logs`

### V1 Column Strategy
V1-only columns (`key_topics`, `document_date`, `chunk_summary`, `keywords`, `tsv`, `query_variants`, `rerank_scores`) are included in the MVP schema as nullable. They cost nothing when null — no storage overhead, no index cost. Enabling a V1 feature later is a code change + backfill, not a migration.
