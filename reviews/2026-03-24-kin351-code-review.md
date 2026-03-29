# Code Review: KIN-351 — Add user-language trigger phrases to 184 curated frameworks

**Reviewer:** Gilfoyle
**Date:** 2026-03-24
**Verdict:** Architecture approved

---

## Summary

Big Head added 5 new user-language trigger phrases to each of 184 curated frameworks (920 new triggers total), bringing every framework to 10 triggers. The enrichment targets the root cause identified in Monica's framework review: existing triggers use consultant/author vocabulary while users type founder/consultant language.

## Structural Validation

| Check | Result |
|---|---|
| Framework count | 184 (matches curated baseline) |
| Triggers per framework | 10/10 for all 184 |
| Required fields present | All (`name`, `type`, `description`, `when_to_apply`, `id`, `category`) |
| Duplicate IDs | None |
| JSON validity | Valid |
| Exact duplicate triggers | None across 920 new phrases |
| Apply script | Correct — simple `cp` to `frameworks_curated.json` |

## Trigger Quality Assessment

### User-Language Quality: Good

Sampled all 8 org-design frameworks, all 14 strategic-planning frameworks, and first 8 ai-adoption frameworks (30 of 184 = 16% sample across all priority clusters).

New triggers consistently use ICP vocabulary:
- Talent/org-design: "how do we structure small teams," "should we hire five more engineers or invest in AI dev tooling," "what's the right team structure for an AI-native org"
- Strategy: "I need to present a coherent AI strategy to the board," "how do we narrow down to the two or three bets that actually matter"
- Build-vs-buy: "We shipped fast and the codebase is messy — does that actually matter now that we have AI coding tools?"
- Adoption/culture: "I'm using Cursor to build my startup and my codebase is getting messy," "We built a fully autonomous agent workflow and adoption is way lower than we expected"

These read like things a tech founder or AI consultant would actually type. The priority clusters identified in the ticket (talent, strategy, build-vs-buy, adoption) all received appropriate vocabulary.

### Consultant-Speak Leakage: Minimal

Automated scan for consultant terms (`paradigm`, `ontology`, `taxonomy`, `heuristic`, `meta-cognitive`, etc.) flagged 10 of 920 new triggers. 8 of 10 are uses of "moat" — a term that straddles consultant and founder vocabulary (founders do say "moat" when talking to investors). 1 use of "taxonomy" in a context where the user is asking for one. Acceptable.

### Collision Risk: Low

Zero pairs of same-category frameworks had >60% keyword overlap in their new triggers. Zero exact duplicate triggers across all 920 new phrases. The enrichment pass successfully differentiated between similar frameworks.

## Issues Found

### I1 — Paraphrase Inflation (Important)

193 of 920 new triggers (21%) are paraphrases of existing ORIG triggers (>75% keyword overlap with an ORIG trigger on the same framework). 30 frameworks have 3+ paraphrased new triggers. 7 frameworks have ALL 5 new triggers as paraphrases:

- `strategic-altitude-shifting` (5/5)
- `colleague-shaped-vs-tool-shaped-ai-selection-framework` (5/5)
- `code-cost-vs-attention-cost-distinction` (5/5)
- `proactively-reliable-ai-the-two-step-enterprise-strategy` (5/5)
- `two-ai-economies-framework` (5/5)
- `the-factory-curve` (5/5)
- `four-lane-supply-strategy` (5/5)

Paraphrased triggers embed to nearly identical vectors as the originals. They add near-zero retrieval value — the framework already matches those queries. The whole point of this enrichment was to expand the vocabulary surface, not restate existing phrases.

**Severity:** Important. These 7 frameworks got no effective enrichment. The remaining 177 frameworks averaged ~4 genuinely new triggers each, which is acceptable. Not blocking because the net enrichment is still large (727 new-vocabulary triggers), but the 7 zero-value frameworks should be re-enriched in a follow-up.

### I2 — Casing Inconsistency (Important)

All 920 ORIG triggers start with uppercase (sentence case). 187 of 920 NEW triggers (20%) start lowercase. Examples:
- "should we spend our AI budget on visibility tools..."
- "our AI investment is all dashboards and reporting..."
- "how do we structure small teams to use AI..."

Embedding models treat casing as signal. Inconsistent casing within the same `when_to_apply` array means the trigger vectors are not normalized the same way, which introduces noise in similarity scoring. At 184 frameworks with ~1,840 total triggers embedded as separate vectors, this is a measurable signal quality issue.

**Fix:** Capitalize the first character of all 187 lowercase triggers. One-line script: `t[0].upper() + t[1:]` for each.

**Severity:** Important. Easy fix, real impact on embedding quality.

## Retrieval Verification

Big Head's comment reports 4/7 representative queries now hit the expected framework in top 5 (keyword-overlap proxy), up from 1/7 pre-enrichment. This is a proxy test only — full embedding-based verification is needed post-merge. The improvement trajectory is correct and meets the spirit of the acceptance criteria, though not the letter (AC says "run the 7 representative queries again" which requires embedding).

## Verdict

**Architecture approved.** 0 Critical, 2 Important.

The enrichment delivers substantial value: 727 genuinely new user-language triggers across 184 frameworks, with good ICP vocabulary coverage and no collision risk. The two Important items (7 fully-paraphrased frameworks, 187 lowercase triggers) should be fixed but do not block merge.

**Recommended follow-up:**
1. Fix I2 (casing) before applying — trivial script.
2. File a ticket for I1 (re-enrich the 7 paraphrased frameworks) as a low-priority follow-up.
3. Run full embedding-based retrieval test on the 7 representative queries post-merge.
