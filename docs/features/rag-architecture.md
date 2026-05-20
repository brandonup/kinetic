# Kinetic — RAG Architecture

**Status:** Draft
**Last updated:** 2026-03-21
**Owner:** Brandon (CEO)

---

## Overview

Kinetic uses a Retrieval-Augmented Generation (RAG) pipeline to surface relevant content from Knowledge Bases at query time. The same pipeline runs against two different scopes: the Project Knowledge Base and the AgentDefinition Knowledge Base. Both use the same retrieval logic; they differ only in how they are namespaced and what they contain.

RAG retrieval is layers 8 and 9 of the 9-layer MVP context stack (Project KB = Layer 8, Agent KB = Layer 9). Note: the full V1 stack adds Thought Stream as Layer 7, shifting these to layers 9 and 10. It runs after all deterministic layers (user profile, company, project instructions, active memory, agent system prompt, agent active memory, and matched framework) have been assembled. RAG chunks are supplementary — they add depth and specificity without displacing the structured context above them.

---

## Two RAG Scopes

| Scope | Layer | Namespaced by | Contents | Purpose |
|---|---|---|---|---|
| **Project KB** | 8 (MVP) / 9 (full V1) | `project_id` | Client docs, transcripts, reports, notes, deliverables | Ground the AI in the specific engagement's materials |
| **Agent KB** | 9 (MVP) / 10 (full V1) | `agent_definition_id` | Thought leader corpus, domain references | Ground the AI in the agent's knowledge base |

Both scopes run the same retrieval pipeline independently and contribute separate result sets. At prompt assembly, both result sets are injected, with Project KB chunks typically appearing first (they are more specific to the current context).

---

## MVP Pipeline vs. Full V1 Pipeline

The RAG architecture is designed in layers. MVP ships with a fast, zero-LLM-call retrieval pipeline. Each enhancement in the Full V1 column can be enabled independently via configuration — no architectural changes required.

### Ingestion Pipeline

| Step | MVP | Full V1 (add later) | Config flag |
|---|---|---|---|
| Text extraction | Yes — PDF, DOCX, PPTX, TXT, MD, CSV, XLSX, JSONL | Same | Always on |
| Document-level enrichment (AI summary, key topics) | Optional — AI-generated summary for UI display. Key topics deferred. | Full enrichment: summary + key topics + document type classification | `ENRICHMENT_ENABLED` |
| Chunking | Fixed-size (~500 tokens, ~50 token overlap) | Semantic chunking (split by meaning boundaries) | `SEMANTIC_CHUNKING_ENABLED` |
| Chunk-level enrichment (per-chunk summary, keywords) | No — raw chunk text only | AI-generated summary + keywords per chunk | `CHUNK_ENRICHMENT_ENABLED` |
| Embedding | Yes — `text-embedding-3-large`, 3072 dimensions | Same | Always on |
| Indexing | pgvector (HNSW index on embedding column) | Same + GIN index on tsvector column for FTS | `FTS_ENABLED` |

**MVP ingestion flow:**

```
File Upload
    ↓
Text Extraction
(PDF, DOCX, PPTX, TXT, MD, CSV, XLSX, JSONL)
    ↓
Document-Level Summary (optional)
(AI-generated summary for UI display; key topics skipped)
    ↓
Fixed-Size Chunking
(~500 tokens per chunk, ~50 token overlap)
    ↓
Embedding
(text-embedding-3-large, 3072 dimensions, platform-owned OpenAI key)
    ↓
Indexing
(pgvector HNSW index, scoped by project_id or agent_definition_id)
```

**Supported file formats:** `.pdf`, `.docx`, `.doc`, `.pptx`, `.ppt`, `.txt`, `.md`, `.csv`, `.xlsx`, `.xls`, `.rtf`, `.jsonl`

**Upload limits:** Max 25 MB per document. Ingestion token limit: 1,000,000 tokens per document (documents exceeding this are rejected). No per-KB or per-user storage quota in MVP.

**Processing status:** Documents surface a status field in the UI: `pending → extracting → chunking → embedding → completed`. Failures are tracked per stage.

### Retrieval Pipeline

