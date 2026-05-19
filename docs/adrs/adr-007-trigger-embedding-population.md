# ADR-007: Trigger Embedding Population Strategy

**Status:** Accepted, Amended (2026-04-07 KIN-467 platform Gemini; 2026-05-18 KIN-476 halfvec(3072))
**Author:** Gilfoyle
**Date:** 2026-03-28
**Project:** Kinetic
**Ticket:** KIN-410

---

## Context

The `framework_trigger_embeddings` table is empty. The framework selection pipeline (`framework_selection.py`) reads from it via the `match_framework_triggers` RPC, so Layer 7 (framework injection) and MCP framework selection are completely non-functional. 184 curated frameworks exist in the `frameworks` table with `when_to_apply` trigger phrases, but no code path embeds those triggers and inserts them into `framework_trigger_embeddings`.

Three gaps exist:

1. **No RPC function.** `match_framework_triggers` is called by `framework_selection.py` but doesn't exist in the migration file. Tests mock it.
2. **No write-time embedding.** Framework create, update, and bulk upload endpoints write to `frameworks` but never populate `framework_trigger_embeddings`.
3. **No backfill path.** The 184 existing frameworks have no mechanism to retroactively generate trigger embeddings.

Post-KIN-382, no platform-owned API keys exist. All embedding calls require a user's BYOK OpenAI key. This affects both backfill (who provides the key?) and ongoing population (what if the owner has no OpenAI key?).

Key compatibility is not an issue: `text-embedding-3-large` produces identical vectors regardless of which API key authenticates the call. Trigger embeddings generated with owner key A are searchable with querying user key B — same model, same vector space.

## Decision

> We will populate trigger embeddings via background jobs dispatched from framework write endpoints, using the agent definition owner's BYOK OpenAI key, with a one-time admin backfill endpoint for existing data.

### 1. Backfill: Admin endpoint

`POST /api/v1/admin/backfill-trigger-embeddings`

- Admin-only (reuses existing admin auth guard).
- Accepts optional `agent_definition_id` to scope to one agent, or processes all agents if omitted.
- For each agent definition: fetch owner's decrypted OpenAI key → embed all `when_to_apply` triggers → upsert into `framework_trigger_embeddings`.
- If the owner has no OpenAI key: skip that agent, log it, include in response summary.
- Idempotent: deletes existing trigger embeddings for each framework before inserting fresh ones (avoids duplicates on re-run).
- Returns: `{ "processed": N, "skipped_no_key": N, "frameworks_embedded": N, "triggers_embedded": N }`.

### 2. Ongoing population: Background job via TaskDispatcher

On every framework write operation, dispatch an async embedding job:

| Endpoint | Trigger | Job behavior |
|---|---|---|
| `POST .../frameworks` (create) | After successful insert | Embed all `when_to_apply` triggers → insert into `framework_trigger_embeddings` |
| `PATCH .../frameworks/{id}` (update) | Only if `when_to_apply` changed | Delete old trigger embeddings for this framework → embed new triggers → insert |
| `POST .../frameworks/upload` (bulk) | After merge logic completes | For each added or updated framework where `when_to_apply` changed: delete old → embed → insert |
| `DELETE .../frameworks/{id}` | N/A | `ON DELETE CASCADE` handles cleanup — no job needed |

Job implementation:

```python
async def embed_framework_triggers(
    framework_db_id: str,
    agent_definition_id: str,
    triggers: list[str],
    user_id: str,
) -> None:
    """Background job: embed trigger phrases and insert into framework_trigger_embeddings."""
    openai_key = await fetch_user_key_async(supabase, user_id, "openai")
    if not openai_key:
        logger.warning("No OpenAI key for user %s — skipping trigger embedding for framework %s", user_id, framework_db_id)
        return  # Framework saved but dormant — invisible to selection pipeline

    embedder = EmbeddingService(api_key=openai_key)
    embeddings = embedder.embed_batch(triggers)

    # Delete existing (idempotent)
    supabase.table("framework_trigger_embeddings") \
        .delete().eq("framework_db_id", framework_db_id).execute()

    # Insert new
    rows = [
        {
            "framework_db_id": framework_db_id,
            "agent_definition_id": agent_definition_id,
            "trigger_text": trigger,
            "embedding": emb,
            "embedding_model": "text-embedding-3-large",
        }
        for trigger, emb in zip(triggers, embeddings)
    ]
    supabase.table("framework_trigger_embeddings").insert(rows).execute()
```

