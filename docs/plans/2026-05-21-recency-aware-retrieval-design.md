# Recency-Aware Retrieval — Design

**Status:** Approved
**Date:** 2026-05-21
**Author:** Jared (product)
**Reviewed by:** Gilfoyle — design review 2026-05-21 (verdict `NEEDS REWORK`; full punch list applied below). MCP-scope recommendation (Option B) adopted.

---

## Context

Kinetic agent KBs (Layer 9) hold AI-domain commentary — articles and podcast/lecture transcripts. The AI field moves fast and this content goes stale fast: a 2024 take on "agents" is materially different from a 2026 take. Current retrieval ranks purely on cosine similarity (`match_chunks` RPC) with **zero recency logic**, so a stale chunk that is semantically relevant is retrieved and can be cited by the agent as current truth.

## Problem

Two distinct failures, conflated in the original ask:

1. **No recency prioritization** — fresh and stale content compete on semantic similarity alone.
2. **No contradiction safety** — when a stale chunk and a newer chunk make opposing claims, nothing signals the agent to prefer the newer one or to flag potentially-outdated information.

## Goal

Bias retrieval toward recent content, and — more importantly — ensure the agent can *see* publication dates and resolve conflicts toward newer sources. Scoped for the **MVP launch**.

---

## Approach

**Approach 2 — recency scoring + date-aware generation.** Chosen over two alternatives:

| Approach | Why not |
|---|---|
| 1. Recency scoring only | Demotes stale content but never resolves contradiction — a relevant stale chunk is still retrieved and citable. |
| 3. Active LLM contradiction-detection pass | Extra LLM call per query, latency + cost regression on a zero-LLM-call retrieval path, error-prone. Over-scoped for MVP. |

Approach 2 splits the work by mechanism:

- **Recency scoring** (Component C) — a *soft demote*. No hard age cutoff, no topic classification. Never buries evergreen content (e.g. a foundational paper). This addresses "prioritize recency."
- **Date-aware generation** (Component D) — the actual contradiction-safety mechanism. The LLM sees each source's date and is instructed to prefer recent sources on conflict. Retrieval ranking *cannot* resolve contradictions; the generation layer can.

## Scope Decision — MCP/Cowork coverage (Option B)

Kinetic has **two retrieval surfaces**. The Python API path (`retrieval.py`) and the MCP/Cowork path are functionally separate: the MCP Edge Function (`supabase/functions/kinetic-mcp/tools.ts:503-508`, `:864-869`) calls `match_chunks` directly, applies only a similarity threshold + top-8 (`tools.ts:515-517`) — no MMR, no token budget — and builds its own context block (`tools.ts:896-901`).

**Decision: Option B — recency *ranking* is API-only for MVP; recency *safety* covers both surfaces.**

The feature decomposes into a safety layer and an optimization layer, and they are scoped differently:

| Layer | Mechanism | API path | MCP/Cowork path |
|---|---|---|---|
| `effective_date` on RPC (Component B) | one column added to `match_chunks` | ✅ | ✅ — free; consumers read columns by name, nothing breaks |
| **Safety** — date-aware generation (Component D) | date label in context + contradiction instruction | ✅ | ✅ — ~2 lines of TS + a static instruction string, no shared logic, no drift |
| **Optimization** — recency ranking boost (Component C) | decay-weighted score adjustment | ✅ | ❌ — raw cosine for MVP |

Rationale: the safety mechanism is Component D, and it is cheap and drift-free on both surfaces. The recency *ranking* boost (Component C) is the optimization, and it is the only part requiring the decay function — porting that to TypeScript/Deno would fork a tunable pure function across two homes that silently diverge the first time `RECENCY_WEIGHT` is tuned. The MCP path also has no MMR/token-budget, so a partial port produces inconsistent ranking between surfaces. Recency *ranking* reaches Cowork later via the unification ticket (see Follow-ups).

---

## Component A — Capture publication date at ingestion

The pipeline must populate `knowledge_base_documents.document_date` (DATE column exists, currently unused). **Three** ingestion entry points, each needs wiring:

