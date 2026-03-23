# ADR-003: AgentDefinition + AgentInstance Architecture

**Status:** Proposed
**Author:** Gilfoyle
**Date:** 2026-03-22
**Project:** Kinetic
**Spec ref:** `docs/specs/agents.md` (KIN-242)
**Schema ref:** `docs/db-schema-spec.md` §8–11, §14–15, §16–18

---

## Context

Kinetic agents are AI personas grounded in system prompts, knowledge bases, and framework libraries. The core design challenge is the split between the agent blueprint (shared, owned by one user) and the per-user runtime state (private to the invoking user). This split affects every layer: data model, API surface, access control, context stack assembly, and the framework selection pipeline.

Forces at play:

1. **Shared vs. private state:** AgentDefinition (instructions, KB, frameworks) is shared — all invokers see the same content. AgentInstance (active memory, framework overrides) is private — per-user, per-agent.
2. **Immediate propagation:** When the owner updates an AgentDefinition, all invokers see the update on their next query. No versioning in MVP.
3. **Scale:** MVP targets ~50 users with ~20 agents. The design must be clean enough to support `shared` visibility (explicit invoker grants) post-MVP without a rewrite.
4. **Framework pipeline:** Frameworks are structured rows with per-trigger embeddings — not RAG chunks. The selection pipeline is distinct from KB retrieval.
5. **MCP access:** External AI clients can access AgentDefinitions via MCP. MCP exposes read-only context (system prompt, KB RAG, framework selection) but not AgentInstance data.

---

## Decision

### 1. Definition/Instance Split (Two Tables)

**`agent_definitions`** stores the shared blueprint: name, instructions (system prompt), type, visibility. Owned by one user (`owner_id`). Linked to a Knowledge Base and Framework Library via FK chains.

**`agent_instances`** stores per-user state: framework overrides (pinned/excluded). One instance per `(user_id, agent_definition_id)` pair. Auto-created on first invocation (get-or-create pattern). Active Memory entries live in `active_memory_entries` with an `agent_instance_id` FK, not in a text blob on the instance row.

**Why two tables (not one with user-scoped rows):** The definition is a first-class entity with its own lifecycle (create, edit, publish, delete). Instance data is ephemeral per-user state. Merging them would either leak instance data to the owner or require complex filtering on every query. The split maps directly to the access control model: definition-level RLS is visibility-based, instance-level RLS is user-scoped.

### 2. AgentInstance Auto-Creation (Get-or-Create on First Invocation)

When a user invokes an agent for the first time, `GET /api/v1/agents/:id/instance` performs a get-or-create:

```
SELECT * FROM agent_instances WHERE user_id = $1 AND agent_definition_id = $2;
-- If not found:
INSERT INTO agent_instances (user_id, agent_definition_id) VALUES ($1, $2) RETURNING *;
```

The `UNIQUE(user_id, agent_definition_id)` constraint prevents race-condition duplicates. An `ON CONFLICT DO NOTHING` + re-SELECT handles concurrent first-invocations.

**Why not explicit creation:** Requiring users to "subscribe" to an agent before invoking it adds friction with no benefit. The instance is invisible infrastructure — users don't need to know it exists. Lazy creation avoids pre-allocating instances for agents the user never invokes.

**Why not a DB trigger on first message:** Triggers are invisible and hard to debug. The API layer can log the creation event, validate preconditions (agent exists, user has access), and return the instance in the same round-trip.

### 3. Update Propagation (Immediate, No Versioning)

When the owner updates an AgentDefinition (instructions, KB content, frameworks), all invokers see the updated state on their next query. There is no snapshot, no version history, no "pin to version" in MVP.

**Why immediate:** MVP targets ~50 users, most agents are private (owner is the only invoker). The marginal complexity of versioning outweighs the risk of breaking changes at this scale.

**Post-MVP implication:** When `shared` visibility ships (explicit invoker grants), update propagation may need a notification or changelog so shared invokers know when the agent changes. This does not require versioning — a `last_updated_at` comparison and a changelog feed are sufficient. The current schema supports this without changes (agents already have `updated_at`).