| Step | MVP | Full V1 (add later) | Config flag |
|---|---|---|---|
| Query rewriting (LLM generates 3-4 variants) | No — single query embedding | Yes — improves recall for poorly-phrased queries against large KBs | `QUERY_REWRITE_ENABLED` |
| Vector search (pgvector cosine similarity) | Yes | Yes | Always on |
| Full-text search (PostgreSQL GIN/tsvector) | No — vector search only | Yes — catches exact term/proper noun matches that embeddings miss | `FTS_ENABLED` |
| Result merging and dedup | No (single search path) | Yes — merge vector + FTS results, deduplicate | `FTS_ENABLED` |
| MMR selection (relevance/diversity balance) | Yes | Yes | Always on |
| LLM reranking (score 1-10 per chunk) | No | Yes — catches false positives from embedding similarity | `RERANKING_ENABLED` |
| Recency scoring | No | Yes — boost recent documents when relevance is close | `RECENCY_ENABLED` |
| Confidence gating | Simplified — minimum cosine similarity threshold | Full 3-tier gating (high / limited / none) based on reranker scores | `RERANKING_ENABLED` |
| Citation assembly | Yes | Yes | Always on |

**MVP retrieval flow:**

```
User Query
    ↓
Embed Query
(text-embedding-3-large, platform-owned key)
    ↓
Vector Search
(cosine similarity against scoped chunk embeddings, top-K candidates)
    ↓
MMR Selection
(balance relevance and diversity, reduce near-duplicates)
    ↓
Similarity Threshold
(below minimum → no chunks injected; above → top-K injected)
    ↓
Citation Assembly
(document title, type, section, snippet, similarity score)
    ↓
Context Injection into Prompt (Layer 8 or 9)
```

**Zero LLM calls in the MVP retrieval path.** Every query goes straight from vector search to context injection. No latency overhead from pipeline LLM calls.

---

## MVP Retrieval Details

### Vector Search

The user's query is embedded using `text-embedding-3-large` and compared against all chunk embeddings in the active scope (filtered by `project_id` or `agent_definition_id`) using cosine similarity. Returns top-K candidates.

**Production implementation:** The `match_chunks` Supabase RPC function handles scoped vector search with dynamic column filtering. The `retrieval.py` fallback select path exists as a safety net. See `db-schema-spec.md` § RPC Functions for the function signature. Framework trigger matching uses the separate `match_framework_triggers` RPC.

**Parameter:** `VECTOR_TOP_K` (default 20) — candidates returned from vector search.

### MMR Selection (Maximal Marginal Relevance)

Raw results often include near-duplicate chunks (adjacent paragraphs, repeated content). MMR selects a diverse subset by balancing relevance to the query against similarity to already-selected chunks. This ensures the injected context covers more distinct information rather than repeating the same point.

**Parameter:** `MMR_TOP_K` (default 8) — candidates after MMR selection.
**Parameter:** `MMR_LAMBDA` (default 0.6) — controls the relevance/diversity tradeoff. Higher values favor relevance; lower values favor diversity.

### Similarity Threshold

Chunks below a minimum cosine similarity score are excluded. This prevents low-quality, misleading chunks from entering the context. When no chunks exceed the threshold, the LLM responds based on its other context layers rather than hallucinating relevance.

**Parameter:** `SIMILARITY_THRESHOLD` (default 0.3) — minimum cosine similarity for a chunk to be injected. Tune based on retrieval quality observations.

### Citation Assembly

Each injected chunk is associated with:

| Citation field | Description |
|---|---|
| Document title | Name of the source document |
| Document type | Transcript, report, article, etc. |
| Section / page | Where in the document the chunk lives |
| Snippet | Short excerpt from the chunk |
| Similarity score | Cosine similarity score for this chunk |
| Source scope | Which KB it came from (Project or Agent) |

Citations are surfaced in the UI as expandable references below AI responses — traceable to source documents.

---

## Full V1 Retrieval Enhancements (Deferred)

Each enhancement below is designed to be enabled independently via its config flag. The MVP schema includes all columns needed for V1 features (e.g., `tsv`, `chunk_summary`, `keywords`) — they are nullable and unused until the corresponding feature is enabled.

### Query Rewriting (`QUERY_REWRITE_ENABLED`)

The user's raw query is rewritten into 3-4 distinct variants using an LLM. Each variant targets a different angle of the question (semantic rephrasing, keyword-heavy version, context-specific version). All variants are submitted to vector search in parallel. This improves recall when the user's phrasing doesn't closely match the document language.