Dispatched via existing `TaskDispatcher.dispatch()` pattern. No retry — if embedding fails, the framework is dormant. User can re-trigger by updating `when_to_apply`.

### 3. Lifecycle management

| Event | Trigger embeddings action |
|---|---|
| Framework created | Generate embeddings for all `when_to_apply` triggers |
| Framework updated (`when_to_apply` changed) | Delete old, generate new |
| Framework updated (`when_to_apply` unchanged) | No action |
| Framework deleted | Automatic via `ON DELETE CASCADE` |
| Agent definition deleted | Automatic via `ON DELETE CASCADE` (frameworks cascade first, then trigger embeddings) |

### 4. BYOK key rules

- **Write-time (trigger embedding generation):** Agent definition owner's OpenAI key. Fetched via `fetch_user_key_async(supabase, owner_user_id, "openai")`.
- **Query-time (query embedding for search):** Querying user's OpenAI key. Already implemented in `framework_selection.py`.
- **No OpenAI key at write time:** Framework saves normally. Trigger embeddings are not generated. Framework is "dormant" — visible in the library UI but invisible to the selection pipeline. No error surfaced to the user (fail-open, consistent with existing pipeline design).
- **No OpenAI key at query time:** `select_framework` returns `no_match` (already implemented — fails open).

### 5. RPC function

Add `match_framework_triggers` to `000_complete_schema.sql`:

```sql
CREATE OR REPLACE FUNCTION public.match_framework_triggers(
  query_embedding vector(3072),
  p_agent_id uuid,
  match_count integer DEFAULT 20
)
RETURNS TABLE (
  framework_db_id uuid,
  trigger_text text,
  similarity double precision
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN QUERY
  SELECT
    fte.framework_db_id,
    fte.trigger_text,
    1 - (fte.embedding <=> query_embedding) AS similarity
  FROM public.framework_trigger_embeddings fte
  WHERE fte.agent_definition_id = p_agent_id
  ORDER BY fte.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
```

`SECURITY DEFINER` bypasses RLS — the RPC is called from the backend with a service-role client. Scoping by `p_agent_id` provides tenant isolation.

## Alternatives Considered

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **A. Background job + BYOK key (chosen)** | Consistent with BYOK model. No platform cost. Existing patterns (TaskDispatcher, EmbeddingService). Fail-open on missing key. | Dormant frameworks if no OpenAI key. Backfill requires admin endpoint. | N/A — this is the decision |
| **B. Platform-owned key for embedding** | Every framework gets embedded regardless of user key status. Simpler backfill (one key for all). | Contradicts KIN-382 (no platform keys). Re-introduces platform cost for embedding. Creates a second key management path. | Contradicts locked BYOK decision. Adds operational complexity for a narrow benefit. |
| **C. Synchronous embedding in request path** | Simpler — no background job infrastructure. Embedding guaranteed before response. | Adds 500-2000ms latency per framework create/update (embedding API call). Bulk upload would be extremely slow (184 frameworks × 3-5 triggers each). Blocks the request thread. | Unacceptable latency, especially for bulk upload. |
| **D. Lazy embedding on first query** | No write-time cost. Embedding happens when needed. | Cold-start latency on first query per framework. Race condition if multiple users query simultaneously. Complex cache-invalidation when `when_to_apply` changes. | Shifts cost to the reader, not the writer. Wrong user pays (querying user, not framework owner). Complexity not justified. |

## Consequences

**Positive:**
- Framework selection pipeline becomes functional (Layer 7 + MCP).
- Write-time embedding is invisible to the user — no UX change to framework CRUD.
- Consistent with existing BYOK model and TaskDispatcher pattern.
- Idempotent backfill endpoint is re-runnable (safe for future bulk imports).

**Negative:**
- Frameworks created by users without an OpenAI key are dormant — they exist in the library but are invisible to the selection pipeline. No explicit UI signal for this in MVP.
- Backfill is a manual admin action, not automatic on deploy.

**Neutral:**
- Embedding cost shifts to the framework owner (write-time BYOK). At ~$0.00013 per 1K tokens and ~5 triggers × ~10 tokens each, cost per framework is negligible (~$0.000007).

## Risks

- **Dormant frameworks confuse users:** A user creates frameworks but gets no framework suggestions in chat because they have no OpenAI key. **Mitigation:** Log a warning. Post-MVP: surface a "trigger embeddings pending — add an OpenAI key" badge in the framework library UI. For MVP, this is acceptable — the ICP (tech founders, AI consultants) will have OpenAI keys.
- **Backfill fails partway:** Network error or rate limit during bulk embedding. **Mitigation:** Idempotent design — re-run the endpoint. Per-framework error handling (skip failures, report in response).
- **Embedding model change:** If we switch from `text-embedding-3-large`, all existing trigger embeddings are incompatible. **Mitigation:** `embedding_model` column on each row. Backfill endpoint can re-embed all. Future: migration script that re-embeds on model change.

