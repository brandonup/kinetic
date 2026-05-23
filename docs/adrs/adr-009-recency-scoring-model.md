# ADR-009: Recency Scoring Model for KB Retrieval

**Status:** Approved
**Author:** Gilfoyle
**Date:** 2026-05-21
**Approved by:** Brandon, 2026-05-21
**Project:** Kinetic

---

## Context

Kinetic agent KBs (Layer 9) hold AI-domain commentary — articles and podcast/lecture
transcripts. The field moves fast and this content goes stale fast. Retrieval currently
ranks purely on cosine similarity (`match_chunks` RPC), so a semantically-relevant stale
chunk is retrieved and citable as current truth.

The approved design (`docs/plans/2026-05-21-recency-aware-retrieval-design.md`,
Approach 2, MCP scope Option B) introduces a **soft recency demote** in the Python API
retrieval path (Component C). The decay math is a pure Python function
`recency_term(effective_date, now) -> float` next to `mmr_select` in `retrieval.py`,
applied as:

```
recency_adjusted_score = similarity_score + RECENCY_WEIGHT × recency_term
```

`similarity_score` is raw cosine similarity in `[0, 1]` (in practice ~`0.3–0.85` after
the `SIMILARITY_THRESHOLD=0.3` floor). `recency_term ∈ [−1, +1]`.

This ADR fixes the two values that Task 3's done-when criteria cannot be written
without: **the shape of the `recency_term` decay curve** and **the `RECENCY_WEIGHT`
default**. Both were left "fixed in the ADR (Gilfoyle Phase 2)" by the design doc.

Forces at play:

- **Staleness profile of the corpus.** AI commentary has a short useful half-life — a
  6-month-old "state of agents" take is materially weaker than last month's; a
  2-year-old one is usually wrong on specifics. The curve must demote aggressively in
  the first year, not over a multi-year horizon.
- **Soft demote, not a cliff.** Design § Out of Scope explicitly bans a hard age cutoff
  and topic-aware evergreen classification. The curve must be smooth and bounded so a
  foundational-but-old chunk is demoted, never excluded — exclusion is the threshold
  gate's job, on *raw* similarity only.
- **Tunability.** `RECENCY_WEIGHT` must be `settings` config so the KIN-449 eval
  harness can sweep it without a redeploy. The curve constants live in the pure
  function (changing curve *shape* is a deliberate code change with new unit tests).
- **Bounded blast radius.** `RECENCY_ENABLED=False` must be byte-identical to today.
  At any `RECENCY_WEIGHT`, the adjustment cannot dominate similarity — recency is a
  tiebreaker among comparably-relevant chunks, not a relevance replacement.
- **Estimated dates.** When `document_date` is absent, `effective_date` falls back to
  `created_at` and `date_is_estimated = true`. The scoring function still runs on the
  estimate; the *generation* layer (Component D) is what distinguishes a real publish
  date from an ingestion date. `recency_term` does not branch on `date_is_estimated`.
  A `None` `effective_date` (fallback search path) yields `recency_term = 0`.

## Decision

> We will compute `recency_term` with a **piecewise-linear age decay** — `+1` at age 0,
> linear to `0` at a **9-month zero-crossing**, linear to `−1` at **24 months**, and
> clamped at `−1` beyond — and set **`RECENCY_WEIGHT = 0.15`** as the tunable default.

### `recency_term(effective_date, now) -> float`

`age_days = (now.date() - effective_date).days`, after the both-tail clamp
(Component C / Task 2 — future or implausibly-old dates are discarded upstream and
arrive here as a `created_at` fallback or `None`).

```
recency_term(age_days):
    if effective_date is None:      return  0.0      # fallback search path — no signal
    age = max(0, age_days)                            # future-date guard (defensive)
    ZERO_CROSSING_DAYS = 274                           # ~9 months
    FLOOR_DAYS         = 730                           # ~24 months
    if age <= ZERO_CROSSING_DAYS:
        return 1.0 - (age / ZERO_CROSSING_DAYS)        # +1.0  →  0.0
    if age <= FLOOR_DAYS:
        return -1.0 * (age - ZERO_CROSSING_DAYS) / (FLOOR_DAYS - ZERO_CROSSING_DAYS)
                                                       #  0.0  → −1.0
    return -1.0                                        # clamped
```

Reference values (`RECENCY_WEIGHT = 0.15`):

| Age | `recency_term` | Score adjustment |
|---|---|---|
| today | `+1.00` | `+0.150` |
| ~4.5 months (137 d) | `+0.50` | `+0.075` |
| **9 months (274 d) — zero crossing** | `0.00` | `0.000` |
| ~16.5 months (502 d) | `−0.50` | `−0.075` |
| 24 months (730 d) | `−1.00` | `−0.150` |
| > 24 months | `−1.00` (clamped) | `−0.150` |

### `RECENCY_WEIGHT`

`RECENCY_WEIGHT = 0.15`, declared in `settings` as a tunable float.

Rationale for the magnitude: max adjustment is `±0.15` on a similarity range whose
*effective* spread (post-0.3 floor) is roughly `0.3–0.85`. `±0.15` is large enough to
reorder chunks whose raw similarity is within ~`0.15` of each other — the genuine
"comparably relevant" tie the feature targets — and too small to lift a `0.45` chunk
above a `0.75` chunk. It cannot invert a real relevance gap. This is the explicit fix
for the rejected `rag-architecture.md` `+0.5/+0.2/0/−0.3` additive table, where a
`+0.5` boost *does* invert ranking on a 0–1 score.

