# Code Review: KIN-322 — MCP server: RAG pipeline (L8, L9) + framework selection (L7)

**Reviewer:** Gilfoyle
**Date:** 2026-03-24
**Round:** R1
**Verdict:** CHANGES REQUESTED

---

## Files Reviewed

| File | Status | Lines |
|---|---|---|
| `app/services/rag/framework_selection.py` | NEW | 170 |
| `app/api/routes/mcp.py` | Updated | 455 |
| `tests/test_mcp.py` | Updated | 1016 |

## Specs Referenced

- `docs/specs/mcp-spec.md` §4.3, §4.4, §5
- `docs/rag-architecture.md`
- `docs/adr-003-agents-architecture.md`
- `docs/db-schema-spec.md` §14 (frameworks), §15 (framework_trigger_embeddings)

---

## Findings

### C1 — Critical: Haiku reranker omitted without spec update or approval

**File:** `app/services/rag/framework_selection.py` line 127
**Issue:** The spec (mcp-spec.md §4.4 step 2, bullet 3) and MEMORY.md locked decision both specify a 4-step pipeline: (1) embedding similarity, (2) multi-trigger boost, (3) **Haiku reranker on top-5**, (4) confidence gate. The implementation skips step 3 entirely with a code comment "skip Haiku reranker for MVP — use boosted score." This is a unilateral scope reduction on a spec'd behavior. The reranker is what prevents false-positive framework matches — without it, the pipeline degrades to embedding similarity + a tie-breaker boost, which is the exact configuration the reranker was added to compensate for.
**Fix:** Either (a) implement the Haiku reranker as spec'd — the `PLATFORM_ANTHROPIC_KEY` is already committed to for this purpose — or (b) get explicit approval from Brandon/Gilfoyle to defer the reranker and update mcp-spec.md §4.4 + MEMORY.md to reflect the 3-step MVP pipeline. Do not ship with a spec that says one thing and code that does another.

### I1 — Important: Type mismatch — `retrieve()` receives `str` instead of `UUID`

**File:** `app/api/routes/mcp.py` lines 361, 372
**Issue:** `retrieve()` signature declares `scope_id: UUID` (from `uuid` module). The MCP route passes `body.project_id` and `body.agent_id`, both `Optional[str]`. Works at runtime only because `_build_scope_filter` calls `str(scope_id)` on the value — but this violates the type contract and will break if `retrieve` ever adds input validation.
**Fix:** Wrap in `UUID(body.project_id)` / `UUID(body.agent_id)` at the call site. UUID validation already runs earlier (lines 243-249), so the conversion is safe.

### I2 — Important: Fallback path in framework selection returns meaningless scores

**File:** `app/services/rag/framework_selection.py` lines 90-100, 109
**Issue:** When `match_framework_triggers` RPC is unavailable, the fallback queries the `framework_trigger_embeddings` table directly — but returns raw rows without computing cosine similarity. `trigger.get("similarity", 0.0)` defaults every trigger to 0.0. The multi-trigger boost then scores frameworks purely by trigger count (`(count - 1) * 0.05`). A framework with 12 triggers scores 0.55 — barely clearing the 0.55 gate — regardless of query relevance. This makes the fallback a trigger-count selector, not a relevance pipeline.
**Fix:** Either (a) remove the fallback entirely and let the outer `try/except` handle RPC failure (returning `no_match`), or (b) compute cosine similarity in Python against `query_embedding` in the fallback path. Option (a) is simpler and consistent with the fail-open design — if the RPC is unavailable, omit L7 rather than produce a random match.

### I3 — Important: No unit tests for `framework_selection.py`

**File:** `app/services/rag/framework_selection.py` (all), `tests/test_mcp.py`
**Issue:** The new 170-line service module has zero dedicated unit tests. The five new tests verify MCP route integration only (L7/L8/L9 appear in assembled layers, sources populated). The pipeline's core logic — multi-trigger boosting, confidence gating, framework text assembly, edge cases (no triggers returned, single trigger, tie-breaking) — is untested.
**Fix:** Add `tests/test_framework_selection.py` with direct unit tests covering: (a) boosted_score calculation with 1 vs. multiple triggers, (b) confidence gate rejects below 0.55, (c) framework text assembly with missing optional fields, (d) no triggers → no_match, (e) RPC failure fallback behavior (once I2 is resolved). The MCP integration tests are valuable but they only exercise the happy path through mocked returns.

---

## Summary

| Severity | Count | IDs |
|---|---|---|
| Critical | 1 | C1 |
| Important | 3 | I1, I2, I3 |

The MCP route integration (L7/L8/L9 wiring, sources metadata, fail-open pattern) is solid. The framework_selection service structure is clean. The blocking issue is C1: the Haiku reranker is spec'd, budgeted for (platform key), and omitted without approval. That is a spec gap, not a simplification.
