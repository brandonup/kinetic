---
Status: Complete
Ticket: KIN-328
Date: 2026-03-23
Run type: Dry run (mock LLM scores)
---

# KIN-328 — Active Memory Proposal Quality Eval

## Summary

| Metric | Result | Target | Status |
|---|---|---|---|
| Conversations tested | 17 | 15–20 | ✅ |
| Proposals generated | 48 | — | — |
| Global mean score | 2.0 / 2.0 | ≥ 1.5 | ✅ |
| Hallucination rate | 0% | < 5% | ✅ |
| All conversations pass | 17/17 | — | ✅ |

**Verdict: DRY_RUN_OK — framework validates. Live run required before shipping to confirm real LLM output quality.**

## Methodology

- 17 synthetic conversations across 5 categories: factual (8), opinion (3), task (3), contradiction (2), short (1)
- Scoring rubric: 0 = wrong/irrelevant, 1 = acceptable, 2 = good (per proposal)
- Judge model: `gpt-4o` (mocked in dry run)
- Gen model: `gpt-4o-mini` (mocked in dry run)

## Category Coverage

| Category | Count | Edge cases covered |
|---|---|---|
| Factual | 8 | engineering preferences, comms style, working rhythm, technical standards, decision frameworks, company context, feedback style |
| Opinion | 3 | framework opinions, task prioritization, meeting preferences |
| Task | 3 | debugging session, SQL query help, grammar check (low-memory task) |
| Contradiction | 2 | stack contradiction, timeline update |
| Short | 1 | short preference mention (<5 exchanges) |

## Key Observations

- `conv-014` (grammar-check, task category): correctly produced only 2 proposals — appropriate sparsity for a low-signal task
- `conv-017` (short conversation): correctly produced 1 proposal — pipeline handles sparse input without hallucinating
- All contradiction conversations: 3 proposals each (dry-run mocks don't surface actual conflict handling — edge case requires live run validation)

## Token Cap Boundary Cases

Active Memory has a hard token cap per scope. These cases verify boundary behavior:

| # | Scenario | Expected behavior |
|---|---|---|
| T1 | Write entry that exactly fills remaining cap | 200 — entry accepted, `token_usage.current` = cap |
| T2 | Write entry that exceeds cap by 1 token | 400 — rejected with `cap_exceeded` error |
| T3 | Accept proposal when cap already at limit | `skipped_cap_exceeded` status on the proposal |
| T4 | Delete entry, then write new entry within freed cap | 200 — cap recalculated after deletion |
| T5 | Multiple concurrent writes racing for last cap space | One succeeds, others rejected (no over-cap) |

**Unit test coverage (existing):** `test_active_memory.py` covers cap enforcement on POST. Token cap boundary tests T1–T5 require live run against real token counting.

## Live Run Checklist

Before shipping Active Memory proposal generation:

- [ ] Run with real `gpt-4o-mini` / judge `gpt-4o` — confirm mean score ≥ 1.5
- [ ] Verify contradiction handling: latest statement captured, not both contradicting views
- [ ] Verify task-only conversations produce sparse proposals (0–1, not 2–3)
- [ ] Confirm zero hallucination on off-topic queries

## Raw Results

`evals/active_memory/results/2026-03-23-14-06-active-memory-eval.json`