### 4. Active Memory Token Cap (Application Layer)

Active memory entries are individual rows in `active_memory_entries`, each with a `content` text field. The token cap (500 tokens for agent instances, 1000 tokens for projects) is enforced at the API layer, not as a DB constraint.

**Enforcement flow:**
1. On write request, sum `token_count(content)` for all existing entries in the scope.
2. Add the proposed new entry's token count.
3. If sum exceeds cap, reject with `422 Validation Error` and return current usage + cap.
4. Token count uses `cl100k_base` encoding (same as RAG pipeline).

**Why not a DB constraint:** Token counting requires `tiktoken` (Python) — PostgreSQL CHECK constraints cannot call external functions. A generated column could store the token count per row, but the aggregate check across all rows in a scope cannot be expressed as a row-level constraint. The application layer is the natural enforcement point.

**Why not a trigger:** Triggers that import Python libraries (via PL/Python) add operational complexity and Supabase compatibility risk. The API layer is simpler and testable.

### 5. Framework Override Storage (JSONB on AgentInstance)

Framework overrides (pinned and excluded framework IDs) are stored as a JSONB column on `agent_instances`:

```json
{
  "pinned": ["framework-id-1", "framework-id-2"],
  "excluded": ["framework-id-3"]
}
```

**Why JSONB, not a separate table:** The override data is small (array of framework IDs), accessed atomically (always read/written as a unit), and scoped to one instance. A separate `agent_instance_framework_overrides` table with one row per override would add join cost for no structural benefit. The JSONB column is query-friendly (`@>` containment) and schema-flexible for future override types (e.g., parameter tweaks).

**Validation:** The API layer validates that all referenced `framework_id` values exist in the parent AgentDefinition's frameworks. Invalid IDs are silently dropped on read (defensive) and rejected on write (strict).

### 6. Framework Storage (Structured Rows, Not Documents)

Frameworks are stored as structured rows in the `frameworks` table — not as JSON blobs, not as KB documents. Each framework has typed columns for `name`, `description`, `when_to_apply` (text array), `principles` (text array), `steps` (text array), `example_application`, `related_frameworks`, and metadata.

**Why structured rows:** Frameworks are a first-class entity with specific query patterns — list, filter by category, update individual fields, merge on upload. Document-style storage (one JSON blob per agent) would require parsing and reconstructing the entire library on every write. Row-per-framework enables granular CRUD and per-framework RLS.

### 7. Framework Trigger Embeddings (Separate Table)

Each framework has 3-5 `when_to_apply` trigger phrases. Each trigger phrase gets its own embedding row in `framework_trigger_embeddings`. The framework selection pipeline searches these embeddings (not the framework body) to find matching frameworks.

**Why separate table (not embedded on framework row):** One framework maps to N triggers. Storing N embeddings (3072-dim vectors) on the framework row would require an array-of-vectors column, which pgvector doesn't support for HNSW indexing. The separate table enables standard vector search with per-trigger precision.

**Cascade:** `ON DELETE CASCADE` from `frameworks.id` — deleting a framework automatically removes its trigger embeddings.

### 8. MCP Token Strategy

MCP authentication uses per-user bearer tokens stored in `mcp_tokens`:

- **Generation:** User generates a token from the UI. The plaintext token is shown once, then discarded. Only the SHA-256 hash is stored.
- **Lookup:** On each MCP request, SHA-256 the incoming token and look up `mcp_tokens WHERE token_hash = $hash AND revoked_at IS NULL`. O(1) via unique index.
- **Revocation:** Setting `revoked_at` on a token row. Revoked tokens are excluded from lookup via a partial index.
- **Rate limiting:** `mcp_rate_limits` table tracks daily request count per user via upsert (`ON CONFLICT DO UPDATE SET request_count = request_count + 1`). HTTP 429 when `request_count >= daily_cap`.

