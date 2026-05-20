# Framework Eval Plan

**Status:** Draft
**Author:** Monica
**Date:** 2026-03-24
**Scope:** 184 curated ICP-relevant frameworks in `nbj_extractor/frameworks_curated.json`

---

## Purpose

The framework feature's job is to make the agent reason better than a vanilla LLM — applying Nate's specific named lenses, mental models, and diagnostics to the user's situation so the advice is structurally better, not just generic — while not negatively affecting queries that don't need high reasoning.

This plan defines how to evaluate whether the frameworks achieve that goal.

---

## Library Profile

| Metric | Value |
|---|---|
| Total curated frameworks | 184 |
| With procedural steps | 72 (39%) |
| Without steps (conceptual only) | 112 (61%) |

**Type distribution:**

| Type | Count | Procedural? |
|---|---|---|
| taxonomy | 44 | 25% have steps |
| reframe | 37 | 8% have steps |
| diagnostic | 30 | 83% have steps |
| procedure | 26 | 100% have steps |
| distinction | 22 | 5% have steps |
| evaluation_criteria | 13 | 38% have steps |
| failure_catalog | 12 | 8% have steps |

**Top categories:** ai-adoption (43), problem-diagnosis (39), competitive-positioning (37)

---

## The Two Failure Modes to Prevent

| Failure Mode | What It Looks Like | Why It Matters |
|---|---|---|
| **Framework ignored** | Framework is injected, but the model produces advice a vanilla LLM would have given anyway. Nate's named lens isn't in the response. | Users don't get Nate's specific perspective — they get generic AI. The feature doesn't work. |
| **Framework hurts non-framework queries** | Framework fires on an unmatched query. Model mechanically applies it and gives worse advice than vanilla. | Checklist tunnel vision — the system actively degrades quality on misfires. |

Both must be evaluated. Most eval plans only test the first one.

---

## Eval Architecture: 4 Tests

### Test 1: Originality Test

**Question:** Would a vanilla LLM produce structurally equivalent advice without this framework injected?

**When:** Pre-enrichment. Run on current frameworks before KIN-352/357.

**Mechanism:**
1. For each framework, generate 2 queries matching its `when_to_apply` triggers
2. Run both with and without the framework injected, same model, same temperature
3. LLM-as-judge renders a binary verdict: *Does the framework-injected response contain concepts, vocabulary, or structural reasoning that the vanilla response does not?*

**Type-aware rubric:**

| Type | Pass Condition |
|---|---|
| reframe / distinction | Model uses Nate's specific named categories or vocabulary. A generic reframe in different language = fail. |
| diagnostic / procedure | Model explicitly runs the framework's steps or produces the intermediate artifacts. Generic diagnosis without Nate's structure = fail. |
| taxonomy | Model applies Nate's specific taxonomy tiers — not just general categorization. Generic labels = fail. |
| failure_catalog | Model identifies the specific named failure mode — not just "things can go wrong." Generic warnings = fail. |

**Sample size:** All 184 frameworks × 2 queries = 368 comparisons. Automatable with LLM-as-judge. Owner: Jìan.

**Decision gate:** Frameworks that fail both queries are flagged for review before launch. Track the failure reason:
- Weak triggers → feeds KIN-351
- Weak content (vanilla LLM already knows this) → candidate for cut from curated set

---

### Test 2: Framework Application Quality Test

**Question:** When the framework fires, does the model actually USE it — or does it produce reasoning theater?

**When:** Post-enrichment. Runs after KIN-352/357 pilot (first 20 frameworks).

Reading output text is insufficient to verify framework use — the model can parrot a framework without causally using it. This test verifies that conclusions *depend* on the framework's intermediate outputs.

**Mechanism for procedural frameworks** (diagnostic + procedure types, 56 frameworks):
1. Generate a query, inject the framework, capture the response
2. Corrupt the framework: change a key artifact output (e.g., "this position is durable" → "this position is vulnerable"), re-run
3. LLM-as-judge: *Does the final advice change in the direction the corruption would predict?* If yes → framework is causally used. If advice is unchanged → reasoning theater.

**Mechanism for conceptual frameworks** (reframes, distinctions, taxonomies, failure catalogs, 128 frameworks):
1. Minimal-pair test: write two versions of the same query — one that matches the `when_to_apply` conditions, one that doesn't
2. Verify the framework is applied to the matching query and not applied to the non-matching query
3. When applied, verify the model uses Nate's specific vocabulary and categorical structure, not the surface pattern

**Decision gate:** Run Test 2 on the 20-framework enrichment pilot before enriching the remaining 164. If the enriched format doesn't pass Test 2 at a higher rate than the current format, stop and revise the enrichment approach.

---

### Test 3: No-Harm Test

