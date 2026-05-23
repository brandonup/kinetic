# Recency-Aware Retrieval Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use the `executing-plans` skill to implement this plan task-by-task.

**Goal:** Bias KB retrieval toward recent content, and make agents date-aware so they prefer newer sources and flag potentially-outdated information on conflict.

**Architecture:** Approach 2 — a soft recency *demote* in the Python API retrieval scoring (Component C), plus date-aware generation on **both** retrieval surfaces (Component D). Recency *ranking* is API-only for MVP (scope decision: Option B); the MCP/Cowork surface gets date visibility + the contradiction instruction but not the ranking boost.

**Tech Stack:** Python / FastAPI, pytest · Postgres RPC on Supabase · Deno / TypeScript Edge Function.

**Source of truth:** `docs/plans/2026-05-21-recency-aware-retrieval-design.md` (status `Approved`). This plan does not restate the design — every task references it. Read the design doc first.

---

## Prerequisites — do not start Task 1 until these are done

1. **Pre-implementation gate passed** — run the `pre-implementation-gate` skill against the design doc; all 8 gates green.
2. **Gilfoyle Phase 2 tech-prep artifacts exist:**
   - **ADR** — recency scoring model: the `recency_term` decay curve (shape, half-life / zero-crossing age) and the `RECENCY_WEIGHT` default. **This plan references those values; it does not invent them.**
   - **`match_chunks` migration draft** — drop/recreate adding the date columns (Task 2).
   - **`db-schema-spec.md` update** — the `match_chunks` RPC signature.
3. **Corpus state verified** — confirm whether the full ~505-article Nate corpus is already in prod. This determines whether Task 5 (backfill) runs. See design § Sequencing.

## Implementation Order

Tasks 1 and 2 are independent of each other. Tasks 3 and 4 both depend on Task 2 (they need `effective_date` on `RetrievedChunk`). Task 5 is conditional. Task 6 spans all components.

```
Task 1 (A: ingestion)  ─┐
Task 2 (B: RPC+plumbing)─┴─► Task 3 (C: scoring) ─► Task 4 (D: generation) ─► Task 6 (evals)
                              Task 5 (backfill, conditional — after Task 1 deploys)
```

Each task ends with a green test run and a commit. Use `test-driven-development` for every task and `verification-before-completion` before marking any task done.

---

### Task 1 — Component A: capture `document_date` at ingestion (3 paths)

**Skills:** `test-driven-development`, `verification-before-completion`
**Design ref:** § Component A. **Files & line numbers are listed there — use them.**

Three ingestion entry points must populate `knowledge_base_documents.document_date`:
- **API upload** (`documents.py` `upload_document`) — new optional `document_date` Form field, threaded through `run_ingestion` → `_run_pipeline_stages` → the document insert.
- **Nate bulk upload** (`nbj_extractor/bulk_upload_to_kb.py` `convert_article()`) — send `document_date` as a form field; **truncate** the ISO-8601 `date` timestamp to the date portion.
- **Scrape poller** (`poller.py` `_ingest_post`) — map `ScrapedPost.published_at` → `document_date` in the insert dict.

**Steps:**
1. Write failing test: API upload with a `document_date` form field persists it to `documents.document_date`.
2. Write failing test: API upload *without* the field → `document_date` is `NULL`.
3. Implement the API upload path (Form param + thread through the pipeline). Run tests → green.
4. Write failing test: `_ingest_post` maps `published_at` → `document_date`. Implement. Run → green.
5. Update `convert_article()` to send the truncated `document_date`; add/extend its conversion test. Run → green.
6. Write failing test: editing / re-ingesting an existing document **preserves** `document_date` (does not reset it). Implement if needed. Run → green.
7. Run the full ingestion test suite. Commit.

**Done when:** all three ingestion paths populate `document_date`; absent date → `NULL`; document edit preserves the date.

---

### Task 2 — Component B: surface the date via `match_chunks` + Python plumbing

**Skills:** `test-driven-development`, `supabase-postgres-best-practices`, `verification-before-completion`
**Design ref:** § Component B. **Policy:** `database-migrations.md` (esp. §2a — invoke + verify the RPC).

