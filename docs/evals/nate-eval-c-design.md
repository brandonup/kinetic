---
Date: 2026-05-25
Persona: SMB Owner (Eval C)
Reference: jtbd-nate-agent.md, nate-system-prompt.md, nate-eval-a-design.md, nate-eval-b-design.md
Code: packages/api/evals/nate_eval_c/
---

# Nate Eval C — Design Document

## What This Eval Tests

Eval C measures whether the Nate B. Jones agent performs for **Persona C: SMB
Owner** — a small-business owner-operator watching AI erode their competitive
position. The SMB owner is the operator AND the decision-maker, has less
runway than a founder, no strategy team, no peers to bounce things off, and is
actively facing the question: "Will AI take my clients? What do I do before
it does?"

The eval does NOT test retrieval, framework selection, or Kinetic platform
behavior. It tests output quality from the SMB owner's perspective: does Nate
actually help an owner-operator survive AI substitution pressure in a way a
generic ChatGPT prompt would not?

The benchmark is the JTBD Persona C pass bar:
**"Concrete, actionable guidance for their specific business type — not
industry-generic platitudes."**

## Four Failure Modes (mirrored from Eval A and B)

Same four-judge structure. The only adaptations:
- `context_use` validates the response uses Roman-Creative-specific facts
  (12-person agency, $1.8M ARR, 5-month runway, recent churn signals)
- `ai_expertise` emphasizes AI's specific mechanisms in **service-business
  substitution** (vs. founder/product or consultant AI dynamics)

| # | Failure Mode | Why It Matters for Persona C |
|---|---|---|
| 1 | Specificity | An SMB owner with 5 months runway can't iterate on a menu of considerations. They need a verdict to act on this week. |
| 2 | Context Use | The fixture contains hard signals (utilization, runway, churn pattern). If Nate ignores them, the advice is industry-generic. |
| 3 | Voice | Generic empathy ("that's a tough situation") wastes the owner's time. Nate's directness IS the value. |
| 4 | AI Transformation Expertise | The SMB owner is being asked to bet their livelihood on AI's trajectory. Generic AI-speak doesn't help them handicap it. |

## Dataset

**15 test cases** across 5 trigger contexts:

| Trigger | Cases | Description |
|---|---|---|
| ai-threat | 4 | Existential signals: AI tools eating his work (C01–C04) |
| mid-decision | 3 | Operational choices under AI pressure (C05–C07) |
| stress-test | 4 | Marcus stress-testing his survival thesis (C08, C09, C10, C15) |
| competitive | 2 | Specific competitor moves (C11, C12) |
| org-design | 2 | Restructuring team for AI-native ops (C13, C14) |

### Dataset Tuple Structure

    (axis_a: trigger, axis_b: decision_type, axis_c: stakes)

- axis_a (trigger): ai-threat | mid-decision | stress-test | competitive | org-design
- axis_b (decision type): hiring | pricing | positioning | tools | capacity
- axis_c (stakes): existential | operational | client-facing

### Context Fixture: Marcus Reyes + Roman Creative (small marketing agency)

**Fixture choice:** Owner-operator of a 12-person Austin-based content + brand
agency ($1.8M ARR, 5-month runway, 22 retained clients, recent AI-driven
churn). Chosen from the JTBD-listed SMB segments (marketing agency, law firm,
logistics, trade) because:

1. **Maximally exposed to AI substitution in 2026.** Content / creative
   agencies are the SMB segment where AI substitution dynamics are most
   visible and most urgent. The persona faces the JTBD bar's defining
   question ("Will AI take my clients?") at its most acute.
2. **Concrete enough for context_use signal.** The fixture has hard numbers
   (team size, ARR, runway, utilization decline, ACV, churn count) and
   specific competitive signals (Jasper-adjacent platforms, in-house teams).
   The context_use judge has measurable targets.
3. **Cross-persona separation.** Brandon-as-founder (Eval A) has multi-year
   runway and platform-tech leverage. Sarah-the-consultant (Eval B) has
   advisory leverage. Marcus has neither — he's the operator AND the
   strategist AND the salesperson with thin margins. Tests Nate's range.
4. **Matches the prompt's current persona-tuning.** Nate's current prod
   system prompt is explicitly SMB-tuned ("You are Nate B. Jones — a
   strategic advisor specializing in AI transformation for small and mid-
   sized businesses"). Eval C is the most-aligned of the three evals with
   the actual prompt configuration. (Eval A and B both pass against this
   prompt despite the misalignment, but Eval C is the on-target test.)

Brandon's Claude Projects content is NOT used in this fixture (per task brief).
The Marcus/Roman Creative fixture is fully hardcoded.

## Judge Prompts

Full judge prompts are in `packages/api/evals/nate_eval_c/judges.py`. Summary:

| Judge | What PASS looks like | What FAIL looks like |
|---|---|---|
| specificity | Commits to a position with named numbers, timelines, roles | Considerations list; asks Marcus for context he already gave |
| context_use | References Roman, Marcus's role, the 12-person team, runway, recent churn signals, or Marcus's hypotheses | Generic "your agency" advice that could fit any small business |
| voice | Conclusion-first, no empathy filler ("that's tough"), no hedging | "That's a really tough situation" opener, "depends on your unique...", balanced "on the one hand" |
| ai_expertise | Engages with AI's specific service-substitution mechanisms (draft-work substitution, mid-tier pricing collapse, labor utilization compression) | Generic "AI is changing the landscape" language, treats AI as a tool to adopt |

Each judge: one failure mode only, binary PASS/FAIL, critique before verdict,
at least one PASS example and one FAIL example.

## Negative Controls (Calibration)

Three negative controls verify the judges can return FAIL:

| ID | Bad response style | Expected fails |
|---|---|---|
| NC01-generic-chatgpt | Generic empathy + considerations menu | specificity, context_use, voice, ai_expertise |
| NC02-asks-for-context | Asks Marcus to re-explain agency type, revenue, client base | specificity, context_use |
| NC03-hedged | "On one hand / on the other hand / reasonable people disagree" | specificity, voice |

## Pass Thresholds

**Suite PASS bar:** All 4 judges must achieve ≥ 80% pass rate across the 15
real test cases AND all 4 judges must be calibrated against the negative
controls (zero violations, zero errors).

Rationale matches Eval A and B.

Judge model: `gpt-4o`. Generation: Nate agent in Kinetic prod (Claude Sonnet 4.6).

## How to Run

### Dry-run

    cd /Users/brandonupchuch/son_of_anton/projects/kinetic/packages/api
    .venv/bin/python -m evals.nate_eval_c.eval --dry-run

### Live run

    cd /Users/brandonupchuch/son_of_anton/projects/kinetic/packages/api
    JUDGE_API_KEY=<openai-key> \
    KINETIC_USER_TOKEN=<supabase-jwt> \
    KINETIC_AGENT_ID=9b54b4c3-eec0-44dd-add6-feb368f400e8 \
    .venv/bin/python -m evals.nate_eval_c.eval

### Output

Results saved to `evals/nate_eval_c/results/<timestamp>/results.json`.
Exit codes: 0=PASS, 1=FAIL (suite), 2=ERROR (runner).

## Files

    packages/api/evals/nate_eval_c/
      eval.py        -- runner (mirrors nate_eval_a, imports c's data + judges)
      data.py        -- 15 test cases + 3 negative controls + Marcus/Roman fixture
      judges.py      -- 4 binary Pass/Fail judge prompts (adapted for SMB owner)
      results/       -- timestamped JSON results

    docs/evals/
      nate-eval-c-design.md  -- this file