1. **API upload** — `documents.py:71` `upload_document`: add an optional `document_date` Form field. Thread it through `run_ingestion` (`pipeline.py:289`) → `_run_pipeline_stages` (`pipeline.py:143`) → the document insert.
2. **Nate bulk upload** — `nbj_extractor/bulk_upload_to_kb.py`: today `convert_article()` flattens the article JSON `date` into a `Date:` text line in the body (useless for scoring). Change it to send `document_date` as a form field. The JSON `date` is a full ISO-8601 timestamp (`"2026-01-31T03:58:51.677Z"`) — **truncate to the date portion** (`"2026-01-31"`) before it reaches a `DATE` column.
3. **Scrape poller** — `poller.py:_ingest_post()` (lines 191-219): `ScrapedPost.published_at` (`base.py:31`) already exists. Map it → `document_date` in the insert dict at `poller.py:210-217`. This is the highest-value recency signal for the auto-updating corpus.

**Fallback:** null `document_date` → `COALESCE` to `created_at` (ingestion timestamp).

**Document edits:** confirm during implementation that editing/re-ingesting a document **preserves** `document_date` rather than resetting it.

## Component B — Surface the date to retrieval

The `match_chunks` RPC already JOINs `knowledge_base_chunks → knowledge_base_documents` (`20260521000001_fix_match_chunks_uuid_cast.sql:54`). The change:

- Add **two** columns to the RPC's `RETURNS TABLE` + SELECT: `document_date` (raw, nullable) and `created_at`. **Do not pre-`COALESCE`** — Python needs to know whether the date is a real publish date or an estimate (see Component D).
- Signature change → `CREATE OR REPLACE` is insufficient. The migration must **`DROP FUNCTION`** all historical overloads (vector / halfvec / text param variants, as `20260518000001` did) then recreate.
- Per `policies/database-migrations.md` §2a: the new RPC must be **invoked and verified** before shipping (KIN-478 shipped a `uuid=text` bug because the RPC was created but never called).
- **The recreated function must preserve every prior fix.** Canonical current signature is the 9-column form in `db-schema-spec.md` lines 798-808 (`id, document_id, document_title, document_type, text, chunk_index, section_path, page_range, similarity`) → 11 columns after the two additions. Recreating the function must NOT regress: the KIN-476 `text` param + internal `halfvec` cast, the KIN-478 `$2::uuid` scope cast, or any existing `deleted_at IS NULL` soft-delete filter on the document JOIN.
- Python plumbing:
  - New keys in `_normalise_search_row` output (`retrieval.py:289-321`).
  - New fields on the `RetrievedChunk` dataclass (`retrieval.py:58-76`): `effective_date: Optional[date]`, `date_is_estimated: bool`.
  - The **fallback search path** (`_vector_search_sync:254-265`) selects no document date and computes similarity client-side → `effective_date = None`; recency code treats `None` as "skip recency for this chunk."
- PostgREST returns a SQL `date` as a JSON string → parse with `date.fromisoformat`; handle null/absent.

## Component C — Recency scoring (Python, API path only)

The decay math is a **pure, unit-testable Python function** next to `mmr_select` in `retrieval.py` — **not** in the RPC (the value is tunable config; the eval harness must sweep it without redeploying SQL; the RPC is shared with the MCP server).

- `similarity_score` stays **immutable** (raw cosine). Add a separate `recency_adjusted_score`.
- `recency_adjusted_score = similarity_score + RECENCY_WEIGHT × recency_term`, where `recency_term ∈ [−1, +1]` from a smooth age decay. `RECENCY_WEIGHT` lives in `settings` (start ~0.15, tuned against the eval set). Exact decay curve + weight are fixed in the ADR (Gilfoyle Phase 2).
- **Score usage — which field, where:**

  | Pipeline stage | Score used | Reason |
  |---|---|---|
  | Similarity threshold gate (`retrieval.py:501`, default 0.3) | **raw `similarity_score`** | Quality floor — recency must not push a relevant chunk out or sneak a weak one in. |
  | MMR relevance term + first pick (`retrieval.py:157,165`) | `recency_adjusted_score` when `RECENCY_ENABLED` | Recency reorders selection. |
  | Token-budget eviction (`retrieval.py:329-370`) | `recency_adjusted_score` when `RECENCY_ENABLED` | Where a stale chunk is actually dropped — but only under budget pressure (correct soft-demote). |
  | MMR diversity/redundancy term (`retrieval.py:167`) | unchanged (chunk-to-chunk cosine) | Recency is irrelevant to diversity. |
  | Debug trace (`retrieval.py:477,494`) | logs raw `similarity_score`; adjusted score logged separately | Trace interpretability. |

