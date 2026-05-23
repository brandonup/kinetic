# Recency-aware retrieval eval cases (KIN-483)

Extension of the [KIN-449 KB retrieval eval set](./dataset.jsonl) — adds
recency, contradiction, and over-flagging cases per
`docs/plans/2026-05-21-recency-aware-retrieval-design.md` § Testing.

## Files

| File | Purpose |
|---|---|
| `dataset_recency.jsonl` | The 13 case templates. Each line is one case in extended JSONL format. |
| `populate_recency_dataset.py` | Resolves `*_title_pattern` placeholders to real `document_id`s from a live agent KB. Run after [KIN-489](https://linear.app/brandonup/issue/KIN-489) backfill populates real `document_date`s. |
| `eval_runner.py` | Existing KIN-449 runner. Reads `should_retrieve` / `should_not_retrieve` / `label` and ignores the new fields. Generation-layer assertions (`expected_answer_pattern`, `expected_no_staleness_flag`, `expected_prefers_recent`) require a future runner extension shipped with T6. |

## Field contract (extends KIN-449 format)

Every recency-set line includes the base KIN-449 fields *plus* these:

| Field | Type | Purpose |
|---|---|---|
| `case_type` | `"recency" \| "contradiction" \| "over_flagging" \| "control"` | Drives which assertions apply. |
| `fresh_doc_title_pattern` | `string` | Substring match against `knowledge_base_documents.title`. Resolved → real UUID by `populate_recency_dataset.py`. |
| `stale_doc_title_pattern` | `string` | Same, for the comparison doc. |
| `should_retrieve_titles` | `string[]` | Title slugs (for human reading) — mirror of `should_retrieve` once resolved. |
| `should_not_retrieve_titles` | `string[]` | Same, for `should_not_retrieve`. |
| `expected_answer_pattern` | `string` (regex) | Generation-layer — substring/regex the agent's answer should match. **Contradiction cases only.** |
| `expected_prefers_recent` | `bool` | Generation-layer — assert the answer cites the fresher source when sources disagree. **Contradiction cases only.** |
| `expected_no_staleness_flag` | `bool` | Generation-layer — assert the agent does NOT add a "this source is outdated" preface. **Over-flagging + control cases.** |
| `notes` | `string` | Free-text rationale, helpful for human review. |

The case template values for `should_retrieve` and `should_not_retrieve` are
intentionally `<placeholder>` UUIDs. The existing `eval_runner.py` will treat
those as opaque strings, so running the eval against this file before
populating real IDs reports 0% recall — that is the intended failure signal
("dataset not yet populated"). Run `populate_recency_dataset.py` first.

## Populating real document IDs

Prerequisites:
1. [KIN-481](https://linear.app/brandonup/issue/KIN-481) shipped → Component A captures `document_date` at ingestion. **Done.**
2. [KIN-482](https://linear.app/brandonup/issue/KIN-482) shipped → `match_chunks` surfaces dates. **Done.**
3. [KIN-489](https://linear.app/brandonup/issue/KIN-489) executed → prod Nate corpus re-ingested with real publish dates. **Pending Brandon.**

After KIN-489 lands:

```bash
cd /Users/brandonupchuch/son_of_anton/projects/kinetic/packages/api
.venv/bin/python -m evals.kb_retrieval.populate_recency_dataset \
  --agent-slug nate \
  --input evals/kb_retrieval/dataset_recency.jsonl \
  --output evals/kb_retrieval/dataset_recency.populated.jsonl
```

The script:
1. Connects to Supabase via the same env vars as `eval_runner.py`.
2. Resolves `*_title_pattern` substrings → real `document_id` UUIDs by querying `knowledge_base_documents.title`.
3. For pairs where `fresh` and `stale` patterns differ, picks the **newest** matching doc as fresh and the **oldest** as stale (based on `document_date`).
4. Writes a populated `.jsonl` ready to feed `eval_runner.py`.

## Running the eval

Run **two passes** to validate Component C (recency scoring):

```bash
# Pass 1 — recency on
RECENCY_ENABLED=true RECENCY_WEIGHT=0.15 \
  .venv/bin/python -m evals.kb_retrieval.eval_runner \
  --dataset evals/kb_retrieval/dataset_recency.populated.jsonl \
  --agent-slug nate

# Pass 2 — recency off (byte-identical to pre-feature baseline)
RECENCY_ENABLED=false \
  .venv/bin/python -m evals.kb_retrieval.eval_runner \
  --dataset evals/kb_retrieval/dataset_recency.populated.jsonl \
  --agent-slug nate
```

**Recency cases:** `precision_at_8` and `mrr` should be *higher* in pass 1
than pass 2, indicating recency boost lifts fresh docs above their stale
counterparts.

**Tuning band:** ADR-009 § Risks calls out `0.10–0.25` as the safe
`RECENCY_WEIGHT` window. Sweep this range and pick the value that maximises
recency-case precision without regressing the broader KIN-449 baseline
(false fire rate must stay ≤ 15%).

## Component D (generation-layer) cases

`contradiction` and `over_flagging` cases require the generation pipeline to
run end-to-end (the agent must produce an answer, and the eval reads the
answer text). The current `eval_runner.py` does NOT run generation — it stops
at chunk retrieval. T6 (not yet ticketed) ships a generation-aware runner
that reads `expected_answer_pattern`, `expected_prefers_recent`, and
`expected_no_staleness_flag`. Until then, those fields are inert metadata.

## Why placeholders, not embedded doc IDs?

Real `document_id` values rotate every time the prod Nate corpus is
re-ingested. Hard-coding UUIDs makes the eval set brittle. Title-pattern
resolution is robust: as long as Nate publishes pieces with stable slugs,
the eval rehydrates correctly across re-ingestions.