**Why SHA-256 (not bcrypt):** MCP bearer tokens arrive without a user_id — the token IS the credential. bcrypt is non-deterministic, so no UNIQUE index can be placed on the hash. Without an index, lookup requires a full table scan or a format change to embed a row ID in the token. SHA-256 is deterministic: hash the token, index-scan, done. Token entropy is 256 bits (32 random bytes) — brute-force against SHA-256 is computationally infeasible regardless of hash speed. Use `hmac.compare_digest()` for constant-time comparison.

**Why not API keys (same as BYOK):** MCP tokens are infrastructure credentials (like OAuth tokens), not user secrets (like LLM API keys). They don't need AES-256-GCM encryption — SHA-256 hashing with one-time display is the standard pattern.

### 9. `generate-instructions` Endpoint

`POST /api/v1/agents/:id/generate-instructions` auto-generates a system prompt from the agent's KB.

**Flow:**
1. Validate the agent has a KB with at least one completed document.
2. Retrieve document summaries (or raw content if summaries unavailable) up to a token budget.
3. Call the user's default generation model (BYOK key) with a prompt template requesting a system prompt.
4. Return the generated instructions as a draft (not auto-saved).
5. User reviews, edits, and saves in the instructions editor.

**BYOK key usage:** The generation call uses the user's API key (their default model or first available). The endpoint is gated on having at least one API key configured — returns 422 if no keys exist.

**Timeout handling:** The generation call is wrapped in a 60-second timeout. On timeout, return 504 with a message suggesting retry or a shorter KB.

**Why not platform-key:** Instruction generation is a user-facing LLM call (creative, potentially long-running). BYOK ensures the platform doesn't absorb generation costs for a user-initiated action.

### 10. Framework Bulk Upload Merge Logic

`POST /api/v1/agents/:id/frameworks/upload` accepts a JSON file containing an array of framework objects.

**Merge behavior (id-based):**
- Matching `framework_id` (the semantic ID, not the DB UUID) → **update** existing framework with new values.
- New `framework_id` → **add** to library. Generate trigger embeddings.
- Missing `framework_id` (in DB but not in upload) → **retain** (not deleted). Upload is additive, not destructive.

**Validation pipeline:**
1. Parse JSON file. Reject if not valid JSON or not an array.
2. Per-framework validation: required fields (`name`, `when_to_apply` with ≥1 entry, `principles` with ≥1 entry). Invalid entries are skipped with error details.
3. Valid entries are upserted in a single transaction.
4. Trigger embeddings are regenerated for any framework whose `when_to_apply` changed (compare old vs. new arrays).
5. Return summary: `{ imported: N, updated: N, skipped: N, errors: [...] }`.

**Why retain-on-missing (not delete):** Deleting frameworks not in the upload file would destroy user-added manual frameworks when re-running an extraction script. Retain-on-missing is the safe default. Explicit delete is available via the individual `DELETE /frameworks/:id` endpoint.

---

## Alternatives Considered

### Definition/Instance Split

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **Two tables (chosen)** | Clean access control. Definition lifecycle separate from instance lifecycle. | Two tables to query for full agent state. | N/A |
| Single table with user-scoped columns | Fewer tables. Simpler queries. | Mixes shared and private data. RLS complexity increases. Owner can accidentally see instance data. | Access control violation risk. |
| Three tables (definition + instance + shared config) | Maximum separation. | Over-engineered for MVP. `shared` visibility is post-MVP. | YAGNI. |

### Active Memory Storage

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **Individual rows (chosen)** | Per-entry timestamps. Source conversation tracking. Granular CRUD. | Token cap requires aggregate query on write. | N/A |
| Single text blob on instance | Simple. One column, one read. | No per-entry metadata. No source tracking. Full rewrite on every edit. | PRD specifies per-entry timestamps and source conversation tracking. |
| JSONB array on instance | Structured per-entry data without a join. | No FK to conversations. Harder to enforce constraints. JSONB mutation is full-rewrite. | Worse than separate rows for CRUD patterns. |

### Framework Override Storage

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **JSONB on instance (chosen)** | Atomic read/write. Schema-flexible. No join. | Not independently queryable (rarely needed). | N/A |
| Separate table | Normalized. Independently queryable. | Join cost on every context assembly. Overrides are small — table overhead is disproportionate. | Over-normalized for the data shape. |