**When to enable:** When KBs exceed ~500 chunks and users report "it can't find my document."

**Parameter:** `QUERY_REWRITE_VARIANTS` (default 4) — number of rewritten query variants.

### Full-Text Search (`FTS_ENABLED`)

PostgreSQL GIN-indexed tsvector columns on the chunks table. Weighted fields (title, keywords > body text). Handles exact term matching that semantic search can miss — especially proper nouns, acronyms, and technical terms.

When enabled, FTS runs in parallel with vector search. Results from both methods are merged and deduplicated before MMR.

**When to enable:** When users search for specific names, acronyms, or exact terms and vector search misses them.

### LLM Reranking (`RERANKING_ENABLED`)

The top candidates from MMR are passed to a fast LLM (or the Cohere rerank API) with the full user query. Each chunk is scored 1-10 on relevance. This catches false positives from embedding similarity — cases where chunks are semantically close but contextually irrelevant.

When enabled, replaces the simple similarity threshold with full 3-tier confidence gating:

| Confidence | Score threshold | Behavior |
|---|---|---|
| `high` | ≥ 7.0 | Full context injected with citations |
| `limited` | 4.0 – 6.9 | Reduced context injected; response notes limited sourcing |
| `none` | < 4.0 | No chunks injected; retrieval effectively disabled for this query |

**When to enable:** When KBs grow large enough that false positives from embedding similarity degrade response quality.

**Parameter:** `RERANK_TOP_K` (default 10) — candidates passed to reranker.
**Parameter:** `RERANK_SCORE_THRESHOLD` (default 6.0) — minimum score for `high` confidence.
**Parameter:** `RERANK_SCORE_LIMITED` (default 4.0) — minimum score for `limited` confidence.
**Provider:** Configurable — Cohere rerank API (preferred for speed) or LLM-based scoring.

### Recency Scoring (`RECENCY_ENABLED`)

After the base relevance score is assigned (either similarity score or reranker score), a recency modifier is applied. The modifier uses the chunk's parent document date (`document_date` if set, otherwise `created_at` as fallback):

| Document age | Modifier |
|---|---|
| < 30 days | +0.5 |
| 30 days – 6 months | +0.2 |
| 6 months – 2 years | 0 (neutral) |
| > 2 years | -0.3 |

**When to enable:** When KBs contain documents spanning years and users need recent content to surface preferentially.

**Parameter:** `RECENCY_WEIGHT` (default 1.0) — scaling factor for the recency modifier. Set to 0 to disable.

### Chunk-Level Enrichment (`CHUNK_ENRICHMENT_ENABLED`)

Each chunk gets an AI-generated summary and keyword list at ingestion time. These improve both vector search quality (richer embedding input) and FTS matching (more keyword surface). Requires an LLM call per chunk — the most expensive ingestion step.

**When to enable:** When retrieval quality plateaus and enriched metadata would meaningfully improve matching.

### Semantic Chunking (`SEMANTIC_CHUNKING_ENABLED`)

Replace fixed-size chunking with meaning-boundary chunking — splitting at paragraph breaks, section headers, and topic transitions. Preserves more context per chunk but requires more complex parsing logic per document type.

**When to enable:** When users report that retrieved chunks feel fragmented or cut off mid-thought.

---

## Storage Architecture

Kinetic uses **pgvector** (PostgreSQL extension) for vector storage, avoiding a separate vector database. This is consistent with the decision to use Supabase (which supports pgvector natively) and avoids operational overhead.

### Tables

**`knowledge_base_documents`**

| Column | Type | Description | MVP |
|---|---|---|---|
| id | uuid | Primary key | Yes |
| knowledge_base_id | uuid | Parent KB (FK to knowledge_bases) | Yes |
| title | text | Document name | Yes |
| file_type | text | MIME type / extension | Yes |
| storage_uri | text | File location in Supabase Storage | Yes |
| summary | text | AI-generated document summary (nullable — populated if doc-level enrichment is enabled) | Yes (optional) |
| key_topics | text[] | AI-extracted topics (nullable — populated when full enrichment enabled) | Column exists, null in MVP |
| document_date | date (nullable) | Publication/creation date of the content. Used for recency scoring when enabled. If not set, `created_at` is the fallback. | Column exists, null in MVP |
| status | enum | `pending`, `extracting`, `chunking`, `embedding`, `completed`, `failed` | Yes |
| error_stage | text | Which stage failed, if any | Yes |
| retry_count | int | Number of retry attempts | Yes |
| error_message | text | Error details for failed stage | Yes |
| created_at | timestamp | Upload date | Yes |

