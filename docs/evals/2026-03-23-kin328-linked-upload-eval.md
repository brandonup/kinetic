---
Status: Needs live run
Ticket: KIN-328
Date: 2026-03-23
Run type: Dry run (mock LLM scores; name precision computed from mock extraction)
---

# KIN-328 — Linked Upload Extraction Accuracy Eval

## Summary

| Metric | Result | Target | Status |
|---|---|---|---|
| Documents tested | 30 | 30 | ✅ |
| Errors | 0 | 0 | ✅ |
| **Name precision (overall)** | **21.1%** | **≥ 85%** | **❌ BELOW TARGET** |
| Name precision — profile | 11.1% | ≥ 85% | ❌ |
| Name precision — company | 30.0% | ≥ 85% | ❌ |
| Name precision — agent | N/A (expected null) | — | — |
| Relevance mean | 3.0 / 3.0 | ≥ 2.0 | ✅ (mocked) |

**Verdict: Relevance pipeline validates. Name extraction requires live run — precision is a known dry-run limitation, but failure patterns reveal real prompt issues to fix before shipping.**

## Name Precision Analysis

The dry run uses a fixed mock extraction function (not a real LLM call), so precision directly measures whether the mock's hardcoded output matches the expected name — not real extraction accuracy. However, the failure modes expose prompt design issues that apply to a real run:

### Profile surface (1/9 = 11%)

- Mock always returned "Sarah Chen" regardless of document. In a real run, the prompt must handle: personal bios, CVs, LinkedIn profiles, no-clear-author docs.
- **Risk:** If the real prompt doesn't gracefully return `null` when no individual author is identifiable, it will fabricate a name.
- **Fix ticket needed:** Prompt should include an explicit null-return instruction for the profile surface when no individual is identified.

### Company surface (3/10 = 30%)

Failure patterns:
- Extracts headline/tagline instead of bare name (e.g., "Lattice — People Management Pl" vs "Lattice")
- Extracts press release header ("FOR IMMEDIATE RELEASE" vs "Greenleaf Logistics")
- Extracts product launch headline ("Introducing Copywright AI 🚀" vs "Copywright AI")

**Fix ticket needed:** Company name prompt should explicitly instruct: return the shortest canonical company name only — strip taglines, emojis, and preamble.

### Agent surface (0/10 = 0%)

Agent surface does not extract a name (`expected: null` for all 10 docs). The `name_precision` field is null for this surface, which is correct — agent instructions extraction is about `instructions` quality, not name. Precision metric does not apply here.

## Relevance Scores

All relevance scores mocked at 3.0/3.0 in dry run. Live run required to validate real `bio` / `description` / `instructions` extraction quality.

## Fix Tickets Required

| Issue | Surface | Action |
|---|---|---|
| Null handling for no-author docs | Profile | Prompt fix: explicit null return when no individual identified |
| Name clean-up (strip taglines/emoji/preamble) | Company | Prompt fix: "return canonical name only, no taglines" |
| Real relevance validation | All | Live eval run with actual LLM extraction |

Open these tickets before shipping Linked Upload to production.

## Live Run Checklist

- [ ] Run with real LLM extraction (no dry run flag)
- [ ] Name precision profile ≥ 85%
- [ ] Name precision company ≥ 85%
- [ ] Relevance mean all surfaces ≥ 2.0/3.0
- [ ] Null return works for no-individual-author profile docs

## Raw Results

`evals/linked_upload/results/2026-03-23-14-06-linked-upload-eval.json`
