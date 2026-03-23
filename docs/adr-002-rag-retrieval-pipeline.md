# ADR-002: RAG Retrieval Pipeline Architecture

**Status:** Proposed
**Author:** Gilfoyle
**Date:** 2026-03-22
**Project:** Kinetic
**Implementation:** KIN-258 (Big Head)

---

## Context

Kinetic's 9-layer context stack includes two RAG layers: Project KB (Layer 8) and Agent KB (Layer 9). At query time, these layers retrieve relevant document chunks from knowledge bases and inject them into the prompt alongside deterministic context (user profile, company, project instructions, active memory, agent system prompt, frameworks).

The retrieval pipeline must balance three forces:

1. **Latency:** Every retrieval call adds latency before the first token streams. Extra LLM calls in the pipeline (query rewriting, reranking) compound this.
2. **Precision:** Injecting irrelevant chunks wastes context window tokens and can mislead the model. False positives from embedding similarity are a known failure mode.
3. **Simplicity:** The MVP targets ~50 users and ~20K chunks. Over-engineering the pipeline for millions of chunks adds complexity with no return at current scale.

The RAG architecture spec (`docs/rag-architecture.md`) defines both the MVP pipeline and a set of V1 enhancements, each gated behind independent config flags. This ADR documents the decisions that shaped the MVP pipeline and the rationale for each parameter choice.

---

## Decision

### Zero-LLM Retrieval Path

The MVP retrieval pipeline uses **zero LLM calls**:

```
Embed Query → Vector Search → MMR Selection → Similarity Threshold → Token Budget → Citation Assembly
```

Every step is deterministic or statistical. No LLM reranking, no query rewriting, no confidence scoring. The only external call is the embedding request (platform-owned OpenAI key, `text-embedding-3-large`).

**Why:** At ~20K chunks and ~50 users, embedding similarity + MMR provides sufficient retrieval quality. Adding an LLM reranker (e.g., Haiku) would add ~200-500ms latency per query for marginal precision gains at this scale. The config-flag architecture means reranking can be enabled with a single flag flip when scale demands it — no pipeline changes required.

### MMR Configuration

**Parameters:** `VECTOR_TOP_K=20`, `MMR_TOP_K=8`, `MMR_LAMBDA=0.6`

- **VECTOR_TOP_K=20:** Fetch 20 candidates from pgvector. This is 2.5x the final target (8), providing enough headroom for MMR to find diverse selections. Going higher (50+) adds I/O cost with diminishing diversity gains for small KBs.
- **MMR_TOP_K=8:** 8 chunks after MMR selection. At ~500 tokens per chunk, this is ~4,000 tokens — well within the 15% budget for even the smallest supported models (128K context = 19,200 token budget). Empirically, 5-10 chunks provides a good information density without repetition.
- **MMR_LAMBDA=0.6:** Tilts slightly toward relevance over diversity. A value of 1.0 would be pure relevance (no diversity penalty); 0.0 would be pure diversity. 0.6 preserves topical coherence while still penalizing near-duplicate chunks from adjacent paragraphs. This is the standard starting point in the MMR literature; adjust based on retrieval quality feedback.

### Similarity Threshold

**Parameter:** `SIMILARITY_THRESHOLD=0.3`

Chunks below 0.3 cosine similarity are excluded entirely. When no chunks meet the threshold, the model responds using its other context layers (system prompt, active memory, frameworks) rather than injecting low-quality chunks that could mislead.

**Why 0.3:** With `text-embedding-3-large` (3072 dimensions), cosine similarity scores tend to be lower than with smaller models. A threshold of 0.3 filters obvious non-matches while preserving topically adjacent content. This is conservative — it can be raised to 0.4-0.5 if false positives are observed.

### RAG_MAX_TOKENS

**Formula:** `max(2048, int(model_context_window * 0.15))`

**Parameter:** `RAG_MAX_TOKENS_PERCENT=0.15`, `RAG_MAX_TOKENS_FLOOR=2048`

| Model Context | RAG Budget |
|---|---|
| 8K (small models) | 2,048 (floor) |
| 32K | 4,800 |
| 128K (Claude) | 19,200 |
| 200K (Claude extended) | 30,000 |
| 1M (Claude Opus) | 150,000 |