**Files:**
- Apply the `match_chunks` migration draft (Gilfoyle Phase 2): `DROP FUNCTION` all overloads (vector / halfvec / text param variants), recreate adding `document_date` (raw, nullable) **and** `created_at` to `RETURNS TABLE` + SELECT. **Do not pre-`COALESCE`** — Python needs both.
- `retrieval.py` `_normalise_search_row` — surface the new columns.
- `retrieval.py` `RetrievedChunk` dataclass — add `effective_date: Optional[date]`, `date_is_estimated: bool`.
- `retrieval.py` fallback search path (`_vector_search_sync`) — selects no date → `effective_date = None`.

**Steps:**
1. Apply the migration to **dev**. Invoke `match_chunks` directly in psql; confirm the two new columns return. (`database-migrations.md` §2a — KIN-478 shipped a bug because the RPC was created but never called.)
2. Write failing test: `_normalise_search_row` yields `effective_date` and `date_is_estimated` from an RPC row. `effective_date` = `document_date` if present else `created_at`; `date_is_estimated` = `True` when falling back.
3. Implement normalisation: parse the PostgREST date string (`date.fromisoformat`), handle null/absent. **Implausible-date handling:** a future date (> today+1d) or implausibly-old date (`< ~2015`, e.g. `datetime.min`) → discard, fall back to `created_at`, set `date_is_estimated = True`.
4. Write failing test: the fallback search path yields `effective_date = None`. Implement.
5. Run the retrieval test suite. Commit.

**Done when:** `match_chunks` returns `document_date` + `created_at` and is verified live on dev; `RetrievedChunk` carries `effective_date` + `date_is_estimated`; implausible dates fall back; fallback search path → `None`.

---

### Task 3 — Component C: recency scoring (API path only)

**Skills:** `test-driven-development`, `verification-before-completion`
**Design ref:** § Component C — **the score-usage table is the contract for this task.**

**Files:**
- `retrieval.py` — new pure function `recency_term(effective_date, now) -> float` next to `mmr_select`; compute `recency_adjusted_score` on candidates after the RPC returns.
- `retrieval.py` — MMR relevance term + first pick, and token-budget eviction, read `recency_adjusted_score` when `RECENCY_ENABLED`; the **similarity threshold gate stays on raw `similarity_score`**; debug trace logs both.
- `settings` — add `RECENCY_ENABLED` (bool) and `RECENCY_WEIGHT` (float; default from the ADR).

**Steps:**
1. Write failing unit tests for `recency_term`: recent → `+1`, decay mid-point → `~0`, very old → `−1`, `None` → `0` (no effect). Curve per the ADR.
2. Implement `recency_term`. Run → green.
3. Write failing test: `recency_adjusted_score == similarity_score + RECENCY_WEIGHT × recency_term`; `similarity_score` stays immutable.
4. Implement adjusted-score computation. Run → green.
5. Write failing tests for score-field discipline: (a) threshold gate uses **raw** similarity — a recency-penalised but genuinely-relevant chunk still passes 0.3, a recency-boosted weak chunk still fails; (b) MMR selection + token-budget eviction use the adjusted score.
6. Implement the wiring per the design's score-usage table. Run → green.
7. Write failing test: `RECENCY_ENABLED=False` → retrieval output **byte-identical** (chunk IDs, order, scores) to pre-feature behaviour. Implement gating. Run → green.
8. Run the retrieval suite. Commit.

**Done when:** recency scoring gated behind `RECENCY_ENABLED`; score-field discipline matches the design table exactly; off-state is byte-identical.

---

### Task 4 — Component D: date-aware generation (both surfaces)

**Skills:** `test-driven-development`, `genai`, `mcp-development`, `verification-before-completion`
**Design ref:** § Component D.

**API path files:**
- `context_assembler.py` (the per-chunk injection string, ~line 526) — add the date. Label `Published: {date}` when real, `Added: {date}` when `date_is_estimated`. **Do not** touch the chunker's ingestion-time header — it is embedded in the vector.
- RAG prompt — add the recency/contradiction instruction, gated behind `RECENCY_ENABLED`.