### MCP Token Storage

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **SHA-256 + UNIQUE index (chosen)** | O(1) lookup via unique index. Deterministic — enables DB-level uniqueness constraint. 256-bit token entropy makes brute-force infeasible. `hmac.compare_digest` gives constant-time comparison. No key management. | None at MVP scale. | N/A |
| bcrypt hash | Industry standard for password storage. | Non-deterministic — no UNIQUE index possible. Without embedded row ID in token format, lookup requires full table scan or O(n) iteration over all user tokens. User ID unknown at auth time, so O(n per user) is not achievable without format change. | Incompatible with stateless bearer token lookup. |
| AES-256-GCM (like API keys) | Recoverable — can display the token again. | Unnecessary — tokens are shown once. Adds encryption key dependency for infrastructure tokens. | Over-engineered. Users don't need to see tokens again. |

---

## Consequences

**Positive:**
- Clean separation of shared and private state. Access control is straightforward — definition RLS checks visibility, instance RLS checks user_id.
- Auto-created instances eliminate user friction. No "subscribe" step.
- JSONB framework overrides are atomic and schema-flexible — future override types (parameter tweaks, model preferences) can be added without migration.
- Retain-on-missing upload merge protects user-created frameworks from extraction re-runs.
- SHA-256 token hashing is O(1) lookup with no key management — simple and correct for high-entropy bearer tokens.

**Negative:**
- No versioning means a broken AgentDefinition update affects all invokers immediately. At MVP scale (~50 users, mostly private agents), this is a user error, not a system failure.
- Application-layer token cap enforcement requires careful testing — a bug could allow memory entries to exceed the cap. Mitigation: integration tests validate rejection at the boundary.
- SHA-256 token lookup is O(1) via unique index. No hashing overhead concern.
- Framework trigger embedding regeneration on upload adds latency to bulk uploads (3-5 embeddings per framework * N frameworks). Mitigated by running in background task.

**Neutral:**
- JSONB framework overrides are not independently queryable. This is fine — no use case requires "find all instances with framework X pinned" in MVP.
- `generate-instructions` timeout at 60 seconds may truncate long KB processing. Users can retry with a smaller KB or edit manually.

---

## Risks

- **Immediate propagation breaking shared agents post-MVP:** When `shared` visibility ships, an owner's bad edit could break all shared invokers. **Mitigation:** Post-MVP: add `updated_at` comparison + notification. Consider "preview before publish" UX. No schema change needed — `agent_definitions.updated_at` already exists.

- **Token cap race condition:** Two concurrent writes could both pass the cap check and both succeed, exceeding the cap. **Mitigation:** Wrap the check + insert in a serializable transaction (or advisory lock). The window is narrow at MVP scale but should be addressed before multi-user agents ship.

- **Framework override drift:** If a framework is deleted from the definition, pinned/excluded references in instances become stale. **Mitigation:** Defensive filtering on read — unknown framework IDs in overrides are silently ignored. No cleanup cascade needed.

- **MCP token brute-force:** Token entropy is 256 bits (32 random bytes). Brute-forcing SHA-256 against 256-bit input is computationally infeasible regardless of hash speed. Rate limit (1,000 req/day) is an additional defense layer. **Mitigation:** Token entropy is the primary defense. Rate limit is secondary.

- **`generate-instructions` quality:** Auto-generated system prompts may not capture the thought leader's voice accurately. **Mitigation:** This is a draft — user always reviews and edits before saving. The prompt template should emphasize voice/style extraction.

---

## Review Trigger

Revisit this ADR when:
- `shared` visibility ships — update propagation strategy needs notification/changelog
- Agent count exceeds 500 (framework trigger embedding volume, HNSW index pressure)
- Multi-agent per conversation ships — instance management becomes more complex
- MCP request volume exceeds 10,000/day per user — SHA-256 lookup is O(1), no caching concern
- Agent marketplace ships — definition ownership transfer, payment layer, and review process add requirements to the data model