- **Both-tail date clamp:** future dates (> today + 1d) **and** implausibly-old dates (`datetime.min`, before ~2015 — `substack.py:_parse_date` returns `datetime.min` on parse failure) → treat as null → `created_at` fallback, **never** as "maximum staleness."
- Gated behind `RECENCY_ENABLED`.

## Component D — Date-aware generation (both surfaces)

The contradiction-safety mechanism.

**API path:**
1. **Context block** — modify the per-chunk injection string at `context_assembler.py:526` (`[Source: {title}]` → include the date). **Do not** touch the chunker's ingestion-time header (`chunker.py:145-153`) — that string is embedded in the chunk vector; changing it forces a full re-embed of every KB.
2. **RAG-prompt instruction** — add a recency instruction to the RAG prompt (exact prompt file/ID identified in the implementation plan), **gated behind `RECENCY_ENABLED`** so the off-state stays byte-identical.

**MCP/Cowork path:**
3. **Context block** — append the date to the MCP context header (`tools.ts:896-898` and the `:526-534` formatter). ~2 lines, no shared logic.
4. **Contradiction instruction** — add the same static instruction string to the MCP KB-tool output preamble (the agent consuming it is Cowork's Claude; the instruction must ride along in the returned payload, not a Kinetic-side system prompt). Gate via an Edge Function env var (the Deno runtime has no access to the Python `settings` flag).

**Date display — true date vs. estimate:** when the date is a real `document_date`, label it `Published: {date}`. When it is a `created_at` fallback (`date_is_estimated = true`), label it `Added: {date}` or omit it — never present an ingestion date to the LLM as if it were a publication date.

**Instruction content (MVP):** prefer the more recent source when sources conflict; briefly note when relied-on information may be outdated given its date. (The "note outdated info" behavior is kept — Brandon's explicit ask — and covered by an over-flagging eval case rather than cut.)

---

## Edge Cases & Error Handling

| Case | Behavior |
|---|---|
| `RECENCY_ENABLED=False` | Byte-identical to pre-feature behavior — scoring, prompt, and headers all gated. |
| No `document_date` anywhere | `created_at` fallback; `date_is_estimated = true`. |
| All retrieved candidates old | No hard filter — return best available; the agent flags potential staleness via the instruction. |
| Future / implausibly-old dates | Both-tail clamp → null → `created_at` fallback. |
| `effective_date` null on the fallback search path | Recency skipped for that chunk. |
| 0 retrieved candidates | Recency scoring and MMR handle an empty candidate list without error. |
| Malformed / missing date at ingestion | Best-effort — a bad date never fails the ingestion pipeline; stored as `NULL`. |
| Invalid user-supplied `document_date` on upload | Rejected with a 4xx or coerced to `NULL` — never a 500. |
| `match_chunks` recreated | Recreated function preserves existing `deleted_at IS NULL` soft-delete filtering — no stale-document regression. |
| Date arithmetic timezone | `created_at::date` cast and age computation use a consistent timezone (UTC). |

## Sequencing

**Component A must land before the full Nate corpus is uploaded.** The full ~505-article upload (KIN-475 script) is gated behind the KIN-471 smoke test and has likely not run yet. If Component A ships first, dates are captured inline at upload — **no backfill needed.**

If the full corpus is **already** in prod (verify during implementation planning), a backfill is **mandatory** — a bulk upload stamps every article with the same upload-day `created_at`, which the `created_at` fallback would read as "maximally recent," the exact opposite of correct. Backfill mechanism: re-run `bulk_upload_to_kb.py --resume` after Component A lands and after deleting the pre-feature Nate documents.

## Testing

- Extend the KIN-449 KB-retrieval eval set with:
  - **Recency cases** — fresh chunk vs. stale near-duplicate → fresh ranks higher.
  - **Contradiction cases** — two chunks, opposing claims, different dates → the answer prefers the recent claim.
  - **Over-flagging case** — an evergreen explainer with an old date → the agent does **not** spuriously flag it as outdated. (Covers the false-positive risk of the "note outdated info" behavior.)
- **Mandatory regression:** with `RECENCY_ENABLED=False`, retrieval output is byte-identical (same chunk IDs, order, scores) vs. pre-feature `main`.
- Folds into the KIN-471 smoke test.

## Doc Reconciliation

This design **supersedes** `docs/features/rag-architecture.md` § Recency Scoring (~lines 190-203), including the additive modifier table (`+0.5 / +0.2 / 0 / −0.3`) and the `RECENCY_WEIGHT` default of `1.0`. Those raw additive modifiers are rejected: on a 0–1 cosine score a `+0.5` boost inverts relevance ranking.

**Owner of the `rag-architecture.md` update:** Gilfoyle Phase 2 tech prep, alongside the ADR and the `db-schema-spec.md` `match_chunks`-signature update. All three doc updates ship together so the repo never holds two conflicting recency specs.

## Out of Scope (MVP cuts)

No hard age cutoff · no topic-aware evergreen/time-sensitive classification · no active LLM contradiction-detection pass · no new column on `knowledge_base_chunks` (the `match_chunks` JOIN is sufficient) · recency *ranking* on the MCP path.

## Follow-ups

- **Unify MCP retrieval through the Python API** (`architecture` label, post-launch). The MCP Edge Function calling `match_chunks` directly is the root cause of the dual-surface gap and has already caused drift (MCP lacks MMR + token budget). Unification is the permanent fix and is where recency *ranking* reaches Cowork — but it adds a network hop + couples MCP availability to Railway uptime, so it is a deliberate post-MVP ADR decision, not a recency-feature ticket.

## Ticket Shape (provisional)

Pending the pre-implementation gate + Gilfoyle Phase 2 tech prep:

| Ticket | Scope | Est. |
|---|---|---|
| T1 | Component A — date capture across 3 ingestion paths | ~2 |
| T2 | Component B — `match_chunks` RPC change + Python plumbing | ~1–2 |
| T3 | Component C — recency scoring function + pipeline integration (API) | ~2 |
| T4 | Component D — date-aware generation, both surfaces | ~1–2 |
| (conditional) | Nate corpus `document_date` backfill — only if full corpus already in prod | ~1 |
| Follow-up | Unify MCP retrieval through Python API — post-launch, separate | — |

## Decision Log

| Date | Decision |
|---|---|
| 2026-05-21 | Recency scoped into the MVP launch (Brandon). |
| 2026-05-21 | Soft demote only — no hard age cutoff, no topic classification (Jared; protects evergreen content). |
| 2026-05-21 | Approach 2 (recency scoring + date-aware generation) over Approaches 1 and 3 (Jared). |
| 2026-05-21 | Gilfoyle design review → `NEEDS REWORK`; 13-item punch list applied (3-path ingestion, RPC drop/recreate, score-field discipline, `context_assembler` integration point, both-tail clamp, supersede `rag-architecture.md`, mandatory off-state regression). |
| 2026-05-21 | MCP/Cowork scope — **Option B**: recency *ranking* API-only; date-aware generation (safety) on both surfaces. Jared + Gilfoyle converged; Brandon approved. |
| 2026-05-21 | Pre-implementation gate run — 8 gates pass with findings folded into this doc (edge cases, migration-preservation, doc-update ownership). Ticket creation blocked on Gilfoyle Phase 2 (ADR + migration draft + `db-schema-spec.md` update); T2/T3 done-when cannot be completed until the ADR fixes the decay curve + `RECENCY_WEIGHT`. |
