# NBJ Extractor — Extraction Learnings

_Updated after each extraction run. Read this before starting a new run._

---

## Pipeline Behavior

### False Positive Truncation Warnings (2026-03-23)
The truncation detection in `_process_post` checks if the raw response ends with `]` or `}`. The model often wraps its JSON in markdown code fences (` ```json ... ``` `), so the response ends with ` ``` ` and the warning fires even when the response is complete. **This is a false positive.** The JSON is parsed correctly regardless — confirm by checking that frameworks still appear as "Found" on the lines immediately after the warning. The real tell for actual truncation would be a JSON parse error, not this warning. Fix if it becomes noisy: add `` '`' `` to the valid last-char set at line 391.

### `max_tokens` (2026-03-23)
Already set to `8192` in `_process_post`. Do not lower this — posts with 4–5 frameworks generate enough JSON to approach 4096 tokens, which was the original limit that caused real truncation in earlier versions.

### Pass 2 Re-processes All Candidates (2026-03-23)
Pass 2 reads the full `pass1_candidates.jsonl` every time, not just new additions. This is by design — it deduplicates across the full pool. Existing frameworks are not lost, but the index is rebuilt from scratch. The `pass2_progress.jsonl` resume file prevents Opus from re-enriching frameworks it already processed.

---

## Post Type Patterns

### Posts That Yield Zero Frameworks
From the first 20-post run, 7 of 20 posts produced no frameworks. All fell into these categories:

| Pattern | Example |
|---|---|
| AI news / model release commentary | GPT-5.4 eval, $700B cloud bet, Claude benchmark comparison |
| Product demo / walkthrough | Claude in Chrome, /loop feature explainer |
| How-to / setup guide | Open Brain 45-min setup guide |
| Prompt kit posts | "6 prompts to do X" |
| Strategic argument (no named tool) | "Don't cut headcount" thesis — references Jevons Paradox but doesn't teach it as a framework |

**Implication:** Expect roughly 30–40% of posts to yield zero frameworks. Don't treat low yield as a pipeline problem.

### Executive Briefing Posts — Incomplete Content (2026-03-23)
Posts titled "Executive Briefing: ..." follow a consistent format: written teaser with framework names dropped → full content delivered via podcast/audio to paid subscribers. The scraper only gets the teaser. This produces `extraction_incomplete: true` quarantine entries — the framework name and description are solid, but steps and diagnostic questions are hollow.

**Known affected posts:** 189211551, 190757490 (and likely others in the same series).

**Recovery path:** Requires audio transcripts from the paid briefings. Cannot be recovered from scraped text alone.

---

## Quality Flag Reference

When Pass 2 reports quality validators flagged N issues, here's what each flag means:

| Flag | Meaning | Action |
|---|---|---|
| `extraction_incomplete` | Post referenced content not visible in scraped text (usually audio/podcast). Steps array is empty. | Quarantined automatically. Recover only if transcript is available. |
| `process_spec` | Framework slipped through pass 1 that is actually a build guide or operational procedure, not a reasoning tool. | Quarantined. Pass 1 prompt should have caught it — note the post for prompt refinement. |
| `hardcoded_model_names` | Framework steps or principles reference a specific model name (e.g., "GPT-4", "Sonnet"). Violates model-agnosticity rule. | Flagged for manual edit. Replace with capability description ("a model optimized for extended reasoning"). |

---

## Verification

### Manual Post Review (2026-03-23)
After the first 20-post run, all 7 zero-framework posts were manually read in full. Confirmed: the extractor made the right calls on all 7. No missed frameworks. The filter is working correctly.

**What to look for in borderline posts:**
- Does the author name the concept and give it structure (steps, principles, criteria)? → Framework.
- Is it a strategic argument that *uses* existing concepts as evidence? → Not a framework.
- Is it a prompt template or setup guide? → Not a framework, even if structured.
- Does it reference specific content ("here are my 5 questions") that isn't visible? → Extract with `extraction_incomplete: true`.

---

## Batch Sizing

