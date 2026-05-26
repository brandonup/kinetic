---
Date: 2026-05-24
Persona: Founder/CEO (Eval A)
Reference: jtbd-nate-agent.md, nate-system-prompt.md
Code: packages/api/evals/nate_eval_a/
---

# Nate Eval A — Design Document

## What This Eval Tests

Eval A measures whether the Nate B. Jones agent performs for **Persona A: Founder/CEO** — a tech founder or startup CEO making company-level strategic bets on AI, mid-work, with no strategy team. This is the primary ICP for Kinetic at launch.

The eval does NOT test retrieval accuracy (that is ), framework selection (that is ), or Kinetic platform behavior. It tests **output quality from the user perspective**: does Nate actually give useful advice to this specific type of user?

The benchmark is: **could the user have gotten this response from a generic ChatGPT prompt with no context injected?** If yes, the eval fails.

## Why These Four Failure Modes

From  shared pass/fail bar:

| # | Failure Mode | Why It Matters |
|---|---|---|
| 1 | Specificity | Generic menus of considerations are the dominant failure mode of AI advisors. Nate VP is a specific verdict, not balanced options. |
| 2 | Context Use | The core Kinetic claim is persistent context that eliminates re-explanation. If Nate ignores injected context, Kinetic value prop fails. |
| 3 | Voice / Tone | Nate voice (direct, opinionated, no hedging) is a product differentiator. Generic AI tone is indistinguishable from ChatGPT. |
| 4 | AI Transformation Expertise | Nate is positioned as an AI transformation expert, not a generic business advisor. Generic AI-speak (where replacing AI with software still works) signals the KB is not effective. |

## Dataset

**15 test cases** across 4 trigger situations from  Trigger Situations:

| Trigger | Cases | Description |
|---|---|---|
| mid-decision | 4 | Mid-work AI decision with no strategy team (A01, A02, A03, A12) |
| stress-test | 5 | Stress-testing an assumption before a board/investor/customer conversation (A04, A05, A06, A11, A15) |
| competitive | 4 | Diagnosing a competitive AI signal (A07, A08, A09, A14) |
| org-design | 2 | Org/product restructuring under AI disruption (A10, A13) |

### Dataset Tuple Structure (per generate-synthetic-data skill)

Each test case is a tuple:

    (axis_a: trigger_situation, axis_b: decision_type, axis_c: stakes, prompt, context)

- axis_a (trigger): mid-decision | stress-test | competitive | org-design
- axis_b (decision type): moat-validity | build-vs-buy | pivot-timing | make-vs-hire
- axis_c (stakes): board-facing | investor-facing | internal-execution

### Context Fixture

All 15 cases use a single hardcoded context fixture representing a Brandon Kinetic session.
This simulates what Kinetic L1-L5 context stack would inject for a real user.

Key facts in the fixture (drawn from projects/kinetic/MEMORY.md and user_brandon_profile.md):
- User: Brandon Upchurch, CEO/Head of Product, Son of Anton
- Product: Kinetic, AI workspace SaaS with 9-layer context stack, BYOK model, active memory + KB
- ICP: tech founders, AI consultants, SMB leaders
- Stage: MVP shipped, early customer conversations pending
- Strategic pressure: Claude Projects, Cursor rules, GPT memory are competing context-persistence solutions

The fixture is injected as a preamble to the user prompt (not via Kinetic conversation system),
clearly delimited with [KINETIC CONTEXT] markers. This simulates context injection without
requiring a fully configured Kinetic session per case.

## Judge Prompts

Full judge prompts are in packages/api/evals/nate_eval_a/judges.py. Summary:

| Judge | What PASS looks like | What FAIL looks like |
|---|---|---|
| specificity | Commits to a position, names specific things | Generic consideration lists; hedges without committing |
| context_use | References Kinetic, Brandon, ICP, BYOK, or other fixture facts | Generic advice that could be from any founder prompt |
| voice | Conclusion-first, opinionated, no filler opener | Great question opener, hedged qualifications, balanced pros/cons |
| ai_expertise | Engages with specific AI mechanism (commoditization, context windows, model-layer moats) | Generic AI is changing the landscape language |

Each judge: one failure mode only, binary PASS/FAIL, critique before verdict, at least 2 examples.

## Pass Thresholds and Rationale

**Suite PASS bar:** All 4 judges must achieve >= 80% pass rate across the 15 test cases.

Rationale for 80%:
- 100% threshold is too brittle for a first-run baseline; ambiguous edge cases should not block.
- 80% means at most 3 of 15 cases can fail any given judge.
- Calibrated slightly higher than kb_retrieval precision@8 (70%) because voice evals have more variance than retrieval evals.

Judge model: gpt-4o (default). Configured via JUDGE_MODEL env var.

## How to Run

### Dry-run (no API calls, verifiable from code)

    cd /Users/brandonupchuch/son_of_anton/projects/kinetic/packages/api
    python -m evals.nate_eval_a.eval --dry-run

Dry-run uses DRY_RUN_MOCK_RESPONSE from data.py for generation and deterministic
PASS/FAIL alternation from _dry_run_judge() in eval.py for judges. No API keys needed.

### Live run prerequisites

1. A Kinetic prod conversation with Nate agent active (kinetic-ashy-beta.vercel.app)
2. Supabase session JWT (browser dev tools -> Application -> Local Storage -> sb-iiapaogaoadtvjnryuls-auth-token)
3. OpenAI API key for judge model
4. Nate agent definition UUID (Kinetic UI or Supabase agent_definitions table)

### Live run command

    cd /Users/brandonupchuch/son_of_anton/projects/kinetic/packages/api
    JUDGE_API_KEY=<openai-key>
    KINETIC_USER_TOKEN=<supabase-jwt>
    KINETIC_CONVERSATION_ID=<conversation-uuid>
    KINETIC_AGENT_ID=<nate-agent-uuid>
    python -m evals.nate_eval_a.eval

### Output

Results saved to evals/nate_eval_a/results/<timestamp>/results.json.
Exit codes: 0=PASS, 1=FAIL (suite), 2=ERROR (runner).

## Files

    packages/api/evals/nate_eval_a/
      eval.py        -- runner (generation + judges + metrics + report)
      data.py        -- 15 test cases + context fixture + dry-run mock
      judges.py      -- 4 binary Pass/Fail judge prompts + registry
      results/       -- timestamped JSON results (git-ignored except .gitkeep)

    docs/evals/
      nate-eval-a-design.md  -- this file
