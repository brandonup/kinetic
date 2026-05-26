---
Status: Stale plan — pending re-run on the Gemini-embedded corpus (see KIN-497).
        KIN-467 migrated the platform embedding to Gemini `gemini-embedding-001`
        in March 2026; eval embedding must match prod to be meaningful.
Ticket: KIN-340 (superseded for execution by KIN-497)
Date: 2026-03-24
Run type: Pending (requires seeded agent + live embedding service)
---

# KIN-340 — Framework Selection Eval

## Target

≥ 80% precision: for each query, the pipeline either selects the correct framework or correctly returns "none" for off-topic queries.

## Methodology

1. Seed a test agent with 10 diverse frameworks (strategy, communication, decision-making, prioritization, technical, etc.)
2. Run 20 queries through `select_framework()` — mix of on-topic (15) and off-topic (5)
3. For each query, compare the selected framework against the expected winner
4. Score: 1 = correct selection or correct "none"; 0 = wrong framework or false positive "none"
5. Precision = correct / 20

## Test Cases (20 queries)

### On-topic queries — expect a specific framework (15)

| # | Query | Expected framework |
|---|---|---|
| 1 | "We're deciding between two vendors for our data pipeline. How should I structure this?" | Decision matrix / criteria scoring |
| 2 | "I need to evaluate our competitive position before the board meeting." | SWOT analysis |
| 3 | "The team is scattered across 4 time zones. What's the best way to keep everyone aligned?" | Communication / async-first |
| 4 | "We have 12 bugs open and 3 features promised to customers this sprint. How do I prioritize?" | Prioritization / triage |
| 5 | "I'm pitching to investors next week. What story should I tell?" | Storytelling / pitch structure |
| 6 | "Our NPS dropped 15 points last quarter. How do I diagnose the root cause?" | Root cause analysis / 5-whys |
| 7 | "I need to onboard a new engineer who's never used our stack. What's the right approach?" | Onboarding / knowledge transfer |
| 8 | "The product roadmap has 30 items. How do I get leadership aligned on what to cut?" | Strategic planning / roadmap pruning |
| 9 | "This code module has grown to 4,000 lines. How do I decide what to refactor first?" | Technical debt triage |
| 10 | "I keep getting pulled into tactical firefighting. How do I create thinking time?" | Time management / deep work |
| 11 | "Two engineers on the team keep disagreeing in code reviews. What's the right intervention?" | Conflict resolution |
| 12 | "We're about to launch a new feature. How do I think about risk?" | Risk analysis / launch readiness |
| 13 | "My team seems unmotivated lately. How should I approach 1:1s?" | Motivation / feedback frameworks |
| 14 | "We need to set Q3 OKRs but don't know what to focus on." | Goal setting / OKR structure |
| 15 | "The biggest technical debt item is blocking three new features. How do I make the case to fix it?" | Stakeholder communication / business case |

### Off-topic queries — expect "none" (5)

| # | Query | Expected |
|---|---|---|
| 16 | "What's the capital of France?" | none |
| 17 | "Can you write a haiku about autumn?" | none |
| 18 | "What's 2 + 2?" | none |
| 19 | "How do I make chocolate chip cookies?" | none |
| 20 | "What year was the Eiffel Tower built?" | none |

## Scoring

- True positive: on-topic query selects the right framework class
- True negative: off-topic query returns `matched_framework_id=None`
- False positive: off-topic query triggers a framework (wrong)
- False negative: on-topic query returns "none" (miss)

Precision = (TP + TN) / 20. Target: ≥ 16/20.

## Status

**Not yet run.** Requires:
- Seeded agent definition with ≥10 frameworks and pre-computed trigger embeddings in pgvector
- Live `EmbeddingService` (platform OpenAI key)
- `select_framework()` callable against the test agent

Run command (once environment ready):
```bash
# From packages/api/
python evals/framework_selection/eval_runner.py --agent-id <seeded-agent-id>
```

The eval runner script does not yet exist — it should be created as part of the live run setup.

## Boost Logic Test Cases (trigger-count boost)

The framework selection pipeline applies `MULTI_TRIGGER_BOOST = 0.05` per additional trigger match above the first. These cases verify boost correctness:

| # | Scenario | Expected behavior |
|---|---|---|
| B1 | Framework A: 1 trigger hits (sim=0.75). Framework B: 3 triggers hit (max_sim=0.72). | B wins: 0.72 + 2×0.05 = 0.82 > 0.75. Boost breaks the tie. |
| B2 | Framework A: 1 trigger hits (sim=0.85). Framework B: 5 triggers hit (max_sim=0.60). | A wins: 0.60 + 4×0.05 = 0.80 < 0.85. Boost not enough to overcome gap. |
| B3 | Two frameworks both have 2 triggers, identical boosted scores. | Higher raw max_sim wins (stable sort). |
| B4 | Top framework boosted score still below `FRAMEWORK_MIN_SIMILARITY`. | Returns "none" — boost can't rescue below-threshold matches. |

## Precision + Recall Metrics

| Metric | Definition | Target |
|---|---|---|
| Precision | (TP + TN) / total queries | ≥ 80% (16/20) |
| Recall (on-topic) | TP / (TP + FN) — correct selections / total on-topic | ≥ 80% (12/15) |
| False positive rate | FP / total off-topic | ≤ 20% (≤ 1/5) |
| Boost contribution | Queries where boost changed the winner vs. raw max_sim | Report count (no target — informational) |

## Unit Test Coverage (in CI)

`tests/test_framework_selection.py` covers the pipeline logic with mocked embeddings:
- Winner selection when similarity > threshold
- Multi-trigger boost applied
- No match when all scores < threshold
- No match when agent has no frameworks

These do not substitute for the precision eval — they verify logic, not LLM embedding quality.