**Why 15%:** The 9-layer context stack must fit within the model's context window alongside the conversation history and the current message. Layers 1-7 (user profile through frameworks) are typically 2,000-8,000 tokens combined. Conversation history (with rolling compression) occupies the largest share. 15% for RAG leaves room for everything else while providing meaningful retrieval depth.

**Why floor 2048:** Even on small-context models, the pipeline should inject at least 4-5 chunks to be useful. At ~500 tokens per chunk, 2048 tokens fits 4 chunks.

### Token Budget Allocation

**Strategy:** Dynamic score-based (greedy fill by MMR rank).

Chunks are ordered by MMR score (which already balances relevance and diversity). The budget is filled greedily from the top — each chunk is added if it fits, skipped if it would exceed the budget. No fixed ratio between Project KB and Agent KB.

**Why not fixed ratio (e.g., 60/40):** The ratio between project-relevant and agent-relevant content varies wildly by query. A project-specific question should allocate 100% to Project KB. A domain expertise question should favor Agent KB. Dynamic allocation lets the scoring decide.

**Implementation note:** When both scopes are active (project conversation with an invoked agent), the caller runs `retrieve()` twice — once per scope — and merges the results by similarity score before applying the token budget. This is handled at the context assembly layer, not within the retrieval module.

### Soft-Delete and Chunk Cleanup

**Decision:** Documents use soft-delete (`deleted_at` timestamp). Chunks of soft-deleted documents are excluded from retrieval via a filter: `knowledge_base_documents.deleted_at IS NULL`. Physical chunk cleanup runs after 7 days.

**Why soft-delete with deferred cleanup:**
- **Immediate hard-delete** of chunks on document deletion would require a synchronous cascade across potentially thousands of rows, blocking the delete request.
- **7-day window** allows undo and prevents accidental data loss. Chunks are invisible to retrieval immediately (the `deleted_at` filter fires at query time), so there is no retrieval quality impact.
- **Cleanup job** runs as a background task, purging chunks where the parent document's `deleted_at` is older than 7 days.

**Implementation ref:** `retrieval.py:261-276` — two `deleted_at` filters in the fallback select path (chunks and documents).

### pgvector Choice

**Decision:** pgvector (Supabase extension) with HNSW indexes.

| Factor | pgvector | Qdrant |
|---|---|---|
| Operational overhead | Zero — runs inside Supabase PostgreSQL | Separate service: hosting, monitoring, backup |
| Scale limit | ~1M vectors before latency degrades | 100M+ vectors |
| Current load | ~20K vectors (0.02x limit) | N/A |
| Query integration | Same transaction as scope filters and joins | Separate network call + result merge |
| Migration cost | N/A | Schema maps cleanly — scope columns → collection namespaces |

**Migration trigger:** If retrieval latency (p95) exceeds 200ms at query time, or chunk count exceeds 500K, evaluate Qdrant migration. The `embedding_model` column on chunks supports reindexing into a different store without re-embedding.

### Config-Flag Stubs for V1 Enhancements

Each V1 enhancement is designed to be enabled independently. The MVP schema includes all necessary columns (nullable, unused until enabled). Enabling a feature is a code change + potential backfill, not a schema migration.

| Flag | Enhancement | When to Enable |
|---|---|---|
| `QUERY_REWRITE_ENABLED` | LLM generates 3-4 query variants | KBs exceed ~500 chunks and users report "can't find my document" |
| `FTS_ENABLED` | PostgreSQL GIN/tsvector hybrid search | Users search exact terms, acronyms, proper nouns that embeddings miss |
| `RERANKING_ENABLED` | LLM/Cohere reranker + 3-tier confidence gating | False positives from embedding similarity degrade response quality |
| `RECENCY_ENABLED` | Recency scoring modifier on document age | KBs span years and recent content should surface preferentially |
| `CHUNK_ENRICHMENT_ENABLED` | Per-chunk AI summary + keywords at ingestion | Retrieval quality plateaus; enriched metadata would improve matching |
| `SEMANTIC_CHUNKING_ENABLED` | Meaning-boundary chunking | Users report chunks feel fragmented or cut off mid-thought |

**Recommended enablement order:** FTS first (cheapest — no LLM calls, just a GIN index + query merge), then Reranking (biggest precision gain), then Query Rewriting (biggest recall gain for large KBs).