**MCP path files:**
- `supabase/functions/kinetic-mcp/tools.ts` — both context formatters (~`:896-898`, ~`:526-534`): append the date to the header line.
- `tools.ts` — add the contradiction-preference instruction string to the MCP KB-tool output preamble; gate via an Edge Function env var (Deno has no access to the Python `settings` flag).

**Steps:**
1. Write failing test: API context block shows `Published:` for a real date and `Added:` for an estimated date. Implement the `context_assembler` change. Run → green.
2. Identify the RAG prompt file/ID. Add the recency instruction gated by `RECENCY_ENABLED`. Write a test that the off-state prompt is byte-identical. Run → green.
3. Add the date to both `tools.ts` formatters; test. Run → green.
4. Add the contradiction instruction string to the MCP KB-tool output; gate via env var; test.
5. Run API + MCP test suites. Commit.

**Done when:** both surfaces display dates with correct Published/Added labelling; the contradiction instruction is present and gated on both surfaces; `RECENCY_ENABLED=False` leaves API generation unchanged.

---

### Task 5 — (Conditional) Nate corpus `document_date` backfill

**Run only if** the Prerequisites check found the full Nate corpus already in prod. Design ref: § Sequencing.

**Steps:**
1. Confirm Task 1 is deployed (so re-upload captures dates inline).
2. Delete the pre-feature Nate documents from the agent KB.
3. Re-run `bulk_upload_to_kb.py --resume`.
4. Spot-check: query several Nate documents — `document_date` must reflect the article publish date, **not** the upload day.

**Done when:** every Nate document carries a real `document_date`; none falls back to `created_at`.

---

### Task 6 — Evals & feature-level regression

**Skills:** `llm-evaluation`, `test-driven-development`
**Design ref:** § Testing.

Extend the KIN-449 KB-retrieval eval set with:
- **Recency cases** — fresh chunk vs. stale near-duplicate → fresh ranks higher.
- **Contradiction cases** — opposing claims, different dates → the answer prefers the recent claim.
- **Over-flagging cases** — an evergreen explainer with an old date → the agent does **not** spuriously flag it as outdated.

Confirm the Task 3 byte-identical `RECENCY_ENABLED=False` regression runs in CI. Fold the eval run into the KIN-471 smoke test.

**Done when:** the three eval case types exist and run; the off-state regression is in CI.

---

## Test Strategy

- **Unit:** `recency_term` curve (pure function — exhaustive boundary tests), `_normalise_search_row` date derivation, implausible-date clamping.
- **Integration:** each ingestion path persists `document_date`; `match_chunks` returns the new columns; the score-field discipline (threshold vs. MMR vs. budget) behaves per the design table.
- **Regression (mandatory):** `RECENCY_ENABLED=False` → retrieval output byte-identical to pre-feature `main`. This is the highest-risk surface — the feature must be a true no-op when off.
- **Eval:** recency / contradiction / over-flagging cases in the KIN-449 set.

## Feature-Level Done-When

- All three ingestion paths capture `document_date`; corpus dates are real publish dates, not upload dates.
- API retrieval demotes stale content via `recency_adjusted_score` with correct score-field discipline.
- Both surfaces show source dates and carry the contradiction instruction.
- `RECENCY_ENABLED` off → byte-identical to today.
- `rag-architecture.md` § Recency Scoring updated to match this design (supersession noted in the design doc).

## Next Step — Handoff

This plan does **not** go straight to a coding session. Per Jared's workflow the path is:

1. **Pre-implementation gate** (`pre-implementation-gate` skill) against the design doc.
2. **Gilfoyle Phase 2 tech prep** — produces the ADR, the `match_chunks` migration draft, and the `db-schema-spec.md` update that Tasks 1–2 depend on.
3. **Ticket creation** — Tasks 1–4 (+ conditional Task 5, + Task 6) become Linear implementation tickets with the done-when criteria above and skill tags.
4. **Implementation** — Dinesh executes the tickets using `executing-plans`.