- **50–100 posts per run** is a reasonable batch size for Sonnet pass 1 + Opus pass 2. 100 ran cleanly; 185 was not tested.
- Most posts in the corpus are news/commentary — expect framework density to be higher in older posts (the corpus skews toward frameworks earlier in the author's publication history).
- Total corpus: **505 posts**. **420 of 505 processed as of 2026-03-23.** 85 remaining (offset 420–505). Final batch pending.

---

## Framework Schema Design (2026-03-23)

### The uniform schema is the wrong shape

The current schema forces every framework into `steps` + `principles`. This is a bad fit. Most of Nate's frameworks aren't step-by-step procedures — they're distinctions, taxonomies, diagnostic question sets, reframes, decision trees, and failure mode catalogs. Forcing a distinction into "steps" produces fabricated filler or awkward reformulations the agent recites back instead of reasons with.

### Inject the idea, not instructions about the idea

The single highest-leverage insight: **the framework object should contain the actual intellectual contribution in natural language, not metadata about it.** An LLM doesn't need "Step 1: Ask about X. Step 2: Analyze Y." It needs to *understand the distinction clearly enough to diagnose which side the user is on.* Give the agent the idea — it will figure out how to apply it. What it can't do is invent Nate's specific distinctions and reframes from nothing.

### Type the intellectual move

Frameworks should declare their type (`distinction`, `taxonomy`, `diagnostic`, `reframe`, `decision_tree`, `failure_modes`, `evaluation_criteria`, `mental_model`). The substance field's internal structure should vary by type — a distinction has two sides, a taxonomy has categories, a diagnostic has questions. This replaces the one-size-fits-all `steps` array.

### Key schema changes identified

| Current field | Recommendation |
|---|---|
| `description` | Replace with `the_move` — 2-4 sentences stating the actual intellectual contribution, not what the framework is "about" |
| `steps` | Replace with `substance` — type-dependent structure carrying the actual content (distinction sides, taxonomy categories, diagnostic questions, etc.) |
| `principles` | Replace with `nate_would_say` — 1-2 sentences in Nate's actual voice, the sharp/direct version of the advice. Generic principles don't constrain agent behavior; specific voice lines do. |
| `example_application` | Cut as mandatory field. Include inside `substance` only where a worked example adds value. |
| `category` | Keep for human browsing only. Classifier should route on `when_to_apply` + `type`, not category. |

### The quality test that matters most

> "Would a vanilla LLM produce the same advice without this framework injected?"

If yes, the framework adds no value and shouldn't exist in the index. The injection must cause the agent to think differently, not just reference a template.

### `when_to_apply` collision is the top routing risk

At 115 frameworks, trigger overlap is inevitable if triggers read like topic labels. Each trigger must pass two tests: (1) would this framework be the *only* correct match? (2) does it describe a moment of confusion/risk/decision, not a topic? Bad: "Evaluating AI tools." Good: "We're trying to decide between Claude Code and Cursor for our engineering team."

### `confidence` should be a hard runtime gate

Currently low-confidence frameworks can still be injected. Wire the classifier: `low` = never inject (quarantine), `medium` = tiebreaker penalty, `high` = eligible. One-line change, outsized impact on UX.

### Full recommendations doc

See `/kinetic/framework-design-recommendations.md` for the complete proposed schema with type-specific substance examples and migration path.

---

## Prompt Authoring — Pass 2 Enrichment

### Mode 3: the agent reasons FROM content, not ABOUT it (2026-03-23)

The single most important authoring principle for framework enrichment content. There are three modes:

- **Mode 1 (instructions):** "First, ask the user whether they have proprietary data." — Tells the agent what to do. Brittle and paternalistic.
- **Mode 2 (reference):** "This diagnostic is used to evaluate AI company defensibility." — Tells the agent what the framework is about. Creates metadata, not reasoning.
- **Mode 3 (assertions):** "Most AI products disappear when their model provider ships the same feature. Proprietary data, workflow lock-in, and regulatory moats are the only durable positions. Model-layer execution speed is not a moat." — Gives the agent the idea. It already has the right lens before touching any scaffold fields.

**Always write `example_application`, `core_question`, and type-specific content in Mode 3.** If what you've written could appear in a user manual about the framework, rewrite it as a direct claim about the world.

### `core_question` is the semantic anchor for routing (2026-03-23)

The `core_question` field captures the user's unresolved tension in one sentence — written from inside the user's perspective, not as a description of the framework's domain.

- **Bad:** "Evaluating the defensibility of an AI startup's competitive moat."
- **Good:** "Is this AI company building a durable product, or just renting a position in someone else's stack?"

The distinction: the bad version describes what the framework does. The good version is the thing the user is feeling. At retrieval time, a user query like "we're worried our API provider will build what we built" matches the good version semantically but not the bad one.

### `type` enables type-aware enrichment — use it (2026-03-23)

Passing `type` into the enrichment prompt allows Opus to generate `example_application` in the right shape for each framework type:

| Type | `example_application` job |
|---|---|
| `distinction` | State which side the situation is on. "This is X, not Y — the tell is Z." |
| `taxonomy` | Name the category and what that classification implies for the decision. |
| `diagnostic` | Deliver the verdict and the evidence: "The answer is X. The signals are A, B, C." |
| `reframe` | Lead with the counter-claim. "The conventional read is X. That's wrong here because Y." |
| `failure_catalog` | Name the active failure mode and the early warning that confirms it. |
| `evaluation_criteria` | Score the dimension, name the indicator, state the implication. |
| `procedure` | State what the agent knows after running through it — not the steps, the output. |

Without `type`, Opus defaults to descriptive/reference mode (Mode 2). With it, it can write Mode 3 assertions shaped for the specific intellectual move the framework makes.

### `when_to_apply` triggers must be discriminating, not just relevant (2026-03-23)

The classifier's failure mode is over-matching — retrieving 3 frameworks when 1 is right. Each trigger should describe the specific situation where THIS framework is the right choice over its category-mates. The test: "Would this trigger also match the other frameworks in the same category?" If yes, rewrite it to be more specific. The right mental model: write triggers that rule out the wrong frameworks, not just rule in the right one.

---

## API Mechanics

### `max_tokens` is a required ceiling, not a target (2026-03-23)

The Anthropic API requires `max_tokens` on every call. You only pay for tokens actually generated — setting it high doesn't waste money or cause rambling. The risk is setting it too **low**, which causes the model to stop mid-response and produce truncated JSON. Current settings:

- Pass 1 (`_process_post`): `8192` — enough for posts with 4–5 frameworks
- Pass 2 enrichment (`_enrich_framework`): `1200` — bumped from 896 when `core_question` and type-aware Mode 3 content was added; Opus needs room to write substantive content across 5 fields

If you add new fields or more detailed prompt requirements, increase the Pass 2 limit accordingly.

---

## Architecture Decisions

### One-call-per-post is strictly better than batching (2026-03-23)

Earlier versions batched multiple posts per API call. This caused two failure modes: (1) cross-post contamination where frameworks were attributed to the wrong post, and (2) response truncation when a batch produced too many frameworks to fit in the token limit. The fix is one post per call. The cost is more API calls — acceptable given the quality difference.

### Dedup must run before the confidence filter (2026-03-23)

The correct order in Pass 2 is: dedup → confidence filter. The wrong order was: confidence filter → dedup. The bug: filtering first drops low-confidence candidates before dedup has a chance to merge them into their high-confidence counterparts. When a framework appears in 3 posts — 2 as "medium" and 1 as "high" — filtering first keeps only the high-confidence entry but loses the 2 source post references. Deduplication merges all source posts into the best candidate first, then the confidence filter has the full picture.

### Schema complexity should be driven by what the agent actually needs (2026-03-23)

When multiple recommendations docs produced conflicting schema designs (some suggesting 8+ new fields, sub-objects, type-specific structs), the right move was to simplify to the minimum set of changes that meaningfully change agent behavior:

1. `type` — tells the enrichment pass and the runtime agent what intellectual move this framework makes
2. `core_question` — gives the classifier a semantic anchor that's more robust than trigger-phrase matching
3. Enrichment prompt rewrite — makes existing fields carry Mode 3 content instead of Mode 2 metadata

More fields don't improve retrieval. Better content in fewer fields does.

### `type` and `date` are now part of the upload schema (2026-03-23)

`type` is a **required** field in the PRD upload schema (one of: `distinction`, `taxonomy`, `diagnostic`, `reframe`, `failure_catalog`, `evaluation_criteria`, `procedure`). `date` is **optional** (ISO 8601 datetime of the earliest source post). Both are stored in the framework record and passed through to the product. `core_question` is **internal only** — stripped at output time by `_clean_for_output()` before writing `frameworks_index.json`. Never add `core_question` back to the upload schema; its value is entirely as a routing aid during the pipeline.

### The thin heuristic filter ("no steps + medium = drop") was wrong (2026-03-23)

**Removed.** The filter assumed all frameworks should have steps — valid under the old uniform schema, but wrong with the type-aware schema. Distinctions, taxonomies, reframes, failure catalogs, and evaluation criteria are legitimately stepless. Dropping them on "no steps" threw away valid frameworks of non-procedural types. The correct thinness gate is the quality validators (self-assessment trap, literal prompt template, process spec, classifier magnet, no agent-applicable reasoning) — these catch actually-thin frameworks regardless of type. Medium confidence already applies a tiebreaker penalty in the selection pipeline; a hard drop on top of it is redundant and destructive.

**Practical consequence:** The 13 frameworks dropped in the 2026-03-23 run (`ai-agent-supervision-model`, `coordination-tax-audit-ai-era-team-sizing`, `double-compression-loop`, etc.) should be re-evaluated on the next run. Some will come back as legitimate frameworks; some may still fail the quality validators for real defects. The filter was not the right mechanism to catch them.

### Verify script syntax before running (2026-03-23)

The `main()` function was silently truncated — the script ended mid-statement with no Python-level error until runtime. Always run a syntax check after any edit to the script:

```
python -c "import ast; ast.parse(open('extract_frameworks.py').read()); print('Syntax OK')"
```

This catches truncation and syntax errors in under a second. File truncation can happen silently (editor crash, partial write) and produces a confusing `SyntaxError: '(' was never closed` at runtime rather than a clear "file is incomplete" message.

### Check what's already implemented before describing changes as pending (2026-03-23)

`core_question` removal, empty `steps` omission, and self-reference cleanup were all already implemented in the script (`_clean_for_output()` at line 866, Fix 6b at line 1252) — but were described as pending changes before the script was inspected. Before flagging script changes, read the relevant sections first. The script has evolved through multiple sessions and may already handle issues that appear unaddressed.

---

## Extraction Status (2026-03-23)

### Current Index State

As of batch 4 (offset 320–420):
- **376 production frameworks**, 11 quarantined, 167 posts scanned
- **Confidence:** 252 high (67%), 124 medium (33%), 0 low
- **Types:** taxonomy 81, procedure 78, reframe 56, diagnostic 55, distinction 44, evaluation_criteria 39, failure_catalog 23
- **Enrichment:** 100% complete — zero frameworks missing `category`, `example_application`, or `when_to_apply`
- **85 posts remaining** (offset 420–505)

### Schema State

**The current index uses the INTERMEDIATE schema, not the MVP strategy schema.** All 376 production frameworks have: `description`, `principles`, `steps`, `example_application`, `when_to_apply`, `type`, `confidence`, `category`. They do NOT have: `scaffold`, `nate_would_say`, `guidance`, or `routing.core_question`. The `core_question` field is generated during enrichment but stripped by `_clean_for_output()` before writing `frameworks_index.json`.

**Decision on schema migration (current → MVP strategy) is pending.** See `framework-mvp-strategy.md` for the target schema and migration path.

### Model Names — Systemic Issue

142 of 376 production frameworks (37.8%) contain hardcoded model names (GPT, ChatGPT, Claude, Gemini, Perplexity, Sonnet, Opus, o1, o3) in various fields. This is a corpus-wide characteristic — Nate's content naturally references specific models as examples. The `_auto_remediate()` function only cleans `steps` and `principles`; model names persist in `when_to_apply`, `example_application`, and `description`.

**Deferred to a post-extraction batch cleanup pass.** Do not quarantine individual frameworks for this.

### Quarantine Whitelist

Six frameworks were false-positive quarantined by validators that over-triggered on sequential-phase language or self-referential steps. A `QUARANTINE_WHITELIST` was added to `_quarantine_flagged()` to pass them to production:
- `code-tile-chunking` (process_spec FP)
- `architecture-first-ai-coding-workflow` (process_spec FP)
- `the-architecture-of-a-prompt` (meta_reference_steps FP)
- `five-design-principles-for-context-architecture` (tool_specific_config FP)
- `cognitive-choreography` (process_spec + meta_reference_steps FP)
- `five-high-altitude-questions-for-evaluating-platform-announc` (meta_reference_steps FP)

### Open Gaps Identified by Monica (AI Systems Advisor)

These are gaps that need to be addressed before the framework library can be evaluated for cognitive effectiveness:

1. **No Nate B. Jones system prompt exists.** The framework injection depends on a system prompt that instructs the agent to reason *through* frameworks, not just acknowledge them. Without it, even well-written frameworks produce generic responses.

2. **No cluster-aware trigger refinement was run.** ~1,500 trigger phrases in the embedding space with no dedup pass. Trigger collision is the top routing risk identified in `framework-mvp-strategy.md`.

3. **No token profiling of injection payloads.** Framework sizes vary widely (estimated 200–1200 tokens). No distribution analysis has been done against the 15% RAG_MAX_TOKENS budget.

4. **No representative user query set.** The framework selection eval has 20 generic test cases. Real queries for the target audience (AI founders, consultants, executives) have not been collected or tested against trigger coverage.

5. **`_auto_remediate()` field scope is incomplete.** Only scans `steps` and `principles` for model name replacement. Needs to scan all text fields (`when_to_apply`, `example_application`, `description`, `principles`).
