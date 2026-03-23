# Framework Selection Eval — Confidence Threshold Tuning

**Ticket:** KIN-260
**Status:** Harness ready. Runnable after Sprint 4 KIN-290 ships the selection pipeline.

---

## Purpose

Finds the cosine similarity threshold at which the framework selection pipeline should suppress injection. Too low = wrong frameworks fire (actively harmful). Too high = frameworks rarely fire (feature feels absent).

The threshold is an asymmetric risk: a false positive (wrong framework injected) directly undermines user trust, whereas a false negative (no injection when a match exists) just means the agent responds without a framework lens. Default stance: err toward precision over recall.

---

## Dataset

**40 labeled cases** across 4 categories:

| Category | Count | What it tests |
|---|---|---|
| `clear_match` | 14 | One framework clearly dominant |
| `ambiguous` | 10 | 2+ frameworks compete; any expected id is acceptable |
| `no_match` | 10 | Pipeline must return None |
| `multi_turn` | 6 | Short follow-ups; tests false-positive rate on low-signal queries |

**Seed frameworks:** 8 representative business frameworks covering operations, leadership, product, talent, finance, and strategy. Defined in `cases.py`.

---

## Setup

```bash
# 1. Start the API server
cd packages/api && uvicorn main:app --reload

# 2. Export credentials
export KINETIC_API_URL=http://localhost:8000
export KINETIC_JWT=<your user jwt>

# 3. Run (creates and seeds eval agent automatically)
python -m evals.framework_selection.eval --seed

# Or run against an existing agent
python -m evals.framework_selection.eval --agent-id <uuid>

# Single threshold (for debugging)
python -m evals.framework_selection.eval --seed --threshold 0.65
```

---

## Output

```
Threshold    Precision    Recall      FPR         F1       TP/TN/FP/FN
----------------------------------------------------------------------
     0.50        0.712     0.857    0.187      0.777      12/15/5/2
     0.55        0.789     0.786    0.125      0.787      11/16/3/3  ← example
     0.60        0.867     0.714    0.063      0.783      10/17/1/4
     0.65        0.900     0.643    0.063      0.750       9/17/1/5  ← example recommended
     0.70        1.000     0.500    0.000      0.667       7/18/0/7
     ...

RECOMMENDED THRESHOLD: 0.65
  Precision=0.900  Recall=0.643  FPR=0.063  F1=0.750
```

Results are saved to `evals/framework_selection/results/YYYY-MM-DD-HH-MM.json`.

---

## Recommendation criteria

1. **False positive rate < 0.10** (hard gate — wrong injection breaks trust)
2. **Precision ≥ 0.85** (when it fires, it should be right)
3. **Highest F1** among thresholds meeting 1 + 2

If no threshold meets all criteria, the one with the lowest FPR is returned as a conservative default.

---

## After running

1. Record the recommended threshold in `docs/adr-005-agents-framework-selection.md`.
2. Set `FRAMEWORK_SELECTION_THRESHOLD` in the API config (or the admin LLM Models defaults table).
3. Re-run this eval after any change to the embedding model or reranker prompt.

---

## Adding cases

Add to `EVAL_CASES` in `cases.py`. Follow the existing format:

```python
EvalCase(
    query="...",
    category="clear_match",            # or ambiguous / no_match / multi_turn
    expected_framework_ids=["fw-id"],  # [] for no_match
    notes="Why this case matters.",
)
```

New cases must reference a `framework_id` present in `SEED_FRAMEWORKS`, or the import-time assertion will fail.
