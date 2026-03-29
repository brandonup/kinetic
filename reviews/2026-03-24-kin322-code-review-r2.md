# Code Review: KIN-322 — MCP server: RAG pipeline (L8, L9) + framework selection (L7)

**Reviewer:** Gilfoyle
**Date:** 2026-03-24
**Round:** R2
**Verdict:** APPROVED

---

## Files Reviewed

| File | Status | Lines |
|---|---|---|
| `app/services/rag/framework_selection.py` | Updated | 158 |
| `app/api/routes/mcp.py` | Updated | 456 |
| `tests/test_mcp.py` | Unchanged | 1016 |
| `tests/test_framework_selection.py` | NEW | 200 |
| `docs/specs/mcp-spec.md` §4.4, §4.5 | Updated | — |

## R1 Findings — Resolution

| ID | Severity | Fix Status | Notes |
|---|---|---|---|
| C1 | Critical | Fixed | Haiku reranker deferred with Brandon approval. Spec §4.4 updated to 3-step pipeline. Reranker row removed from §4.5 key table. Code and spec aligned. |
| I1 | Important | Fixed | `retrieve()` calls now wrap `body.project_id` / `body.agent_id` in `UUID()`. |
| I2 | Important | Fixed | Fallback path removed. RPC failure caught by outer try/except, returns `no_match` (fail-open). |
| I3 | Important | Fixed | New `tests/test_framework_selection.py` — 10 tests across 4 classes covering no-match, threshold gating, multi-trigger boost, text assembly, and fail-open on embedding/RPC failure. |

## New Observations (cosmetic — not blocking)

- Module docstring in `framework_selection.py` (lines 2-8) still describes a "4-step pipeline" with Haiku reranker. Should be updated to match the 3-step reality. Not a functional issue.

## Test Results

66 passed (56 MCP + 10 framework selection), 0 skipped.

---

## Summary

| Severity | Count |
|---|---|
| Critical | 0 |
| Important | 0 |

All R1 findings resolved. Spec and implementation are aligned on the 3-step MVP pipeline. Framework selection logic is clean, well-tested, and correctly wired into the MCP context endpoint. LGTM.
