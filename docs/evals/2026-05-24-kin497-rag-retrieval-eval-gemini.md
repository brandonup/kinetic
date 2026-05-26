---
Date: 2026-05-24
Ticket: KIN-449
Embedding model: gemini-embedding-001
Scope: agent_kb (9b54b4c3-eec0-44dd-add6-feb368f400e8)
Dataset: evals/kb_retrieval/dataset.jsonl (47 cases)
---

# L8/L9 KB Retrieval — Baseline Eval Results

## Metrics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| precision_at_8 | 76.0% | >= 70% | PASS |
| recall_at_20 | 88.0% | >= 80% | PASS |
| mrr | 72.3% | >= 60% | PASS |
| false_injection_rate | 11.6% | <= 15% | PASS |
| false_fire_rate (info) | 40.9% | — | — |

## Dataset Breakdown

- **Total:** 47 cases
- **On-topic:** 25
- **Adjacent:** 12
- **Off-topic:** 10

## Failure Analysis

- **Low precision (<50%):** 6
- **Low recall (<50%):** 3
- **Zero recall:** 3
- **False fires:** 9

### Most Frequently Falsely Injected Documents

- 7x — `88ef174b-1cbe-49ec-9d1f-ad8ce42bf218`
- 4x — `2f9bcddd-3ab5-4e94-b1da-8fbc830e05bd`
- 4x — `12b09135-e391-4122-acb3-9c1d07038107`
- 4x — `92404c5c-46b0-4086-95d8-f507f59ac445`
- 3x — `0fb2e166-123a-4e85-b017-40521841606c`
- 3x — `87d67433-b772-4252-8567-f46c6ff2dee0`
- 3x — `e415e760-d4e0-4230-91f5-83bb74597fd4`
- 3x — `0a9f341f-7d87-4a7e-9874-5b5ffced0a4c`
- 3x — `883d0f4b-cac4-4e71-b89d-dd5a8276a91e`
- 2x — `c1881cc2-6525-4b5e-9340-289ec0b6f012`
