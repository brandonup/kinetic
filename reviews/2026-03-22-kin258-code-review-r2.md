# Code Review R2: KIN-258 — RAG Retrieval Pipeline

**Reviewer:** Gilfoyle
**Date:** 2026-03-22
**Ticket:** KIN-258 — [Big Head] Implement RAG retrieval pipeline
**Round:** 2 (re-review after changes requested in R1)

---

## Verdict: Architecture approved

**0 Critical, 0 Important.** Both R1 findings addressed.

---

## R1 Findings — Resolution

### 1. [Important] Deleted document leakage — FIXED

`retrieval.py:259-279`: Fallback select now includes `knowledge_base_documents.deleted_at` in the inner join select and filters `.is_("knowledge_base_documents.deleted_at", "null")`. Comment documents the 7-day cleanup window rationale. Clean fix.

### 2. [Minor] Test class misplacement — FIXED

`test_rag_retrieval.py:135-168`: `test_mmr_respects_token_budget` moved to `TestTokenBudget` class. Test also improved — uses settings values for budget computation instead of monkey-patching module constants.

---

## LGTM. No new findings.