---

## Alternatives Considered

### Retrieval Pipeline Design

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **Zero-LLM (chosen)** | Fastest latency. Simplest to debug. No pipeline LLM cost. | Lower precision than reranked pipeline at scale. | N/A |
| LLM reranker in MVP | Better precision. Catches false positives. | +200-500ms latency per query. Adds LLM cost per retrieval. Over-engineered for ~20K chunks. | Premature at MVP scale. Config flag ready. |
| Hybrid vector+FTS in MVP | Better exact-term recall. | Requires GIN index (storage overhead) + merge logic. MVP KBs are too small to benefit. | Deferred. FTS is the first V1 enhancement to enable. |

### Token Budget Strategy

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **Dynamic score-based (chosen)** | Allocates budget to best-scoring chunks regardless of source. Handles variable query types. | No guaranteed minimum per scope. | N/A |
| Fixed 60/40 ratio (project/agent) | Predictable allocation. | Wastes budget when one scope has no relevant content. Arbitrary ratio. | Over-constrains. Scoring handles allocation better. |
| User-configurable ratio | Maximum flexibility. | UI complexity. Users shouldn't need to understand token budgets. | YAGNI. Revisit if users request control. |

### Similarity Threshold

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **Fixed threshold (0.3)** | Simple. Predictable. | May need tuning per embedding model. | N/A |
| Dynamic threshold (percentile-based) | Adapts to score distribution per query. | Adds complexity. Can inject low-quality chunks when all scores are low. | Premature complexity. Fixed threshold is tunable and understandable. |
| No threshold (rely on token budget) | All MMR results injected. | Low-quality chunks waste budget. Misleading context. | Unacceptable — gating is essential. |

---

## Consequences

**Positive:**
- Zero-LLM path delivers sub-100ms retrieval latency (embedding + pgvector + MMR in-process).
- Config-flag architecture means every V1 enhancement is a code change, not a migration. No pipeline redesign needed.
- Dynamic token budget handles variable query types without user configuration.
- Soft-delete with deferred cleanup provides immediate retrieval safety without synchronous cascade costs.

**Negative:**
- No query rewriting means poorly phrased queries against large KBs will have lower recall. Users must phrase queries clearly.
- No LLM reranking means false positives from embedding similarity are injected as context. At ~20K chunks, the false positive rate is low enough to accept.
- Fixed-size chunking (~500 tokens) may split coherent sections mid-thought. Semantic chunking (V1) addresses this.
- Pure Python cosine similarity in the fallback path is O(n) — only used in tests; production uses the pgvector RPC.

**Neutral:**
- `text-embedding-3-large` at 3072 dimensions is the highest-quality OpenAI embedding model but produces larger vectors than alternatives. Storage cost at current scale is negligible (~20K * 3072 * 4 bytes = ~235 MB).

---

## Risks

- **Embedding model lock-in:** All chunks and queries use `text-embedding-3-large`. Switching models requires re-embedding all chunks. **Mitigation:** `embedding_model` column on every chunk enables incremental re-embedding. New chunks use the new model; old chunks are backfilled asynchronously.

- **MMR parameter sensitivity:** λ=0.6 and top_k=8 are starting values, not validated against Kinetic-specific content. **Mitigation:** All parameters are runtime-configurable via settings. Retrieval debug logs capture per-query scores for tuning.

- **Threshold too low (0.3):** May inject marginally relevant chunks that dilute model attention. **Mitigation:** Monitor via RAG Debug admin tab. Raise threshold if users report irrelevant citations. Lowering is also easy if recall is too aggressive.

- **Token budget on small-context models:** 2048-token floor may still crowd out conversation history on 8K-context models. **Mitigation:** Context assembly should enforce a total budget across all layers. RAG budget is a ceiling, not an entitlement — if conversation history needs the space, RAG yields.

---

## Review Trigger

Revisit this ADR when:
- Chunk count exceeds 500K across all users (pgvector scale / retrieval latency)
- Retrieval p95 latency exceeds 200ms (performance degradation)
- Users report >10% irrelevant citations in a feedback sample (precision failure)
- A new embedding model with better quality/cost is available (model migration)
- V1 enhancements are enabled — each activation should validate that this ADR's assumptions still hold
