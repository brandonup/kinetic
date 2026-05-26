---
Status: Stale plan — pending re-run on the Gemini-embedded corpus (see KIN-497).
        Original plan referenced OpenAI `text-embedding-3-large`; KIN-467 migrated
        the platform embedding to Gemini `gemini-embedding-001` in March 2026.
Ticket: KIN-348 (superseded for execution by KIN-497)
Date: 2026-03-24
Run type: Pending (requires seeded KB with indexed chunks + live embedding service)
---

# KIN-348 — RAG Retrieval Precision Eval

## Target

Retrieval pipeline returns relevant, non-redundant chunks with correct citations for a variety of query types and KB configurations.

## Pipeline Under Test

`app/services/rag/retrieval.py::retrieve()` — 5-step pipeline:

1. **Embed query** → `gemini-embedding-001` (platform Gemini key — KIN-467)
2. **Vector search** → pgvector `match_chunks` RPC, returns `VECTOR_TOP_K=20` candidates
3. **MMR selection** → reduce to `MMR_TOP_K=8`, `MMR_LAMBDA=0.6` (relevance/diversity tradeoff)
4. **Similarity threshold** → exclude chunks below `SIMILARITY_THRESHOLD=0.3`, return `[]` if none qualify
5. **Token budget** → greedily fill `RAG_MAX_TOKENS` (15% of model context, min 2048)

## Eval 1 — MMR Selection Quality

**Question:** Does MMR produce diverse, non-redundant chunk sets?

| # | Scenario | Expected |
|---|---|---|
| M1 | KB with 5 near-duplicate chunks (same paragraph, minor edits) | MMR returns 1–2 representatives, not all 5 |
| M2 | KB with chunks from 3 distinct topics | MMR returns mix from all 3 topics (not just the top-scoring topic) |
| M3 | Query that matches one topic strongly, others weakly | Top chunk is strong match; remaining fill with diverse weak matches |
| M4 | Lambda=1.0 (pure relevance, no diversity) | Top-K by raw similarity, near-duplicates not penalized |

**Metric:** Intra-set diversity score = 1 - mean(pairwise cosine similarity among selected chunks). Target: ≥ 0.3 for M1–M3.

## Eval 2 — Threshold Gating Correctness

**Question:** Does the threshold gate prevent low-quality chunks from being injected?

| # | Scenario | Expected |
|---|---|---|
| G1 | Query completely unrelated to any KB content | `[]` returned (all below 0.3 threshold) |
| G2 | Query partially related — 3 of 20 candidates above threshold | Only 3 returned |
| G3 | Query very relevant — 15 of 20 above threshold | MMR selects 8 from the 15 |
| G4 | Threshold set to 0.0 (disabled) | All MMR candidates returned regardless of similarity |

**Metric:** False injection rate = chunks injected with cosine sim < 0.3 / total injected. Target: 0%.

## Eval 3 — Citation Assembly Accuracy

**Question:** Do retrieved chunks carry correct source metadata for UI citations?

| # | Scenario | Expected |
|---|---|---|
| C1 | Chunk from PDF document | `source.document_title`, `source.file_type="pdf"` populated |
| C2 | Chunk from DOCX document | `source.file_type="docx"` populated |
| C3 | Two chunks from same document | Same `document_id` in both, different `chunk_index` |
| C4 | Chunk from deleted document (soft-deleted, within 7-day window) | Still returned (cleanup hasn't run). `source` metadata populated. |
| C5 | Chunk from hard-deleted document (cleanup ran) | Not returned (chunk no longer in index) |

**Metric:** Citation accuracy = chunks with correct source metadata / total chunks. Target: 100%.

## Eval 4 — Token Budget Compliance

**Question:** Does the pipeline respect `RAG_MAX_TOKENS` and fill greedily?

| # | Scenario | Expected |
|---|---|---|
| B1 | 8 MMR chunks, total tokens = 1500, budget = 2048 | All 8 returned (within budget) |
| B2 | 8 MMR chunks, total tokens = 5000, budget = 2048 | Partial fill — first N chunks that fit within 2048 |
| B3 | Single chunk = 3000 tokens, budget = 2048 | Single chunk returned (first chunk always included) |
| B4 | Budget = 0 (edge case) | `[]` returned |

**Metric:** Over-budget rate = retrievals where total tokens > budget / total retrievals. Target: 0% (excluding B3 first-chunk exception).

## Unit Test Coverage (in CI)

`tests/test_rag_retrieval.py` covers:
- `TestMMRSelection::test_mmr_returns_diverse_chunks` — diversity verified
- `TestTokenBudget::test_mmr_respects_token_budget` — budget enforcement
- `TestThresholdGating::test_chunks_below_threshold_are_excluded` — threshold filter
- `TestThresholdGating::test_no_chunks_returned_when_all_below_threshold` — empty return
- `TestCitationAssembly::test_retrieved_chunks_include_source_metadata` — metadata populated
- `TestCitationAssembly::test_citations_reference_correct_document` — document ID correct

Unit tests use mocked embeddings. This eval tests against real embedded content to verify end-to-end quality.

## Live Run Requirements

- Seeded KB with ≥50 indexed chunks across ≥5 documents (mix of PDF, DOCX, text)
- Near-duplicate chunks for MMR diversity testing
- Off-topic content for threshold gating
- Live `EmbeddingService` (platform OpenAI key for `text-embedding-3-large`)

Run command (once environment ready):
```bash
python evals/rag_retrieval/eval_runner.py --kb-id <seeded-kb-id>
```

Eval runner script does not yet exist — create as part of live run setup.
