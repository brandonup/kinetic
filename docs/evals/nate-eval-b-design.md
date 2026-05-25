---
Date: 2026-05-25
Persona: Business Consultant (Eval B)
Reference: jtbd-nate-agent.md, nate-system-prompt.md, nate-eval-a-design.md
Code: packages/api/evals/nate_eval_b/
---

# Nate Eval B — Design Document

## What This Eval Tests

Eval B measures whether the Nate B. Jones agent performs for **Persona B:
Business Consultant** — a fractional advisor who uses Nate inside live client
engagements to sharpen advice and outperform generalist consultants. The
consultant uses Nate to stress-test their own recommendations before delivering
to a client, prep for high-stakes client meetings, and react to competitive
signals affecting their client.

The eval does NOT test retrieval accuracy, framework selection, or Kinetic
platform behavior. It tests output quality from the consultant's perspective:
does Nate actually sharpen the consultant's advisory work in a way a generic
ChatGPT prompt would not?

The benchmark is the JTBD Persona B pass bar:
**"Sharper and more specific than a generalist AI would produce; could be
delivered directly to a client."**

## Four Failure Modes (mirrored from Eval A)

| # | Failure Mode | Why It Matters for Persona B |
|---|---|---|
| 1 | Specificity | A consultant who gets a menu can't sharpen anything — they wanted a verdict to translate to the client. |
| 2 | Context Use | The consultant injected client + engagement context for exactly this query. If Nate ignores it, the consultant could have used vanilla ChatGPT. |
| 3 | Voice | A hedged Nate is indistinguishable from a generalist AI advisor — the consultant's edge disappears. |
| 4 | AI Transformation Expertise | The consultant pays Sarah-tier rates partly because she stays ahead of AI dynamics. Generic AI-speak from Nate fails the value prop. |

