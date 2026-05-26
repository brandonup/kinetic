---
Date: 2026-05-24
Ticket: KIN-448
Embedding model: gemini-embedding-001
Agent: 9b54b4c3-eec0-44dd-add6-feb368f400e8
Dataset: evals/framework_selection/dataset.jsonl (249 cases)
---

# L7 Framework Selection — Baseline Eval Results

## Metrics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| precision_at_1 | 92.5% | >= 80% | PASS |
| no_match_accuracy | 91.4% | >= 85% | PASS |
| adjacent_fp_rate | 20.0% | <= 30% | PASS |
| false_negative_rate | 3.7% | <= 25% | PASS |
| MRR (informational) | deferred | >= 0.7 | Pipeline returns top-1 only |

## Dataset Breakdown

- **Total:** 249 cases
- **On-topic:** 214
- **Adjacent:** 15
- **Off-topic:** 20

## Failure Analysis

- **Total failures:** 19
- **False positives:** 3 (framework fired when it shouldn't)
- **False negatives:** 8 (no framework when one should fire)
- **Wrong framework:** 8 (matched wrong framework)

### Worst FP Frameworks (adjacent queries)

- 1x — Three-Question Bridge Drill
- 1x — Proxy Signal Reading
- 1x — Integration Complexity vs. Advantage 2x2 Portfolio Strategy

## Boosted Score Distribution

| | Count | Mean | Median | Min | Max |
|---|---|---|---|---|---|
| Correct | 198 | 1.0854 | 1.1000 | 0.8630 | 1.2000 |
| Incorrect | 11 | 0.8926 | 0.8740 | 0.8549 | 0.9514 |