**Question:** When a query doesn't match a framework's trigger conditions, does injecting the wrong framework degrade advice quality?

**When:** Pre-launch.

**Mechanism:**
1. Build 20–30 baseline queries — general advisory questions the ICP would plausibly ask that shouldn't trigger any specific framework
2. For each baseline query, inject the top-1 framework selected by the pipeline
3. LLM-as-judge: *Is the advice worse, more constrained, or less responsive to the user's actual question than a vanilla response?*
4. Separately: inject a deliberately wrong framework (most topically distant) and verify the model doesn't apply it inappropriately

**What it catches:**
- Frameworks missing `do_not_use_when` conditions or applicability gates
- Retrieval misfires on common queries
- Tunnel vision risk — model over-applies framework structure to questions that need flexibility

**Decision gate:** If >15% of misfire tests degrade quality, applicability gate content needs strengthening before launch.

---

### Test 4: Retrieval-Framework Separation Test

**Question:** Is a bad advisory output caused by the wrong framework being selected, or by the right framework being poorly formatted or applied?

**When:** Pre-launch baseline + ongoing production triage.

Without this separation, you can't diagnose root cause. A bad output may be: (a) wrong framework selected, (b) right framework, bad application, or (c) right framework, right application, model failed to use it.

**Mechanism:**
1. For any advisory output receiving negative signal, run the same query under 3 conditions:
   - No framework injected (vanilla baseline)
   - Correct framework manually injected (bypass retrieval)
   - Pipeline-selected framework injected (as shipped)
2. Diagnose:
   - If condition (b) is clearly better than (a) → framework has value, retrieval may have misfired. Root cause = retrieval pipeline.
   - If condition (b) is not better than (a) → framework content is the problem. Root cause = enrichment quality.

**For MVP pre-launch:** Run manually on 10–15 representative queries spanning all 7 type categories. Automation not required to be useful.

**Production:** Becomes the standard triage protocol for user-reported failures.

---

## Test Sequencing

```
NOW (pre-enrichment):
  Test 1: Originality Test — all 184 frameworks
  → Flags weak-content frameworks for cut or de-prioritization
  → Confirms which trigger sets need KIN-351 work

AFTER KIN-352/357 PILOT (first 20 frameworks enriched):
  Test 2: Application Quality Test — pilot set only
  → Verify enrichment improved causal framework use
  → Gate: do not enrich remaining 164 until pilot passes

PRE-LAUNCH:
  Test 3: No-Harm Test — 20–30 baseline queries
  → Verify injection doesn't degrade general queries
  Test 4: Retrieval-Framework Separation — 10–15 representative queries
  → Establish root-cause diagnostic baseline before production

PRODUCTION (post-launch):
  Test 4 — ongoing triage protocol for user-reported failures
  Test 2 — re-runs on new enriched batches before they go live
```

---

## Implications for Open Tickets

| Ticket | Connection to This Plan |
|---|---|
| **KIN-351** (user-language triggers, P0) | Test 1 failures where the framework has good content but weak triggers feed directly into KIN-351. |
| **KIN-352** (nate_would_say + guidance, P0) | Test 2's corruption test is how you verify this enrichment actually worked. Design the enrichment fields and the Test 2 rubric together — they should measure the same thing. |
| **KIN-357** (stepless enrichment, P1) | Test 1 on current frameworks surfaces which conceptual-type frameworks fail the originality test today. That's the primary input for what `guidance` content needs to contain for non-procedural types. |

---

## Risks

1. **LLM-as-judge may be overgenerous.** Judges tend to find value in any injected content. The Test 1 rubric must anchor on Nate's *specific* vocabulary and categorical structure — not just "better reasoning." Jìan should calibrate the judge against a handful of human-labeled examples before running at scale.

2. **Test 2 corruption is harder for conceptual frameworks.** Corrupting a reframe is less straightforward than corrupting a step output. The minimal-pair approach is the right substitute, but requires careful query design to avoid false positives.

3. **No-Harm baseline query quality matters.** If baseline queries are too easy or too domain-specific, tunnel vision risk won't surface. Queries should cover adjacent domains that could plausibly trigger a wrong framework.

---

## Alternatives Considered

**Run only Test 1, call it good.** Rejected: Test 1 tells you if frameworks add value but doesn't tell you if they hurt on misfires. For a feature that fires dynamically, the no-harm test is not optional.

**Human annotation instead of LLM-as-judge.** Better ground truth but 10–20x slower. Right approach for judge calibration and spot-checking; wrong approach for running 368 comparisons pre-launch. Recommended hybrid: LLM-as-judge with human calibration on a 20-case sample.

**Test only after enrichment.** Rejected: Test 1 pre-enrichment establishes a baseline. Without it, you can't measure whether enrichment improved things.