The four-judge structure mirrors Eval A. The only adaptation is the
`context_use` judge prompt, which checks the response uses CONSULTANT-specific
context (Sarah's practice + her active Vellum engagement) rather than generic
founder context.

## Dataset

**15 test cases** across 5 trigger contexts:

| Trigger | Cases | Description |
|---|---|---|
| mid-advisory | 4 | Mid-engagement, prepping advice for a live client (B01–B04) |
| stress-test | 4 | Stress-testing a recommendation before delivering it (B05–B08) |
| competitive | 3 | Reacting to a competitive AI signal affecting the client (B09–B11) |
| org-design | 2 | Advising client on org / team restructuring under AI (B12, B13) |
| practice | 2 | Sarah's own practice meta-decisions (B14, B15) |

### Dataset Tuple Structure

    (axis_a: trigger, axis_b: decision_type, axis_c: stakes, prompt, context)

- axis_a (trigger): mid-advisory | stress-test | competitive | org-design | practice
- axis_b (decision type): gtm-strategy | build-vs-buy | pricing | hiring | positioning
- axis_c (stakes): client-facing | board-facing | internal-execution

### Context Fixture: Sarah Chen + Vellum Workflows

**Fixture choice:** A fractional CMO advising a fictional Series B B2B SaaS
("Vellum Workflows," $8M ARR AI ops platform). Chosen because:

1. **Realistic Persona B match.** Fractional CMO / fractional CRO / fractional
   advisor is the most common form of "business consultant using AI tools to
   outperform peers" in 2026. Solo practice, multiple concurrent retainers,
   high hourly rate, AI-native differentiation.
2. **Concrete enough to test context_use.** The fixture has named entities
   (Vellum, $8M ARR, Series B from Greylock, Adept/Magic competitors), specific
   stage facts (35 employees, 14-month runway, 90→45 day sales-cycle goal),
   and specific working hypotheses (commoditization within 12 months, BYOK
   hurting non-technical buyers). The context_use judge has hard targets.
3. **Mirrors Brandon's actual world.** Sarah is a B2B SaaS specialist —
   adjacent enough to Brandon's domain that Nate's KB (Substack posts on AI
   strategy) should retrieve relevant material.
4. **Avoids overlap with Eval A.** Eval A tests Brandon-as-founder. Sarah is
   advising someone else, which exercises a different style of question
   ("what should I tell my client" vs "what should I do") and a different
   context-use pattern (consultant's hypotheses about a separate company,
   not the consultant's own company).

Brandon's Claude Projects content is NOT used in this fixture (per task brief —
that's for Persona A only). The Sarah/Vellum fixture is fully hardcoded.

## Judge Prompts

Full judge prompts are in `packages/api/evals/nate_eval_b/judges.py`. Summary:

| Judge | What PASS looks like | What FAIL looks like |
|---|---|---|
| specificity | Commits to a position the consultant can translate to client advice | Generic consideration lists; asks the consultant for more info |
| context_use | References Vellum, Sarah's practice, Vellum's competitive/financial position, or Sarah's hypotheses | Generic advice that could be from any "advising a SaaS client" prompt |
| voice | Conclusion-first, opinionated, no filler opener | Great-question opener, hedged qualifications, balanced pros/cons |
| ai_expertise | Engages with specific AI mechanism (per-seat collapse, commoditization timing, model-layer vs app-layer moats) | Generic "AI is changing the landscape" language |

Each judge: one failure mode only, binary PASS/FAIL, critique before verdict,
at least one PASS example and one FAIL example.

## Negative Controls (Calibration)

Three negative controls verify the judges can return FAIL:

| ID | Bad response style | Expected fails |
|---|---|---|
| NC01-generic-chatgpt | Generic "great question, here are considerations" response | specificity, context_use, voice, ai_expertise |
| NC02-asks-for-context | Asks Sarah to re-explain Vellum's stage, ARR, competitors | specificity, context_use |
| NC03-hedged | "On one hand / on the other hand / reasonable people disagree" | specificity, voice |

## Pass Thresholds

**Suite PASS bar:** All 4 judges must achieve ≥ 80% pass rate across the 15
real test cases AND all 4 judges must be calibrated against the negative
controls (zero violations, zero errors).

Rationale matches Eval A — 80% threshold balances brittleness vs signal; full
calibration prevents pass-by-bypass.

Judge model: `gpt-4o`. Generation: Nate agent in Kinetic prod (Claude Sonnet 4.6).

## How to Run

### Dry-run

    cd /Users/brandonupchuch/son_of_anton/projects/kinetic/packages/api
    .venv/bin/python -m evals.nate_eval_b.eval --dry-run

### Live run

    cd /Users/brandonupchuch/son_of_anton/projects/kinetic/packages/api
    JUDGE_API_KEY=<openai-key> \
    KINETIC_USER_TOKEN=<supabase-jwt> \
    KINETIC_AGENT_ID=9b54b4c3-eec0-44dd-add6-feb368f400e8 \
    .venv/bin/python -m evals.nate_eval_b.eval

Defaults:
- `KINETIC_COMPANY_ID`: Brandon's "AI Consulting" company in prod
  (`51d96aaf-2a73-42bd-b3e4-397084f543d7`)
- `KINETIC_AGENT_ID`: Nate (`9b54b4c3-eec0-44dd-add6-feb368f400e8`)

Each test case spins a fresh conversation in Kinetic prod, sends the prompt
(prepended with the consultant context fixture as `[KINETIC CONTEXT]`), and
captures the full SSE response.

### Output

Results saved to `evals/nate_eval_b/results/<timestamp>/results.json`.
Exit codes: 0=PASS, 1=FAIL (suite), 2=ERROR (runner).

## Files

    packages/api/evals/nate_eval_b/
      eval.py        -- runner (cloned from nate_eval_a, imports b's data + judges)
      data.py        -- 15 test cases + 3 negative controls + Sarah/Vellum fixture
      judges.py      -- 4 binary Pass/Fail judge prompts (adapted for consultant)
      results/       -- timestamped JSON results

    docs/evals/
      nate-eval-b-design.md  -- this file