**`knowledge_base_chunks`**

| Column | Type | Description | MVP |
|---|---|---|---|
| id | uuid | Primary key | Yes |
| document_id | uuid | Parent document (FK) | Yes |
| knowledge_base_id | uuid | Denormalized for query efficiency | Yes |
| project_id | uuid (nullable) | Scope — set if KB belongs to a Project | Yes |
| agent_definition_id | uuid (nullable) | Scope — set if KB belongs to an AgentDefinition | Yes |
| text | text | Chunk content | Yes |
| embedding | vector(3072) | pgvector embedding | Yes |
| chunk_summary | text | AI-generated chunk summary (nullable — populated when chunk enrichment enabled) | Column exists, null in MVP |
| keywords | text[] | AI-extracted keywords (nullable — populated when chunk enrichment enabled) | Column exists, null in MVP |
| section_path | text | Location in document (heading hierarchy) | Yes |
| page_range | text | Page numbers (for PDFs) | Yes |
| chunk_index | int | Position within document | Yes |
| tsv | tsvector | FTS index (nullable — populated when FTS enabled) | Column exists, null in MVP |
| embedding_model | text | Model used to generate this embedding (supports future migrations) | Yes |
| created_at | timestamp | | Yes |

**Why include V1 columns in the MVP schema:** Adding nullable columns now avoids a schema migration when V1 features are enabled. The columns cost nothing when null — no storage, no index overhead. Enabling a feature later is a code change + backfill, not a migration.

**Index strategy:**

| Index | Type | MVP | V1 |
|---|---|---|---|
| `embedding` column | HNSW (pgvector), filtered by scope | Yes | Yes |
| `tsv` column | GIN (PostgreSQL FTS) | No — created when `FTS_ENABLED` | Yes |
| `project_id` | B-tree | Yes | Yes |
| `agent_definition_id` | B-tree | Yes | Yes |
| `document_id` | B-tree | Yes | Yes |

---

## Namespace Isolation

Every chunk is stamped with either `project_id` or `agent_definition_id` at ingestion. All queries filter by the active scope before running vector search. This ensures:

- Project A's documents are never retrieved in Project B's context
- Agent KB chunks are not mixed with Project KB chunks in the same retrieval pass
- When a user switches companies or projects, the correct chunk pool is queried automatically

---

## Embedding Model

**Model:** `text-embedding-3-large` (OpenAI)
**Dimensions:** 3072
**Similarity metric:** Cosine similarity
**Key ownership:** Platform-owned OpenAI API key. Embedding costs are absorbed by the platform — users do not need an OpenAI key for KB functionality.

The same embedding model is used at ingestion (chunk embedding) and at query time (query embedding). Using different models for these would degrade retrieval quality. The `embedding_model` column on each chunk records which model was used, supporting future model migrations.

---

## Context Injection

After retrieval, chunks are formatted and injected into the prompt context at layers 8 and 9:

```
[Project Knowledge Base Context]
Source: {document_title} ({document_type})
Section: {section_path}
---
{chunk_text}
[Relevance: {score}]

[Agent Knowledge Base Context]
Source: {document_title} ({document_type})
Section: {section_path}
---
{chunk_text}
[Relevance: {score}]
```

**Token budget:** The combined Project KB + Agent KB retrieval is capped to avoid crowding out deterministic layers. If the token budget is exceeded, lower-scoring chunks are dropped.

**Parameter:** `RAG_MAX_TOKENS` — total token budget for all RAG chunks combined (default TBD based on model context window).

---

## Framework Library: Not RAG

The Framework Library (layer 7 of the context stack) uses pgvector for its `when_to_apply` trigger embeddings, but it is **not a RAG pipeline**. Key differences:

| Dimension | RAG (KB chunks) | Framework selection |
|---|---|---|
| What's stored | Text chunks from documents | Structured framework entities |
| Storage | Chunked into many rows | One row per trigger phrase |
| Retrieval | Top-K chunks returned | Single best-match returned |
| Injection | Multiple chunks as context | One framework injected whole |
| Pipeline | Vector search → MMR → threshold → inject (MVP) | 4-step classifier (embedding similarity, expertise boost, LLM reranker, inject) |