## Review Trigger

- If framework count exceeds 10K per agent (sequential scan too slow → need HNSW index, which requires ≤2000 dims or dimensionality reduction).
- If platform-owned keys are reintroduced for any pipeline component.
- If embedding model changes from `text-embedding-3-large`.

---

## Amendments

### 2026-04-07 — KIN-467: Embedding model + key source

The decision in **§4 (BYOK key rules)** has been superseded for embedding generation specifically:

- **Embedding model:** `text-embedding-3-large` (OpenAI) → **`gemini-embedding-001`** (Google).
- **Key source:** Agent definition owner's BYOK OpenAI key → **platform-owned `GEMINI_API_KEY`** (server-side).
- **Effect on §4:** Write-time embedding no longer requires the owner to have a BYOK key. The "dormant framework" failure mode (Risks) is eliminated — every framework gets embedded.
- **Code shape:** `EmbeddingService()` is constructed without an explicit `api_key` and reads the platform Gemini key from `settings.GEMINI_API_KEY`. The job code in §2 still applies, with the OpenAI-key fetch step removed.
- **`embedding_model` column DEFAULT:** changed from `'text-embedding-3-large'` to `'gemini-embedding-001'`.
- **Query-time:** server-side embedding via platform Gemini key — the querying user's BYOK key is no longer required for framework selection.

Migration: `20260407000002_gemini_embeddings_1024.sql`.

### 2026-05-18 — KIN-476: Dim bump to native 3072 via halfvec

The vector dim and column type have changed:

- **Dim:** 1024 → **3072** (gemini-embedding-001's native output dim; SDK auto-normalizes at native dim).
- **Column type:** `vector(1024)` → **`extensions.halfvec(3072)`**. `halfvec` uses 16-bit floats and stores 3072 dims in roughly the same bytes as `vector(1536)`. pgvector 0.7+ supports HNSW on `halfvec` up to 4000 dims; the prior `vector` type only supports HNSW up to 2000.
- **HNSW opclass:** `vector_cosine_ops` → **`extensions.halfvec_cosine_ops`**. Single global index `idx_fw_trigger_embeddings_hnsw` on `framework_trigger_embeddings`, and `idx_kb_chunks_embedding_hnsw` on `knowledge_base_chunks` — no scope filter.
- **§5 RPC signature change (Gilfoyle C2):** `query_embedding` parameter type changed from `vector(3072)` to **`text`**, with an internal cast `query_embedding::extensions.halfvec(3072)` inside the function body. PostgREST has no implicit JSON-array → halfvec cast, so the `text` parameter keeps Python callers (`supabase.rpc("match_framework_triggers", {...})` with `list[float]`) working unchanged.
- **Embedder dim handling:** `EmbeddingService._embed_single_batch` only passes `output_dimensionality` to the Gemini SDK when `settings.EMBEDDING_DIMS != 3072` (the native dim). At native, the SDK returns an L2-normalized vector; at non-native, the SDK returns truncated unnormalized vectors that the caller must normalize.
- **Existing data:** Wiped. The migration TRUNCATEs `framework_trigger_embeddings` (and `knowledge_base_chunks`) before the column ALTER. The admin backfill endpoint (§1) was re-run to rebuild 886 trigger embeddings across 184 frameworks.

Migration: `20260518000001_kin476_embeddings_3072_halfvec.sql`.

Synthetic verification (self-match probe via `match_framework_triggers` RPC): top result similarity = **1.0000**, semantic neighbors at **~0.75**, confirming the text → halfvec(3072) cast path works end-to-end from Python via PostgREST. `FRAMEWORK_MIN_SIMILARITY = 0.62` threshold remains appropriate at the new dim.

### Updated "Review Trigger" entries

The original "Review Trigger" list referenced `text-embedding-3-large` and a 2000-dim HNSW ceiling. Post-KIN-476, those triggers are moot. Current review triggers:

- If framework count exceeds 10K per agent (`halfvec(3072)` HNSW remains efficient at this scale; revisit if recall degrades).
- If embedding model changes from `gemini-embedding-001`.
- If pgvector is downgraded below 0.7 (would break the `halfvec` HNSW path).
