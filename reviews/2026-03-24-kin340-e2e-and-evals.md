---
Status: Complete
Ticket: KIN-340
Date: 2026-03-24
---

# KIN-340 — E2E Integration Tests + Eval Suite Finalization

## Summary

E2E test suite complete — all 7 user journey tests passing. KIN-328 eval results reviewed and documented. Framework selection eval plan written; live run blocked on seeded environment.

## E2E Tests: Done

**File:** `packages/api/tests/test_e2e_flows.py`

| Journey | Status |
|---|---|
| 1 — Onboarding | ✅ |
| 2 — KB Ingestion | ✅ |
| 3 — Agent Setup | ✅ |
| 4 — Generation | ✅ |
| 5 — Active Memory | ✅ |
| 6 — MCP | ✅ |
| 7 — Admin Flows | ✅ |

Full suite: **332 passed, 6 skipped.** Run: `python -m pytest tests/test_e2e_flows.py -v`

## KIN-328 Eval Review: Done

| Eval | Target Met | Notes |
|---|---|---|
| Active Memory proposal quality | ✅ Mean 2.0 ≥ 1.5 target | Dry run — live run required to confirm |
| Linked Upload name precision | ❌ 21% vs 85% target | Dry run mock artifact + real prompt issues identified |
| Linked Upload relevance | ✅ 3.0/3.0 ≥ 2.0 target | Dry run — live run required |

**Linked Upload name precision gap requires follow-up:** Two real prompt issues identified from failure patterns:
1. Profile: no explicit null-return instruction when no individual author is identifiable
2. Company: prompt doesn't enforce stripping taglines/emojis/preamble from extracted name

Fix tickets should be opened by Brandon before Linked Upload ships to production.

## Framework Selection Eval: Plan Only

**File:** `docs/evals/2026-03-24-kin340-framework-selection-eval.md`

20 queries defined (15 on-topic, 5 off-topic). Eval runner script not yet built. Requires seeded agent with frameworks + live embedding service. Blocked on live environment.

## Fix Tickets Needed

| Issue | Severity | Action |
|---|---|---|
| Linked Upload profile name extraction: null-return when no individual | Medium | Prompt fix before shipping Linked Upload |
| Linked Upload company name: strip taglines + preamble | Medium | Prompt fix before shipping Linked Upload |
| Framework selection eval live run | Low | Run after seeded environment is available |

## Files Modified / Created

- `packages/api/tests/test_e2e_flows.py` — new (7 E2E journey tests)
- `docs/evals/2026-03-23-kin328-active-memory-eval.md` — new
- `docs/evals/2026-03-23-kin328-linked-upload-eval.md` — new
- `docs/evals/2026-03-24-kin340-framework-selection-eval.md` — new (plan)
- `docs/evals/2026-03-24-kin340-e2e-flows.md` — new

## Recommendation

**Ship the E2E test suite.** Block Linked Upload on prompt fixes before go-live. Framework selection eval can run post-launch against production data.