Frameworks are documented separately in the domain model under **Framework Selection Architecture**.

---

## Debug Tracing

Every retrieval is logged for debugging and quality improvement:

**`retrieval_debug_logs` table:**

| Column | Description |
|---|---|
| message_id | FK to the conversation message |
| scope | `project_kb` or `agent_kb` |
| query_text | The original user query |
| query_variants | The rewritten query variants (null in MVP — single query) |
| vector_candidates | Pre-MMR candidates (scores, chunk IDs) |
| mmr_selections | Post-MMR selections |
| rerank_scores | Per-chunk reranker scores (null in MVP) |
| gating_decision | `injected` or `below_threshold` (MVP); `high`, `limited`, or `none` (V1) |
| injected_chunks | Final chunks that made it into the prompt |
| created_at | Timestamp |

Logs auto-purge after 30 days. Admin can inspect traces per message via the Admin panel's RAG Debug tab.

---

## Configuration Parameters

### MVP Parameters

| Parameter | Default | Description |
|---|---|---|
| `RAG_ENABLED` | `true` | Enable/disable RAG retrieval entirely |
| `VECTOR_TOP_K` | `20` | Candidates returned from vector search |
| `MMR_TOP_K` | `8` | Candidates after MMR selection |
| `MMR_LAMBDA` | `0.6` | Relevance/diversity tradeoff (higher = more relevant) |
| `SIMILARITY_THRESHOLD` | `0.3` | Minimum cosine similarity for chunk injection |
| `RAG_MAX_TOKENS` | TBD | Token budget for all RAG chunks combined |
| `ENRICHMENT_ENABLED` | `true` | Enable/disable document-level summary generation at ingestion |

### V1 Enhancement Flags (all default `false` in MVP)

| Parameter | Default | Description | Enables |
|---|---|---|---|
| `QUERY_REWRITE_ENABLED` | `false` | LLM query rewriting (3-4 variants) | Better recall for large KBs |
| `QUERY_REWRITE_VARIANTS` | `4` | Number of rewritten query variants | — |
| `FTS_ENABLED` | `false` | Full-text search (GIN index, hybrid merge) | Exact term matching |
| `RERANKING_ENABLED` | `false` | LLM reranking + 3-tier confidence gating | Precision filtering |
| `RERANK_TOP_K` | `10` | Candidates passed to reranker | — |
| `RERANK_SCORE_THRESHOLD` | `6.0` | Minimum score for `high` confidence | — |
| `RERANK_SCORE_LIMITED` | `4.0` | Minimum score for `limited` confidence | — |
| `RECENCY_ENABLED` | `false` | Recency scoring modifier | Recent content preference |
| `RECENCY_WEIGHT` | `1.0` | Scaling factor for recency modifier | — |
| `CHUNK_ENRICHMENT_ENABLED` | `false` | Per-chunk AI summary + keywords at ingestion | Richer search metadata |
| `SEMANTIC_CHUNKING_ENABLED` | `false` | Meaning-boundary chunking instead of fixed-size | Better chunk coherence |

---

## Scale Assumptions

The MVP RAG architecture is designed for **≤50 users and ≤10M words of total KB content** (roughly ~20K chunks across all users). At this scale:

- pgvector HNSW index handles similarity search in <100ms
- Vector-only retrieval (no FTS hybrid) has sufficient recall
- Fixed-size chunking produces acceptable chunk quality
- No query rewriting or LLM reranking needed

**When to revisit:** If any of these thresholds are exceeded, or if retrieval quality degrades measurably (monitored via debug traces), enable V1 enhancements incrementally — starting with FTS (cheapest improvement) and LLM reranking (biggest precision gain).

---

## Open Questions

1. **Token budget allocation:** When both Project KB and Agent KB return results, how is the shared token budget split? Fixed split (e.g., 60% project / 40% agent), dynamic based on scores, or user-configurable?
2. **Chunk size:** Is ~500 tokens the right target for fixed-size chunking, or should it be larger (more context per chunk) or smaller (more precision)?
3. **Re-indexing on document delete:** When a document is deleted, its chunks should be removed from the vector index. Is this a synchronous hard delete or a soft-delete with deferred cleanup?