Starting point, not final: `0.15` is the default; the KIN-449 eval set (recency +
contradiction + over-flagging cases) is the tuning instrument. Expected tuning band
`0.10–0.25`. Re-tuning is a config change, not a code change or migration.

### Supersession

This ADR **supersedes** `docs/features/rag-architecture.md` § Recency Scoring (the
`< 30d → +0.5 / 30d–6mo → +0.2 / 6mo–2yr → 0 / > 2yr → −0.3` modifier table and the
`RECENCY_WEIGHT` default of `1.0`). That section is updated to a pointer to this ADR as
part of Phase 2 (`rag-architecture.md` doc update). The `RECENCY_ENABLED` /
`RECENCY_WEIGHT` flag *names* are retained; only their semantics and default change.

## Alternatives Considered

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **Piecewise-linear, 9mo zero-cross, 24mo floor (chosen)** | Transparent — every (age → term) point is hand-verifiable in a unit test; exact zero-crossing and floor are explicit, not emergent; fast; matches AI-commentary staleness profile | Two hard knees (slope changes) rather than a single smooth curve; constants are judgment calls | N/A — chosen |
| Exponential half-life decay (`term = 2·exp(−age/τ) − 1`) | Single smooth curve, one constant (`τ`) | Never actually reaches `−1` (asymptotic) so "fully stale" is fuzzy; the zero-crossing is a derived value (`τ·ln2`) not a stated one — done-when criteria are harder to write; boundary unit tests assert against transcendental values | Rejected — the design wants an explicit zero-crossing age; emergent constants make T3 done-when fragile |
| Additive step table (`rag-architecture.md` original) | Trivially simple | Discontinuous — a 1-day age difference flips the modifier by `0.2–0.3`; raw magnitudes (`+0.5`) invert relevance on a 0–1 score (Gilfoyle design review B-finding) | Rejected — this is the model being superseded |
| Recency as an MMR `λ` term (fold age into diversity math) | No separate score field | Conflates recency with diversity — two orthogonal concerns; breaks the design's score-field discipline table; un-tunable independently | Rejected — design mandates a separate `recency_adjusted_score` |
| SQL-side decay (compute `recency_term` in `match_chunks`) | One fewer Python step | Tuning `RECENCY_WEIGHT`/curve becomes a migration; the RPC is shared with the MCP server, so SQL-side scoring silently changes MCP behavior (violates Option B) | Rejected — design § Component C mandates Python; see ADR-002 boundary |

## Consequences

**Positive:**

- T2/T3 done-when criteria become writable — curve and weight are now concrete values.
- Every (age → term) pair is a hand-checkable unit-test assertion; the curve has no
  emergent or transcendental constants.
- Tuning is a `settings` change. Curve *shape* changes are isolated to one pure
  function with its own test file.
- Bounded `±0.15` adjustment cannot invert a genuine relevance gap — the failure mode
  of the superseded additive table is structurally eliminated.

**Negative:**

- The zero-crossing (9mo) and floor (24mo) are product judgment encoded as engineering
  constants. If the corpus staleness profile differs from the assumption, the curve —
  not just the weight — needs revisiting (a code change).
- Two slope discontinuities mean the curve is C0 but not C1. Acceptable: there is no
  consumer that needs a smooth derivative.
- A chunk with no real `document_date` is scored on its `created_at` estimate, which
  for a same-day bulk upload reads as "maximally recent." This is mitigated by the
  Component A date-capture across all three ingestion paths and the conditional Nate
  backfill (Task 5) — not by this ADR. The scoring function itself cannot detect a bad
  estimate.

**Neutral:**

- `recency_term` returns `0.0` for `effective_date = None`, making the fallback search
  path a no-op for recency rather than an error path.
- MCP/Cowork retrieval is unaffected (Option B — recency *ranking* is API-only). The
  RPC returns raw dates; no scoring runs in SQL or in `tools.ts`.

## Risks

- **Curve constants are wrong for the real corpus.** *Mitigation:* KIN-449 eval cases
  (recency / contradiction / over-flagging) are run before launch; the zero-crossing
  is reviewable against eval output. If demotion is too aggressive on evergreen
  content, the over-flagging eval case fails loudly.
- **`RECENCY_WEIGHT` set too high in tuning inverts relevance.** *Mitigation:* document
  the `0.10–0.25` band; the byte-identical `RECENCY_ENABLED=False` regression and the
  recency eval cases bracket the safe range. `similarity_score` stays immutable so a
  bad weight is always reversible without data loss.
- **`created_at` fallback misreads bulk-uploaded old content as fresh.** *Mitigation:*
  out of scope for this ADR — owned by Component A (3-path date capture) and Task 5
  (Nate backfill). Flagged here only as a known interaction.

## Review Trigger

Revisit if any of:

- KIN-449 eval tuning cannot find a `RECENCY_WEIGHT` in `0.10–0.25` that satisfies the
  recency and over-flagging cases simultaneously — implies the curve shape, not the
  weight, is wrong.
- The KB corpus broadens beyond fast-moving AI commentary (e.g. legal, historical, or
  reference content) where a 9-month zero-crossing is too aggressive — this is the
  trigger for the deferred topic-aware evergreen classification.
- The MCP-unification follow-up lands and recency ranking must run on the Cowork
  surface — confirm the Python `recency_term` is the single source and is not re-forked.

## Related Decisions

- **ADR-002** (RAG retrieval pipeline) — establishes the vector-search → MMR →
  threshold → budget pipeline this scoring step inserts into.
- **Supersedes** `docs/features/rag-architecture.md` § Recency Scoring.
- Implements Component C of `docs/plans/2026-05-21-recency-aware-retrieval-design.md`.
