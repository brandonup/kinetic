# Code Review: KIN-258 — RAG Retrieval Pipeline

**Reviewer:** Gilfoyle
**Date:** 2026-03-22
**Ticket:** KIN-258 — [Big Head] Implement RAG retrieval pipeline
**Files reviewed:** `app/services/rag/retrieval.py`, `tests/test_rag_retrieval.py`, `tests/conftest.py` (RAG fixtures)
**Spec refs:** `docs/rag-architecture.md`, `docs/db-schema-spec.md §13`

---

## Verdict: Changes requested

**1 Important, 0 Critical.**

---

## Findings

### 1. [Important] Deleted document leakage during 7-day cleanup window

**File:** `app/services/rag/retrieval.py:245-271`
**Category:** `spec-gap`

**Issue:** The fallback select path correctly filters `deleted_at IS NULL` on chunks (line 255), but does not check whether the parent document has been soft-deleted. Per MEMORY.md decision (2026-03-22): "Document deletion: soft-delete with deferred cleanup. `deleted_at` timestamp; chunks cleaned up after 7 days." During the 7-day window between document deletion and chunk cleanup, chunks may still have `deleted_at = NULL` even though their parent document is deleted.

The RPC path (`match_chunks`) may or may not handle this — the function isn't defined in this codebase, so the assumption is undocumented.

**Fix:**
- Fallback select: add `.is_("knowledge_base_documents.deleted_at", "null")` to the joined query (or filter post-fetch).
- RPC path: document the assumption that `match_chunks` filters deleted documents, and verify with the DB migration that creates it.

### 2. [Minor] `test_mmr_respects_token_budget` misplaced in `TestMMRSelection`

**File:** `tests/test_rag_retrieval.py:130-173`
**Category:** `test-missing`

**Issue:** This test lives in `TestMMRSelection` but tests `_apply_token_budget`, not MMR. The test name and class placement are misleading — it patches `RAG_MAX_TOKENS_FLOOR` and calls `_apply_token_budget` directly.

**Fix:** Move to its own `TestTokenBudget` class, or rename `TestMMRSelection` to reflect it covers both. Minor, not blocking.

### 3. [Minor] Pure Python cosine similarity at production dimensions

**File:** `app/services/rag/retrieval.py:107-114`
**Category:** `other`

**Issue:** `_cosine_similarity` is pure Python operating on 3072-dimensional vectors. In MMR, this runs ~160 times (20 candidates * 8 selections). At production dimensions, this is O(500K) float operations per query — likely 50-200ms in CPython.

**Not blocking for MVP** (~5 users). If latency becomes an issue, swap to `numpy.dot` / `numpy.linalg.norm` — the interface is unchanged.

### 4. [Note] `EmbeddingService()` instantiated per call

**File:** `app/services/rag/retrieval.py:405`

`EmbeddingService()` is created on every `retrieve()` call. If initialization involves API client setup, this adds overhead. If it's lightweight (just stores a key), it's fine. Verify and consider making it a module-level singleton or a parameter.

### 5. [Note] Tokenizer approximation

`cl100k_base` is the GPT-3.5/4 tokenizer. For Anthropic/Google models, token counts will differ. Since this is budget estimation (not exact billing), the approximation is acceptable. No action needed — just documenting the tradeoff.

---

## What's correct

- **Pipeline structure matches spec exactly:** embed → vector search → MMR → threshold → token budget → citation assembly. Zero LLM calls.
- **Config constants match `rag-architecture.md`:** VECTOR_TOP_K=20, MMR_TOP_K=8, MMR_LAMBDA=0.6, SIMILARITY_THRESHOLD=0.3, RAG_MAX_TOKENS = max(2048, 15% of context window).
- **Supabase calls wrapped in `run_in_executor`** per AC.
- **MMR implementation is correct:** first pick by similarity, subsequent picks balance relevance vs. redundancy. Handles empty candidates and top_k > len(candidates).
- **Graceful degradation:** empty query returns [], empty vector search returns [], all-below-threshold returns []. No 500 errors on empty results.
- **RPC-first with fallback:** production uses `match_chunks` RPC; tests use filtered select. Clean separation.
- **Citation assembly populates all required fields:** document_id, document_title, chunk_index, similarity_score, section_path, page_range, scope.
- **Test coverage is solid:** MMR diversity, threshold gating (above/below), citation metadata, citation attribution, token budget. Fixtures are well-structured.
