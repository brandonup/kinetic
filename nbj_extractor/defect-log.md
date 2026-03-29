# Defect Log — Framework Extraction Pipeline

## DEFECT-001: The Moat Audit — Fabricated Steps

**Status:** FIXED
**Date identified:** 2026-03-22
**Date fixed:** 2026-03-22
**Severity:** High (fabricated content presented as author's voice in production)

### What happened

The Moat Audit framework (id: `the-moat-audit`, source post 182475814) contained 12 fabricated diagnostic questions in its `steps` array. These questions sounded plausible — competitive positioning, data moats, failure modes — but were not Nate's actual questions. The framework also carried `confidence: "low"` and a `_quality_note` acknowledging the fabrication.

### Nate's actual 12 questions (from the source post)

Organized across four sections:

1. **Constraints and drift:** Where do your constraints live — in the prompt, in code, or both? / What validates output before it ships to a user? / What happens when a requirement changes mid-workflow? / Is validation re-applied after each transformation, or only at the end?
2. **Logging and traceability:** What gets logged? Failures, retries, diffs, token counts, latency? / When something breaks, can you trace it back to the specific step that caused it?
3. **Determinism and routing:** What's deterministic in your system versus what's left to the model's discretion? / How do you handle the head of the distribution vs. the tail? / What's your repair logic when validation fails?
4. **Review and boundaries:** Who reviews outputs before they reach users? / What's frozen vs. variable? / If I asked you to change the tone of the output right now, what breaks?

### Root cause

`format_post_for_prompt()` in `extract_frameworks.py` truncated `sections_text` at 2,000 characters. The source post has 14 sections; the actual 12 questions live in the last 4. The truncation caught only the first 2-3 sections (promotional content), so the LLM never saw the questions. Pass 1 produced meta-reference steps ("Work through all 12 questions...") and a later quality pass fabricated specific questions to fill the gap.

### Fix applied

**In `frameworks_index.json`:**
- Replaced fabricated 12 questions with Nate's actual 12 questions from the source post, organized by his four section headings
- Removed `_quality_note` field
- Updated `confidence` from `"low"` to `"high"`

**In `extract_frameworks.py` (three pipeline changes to prevent recurrence):**

1. **Change 1 — Priority-based section selection** (`format_post_for_prompt`): Replaced flat `sections_text[:2000]` truncation with a scoring system that prioritizes sections containing structural markers (question marks, numbered items, keywords like "audit", "diagnostic", "question"). Sections are ranked by score, selected within a 4,000-char budget, then reassembled in original order. This ensures framework substance isn't cut off when it appears late in a long post.

2. **Change 2 — Incompleteness flag in Pass 1 prompt** (`PASS1_SYSTEM`): Added instructions telling the model that if a post references specific content ("12 questions", "5 rules") but that content isn't visible in the excerpt, it must set `steps` to `[]`, add `"extraction_incomplete": true`, and describe what's missing. Prevents fabrication at the source.

3. **Change 3 — Meta-reference step validator** (`run_pass2`, after dedup): Added a regex-based detector that scans steps for meta-reference patterns ("work through all 12 questions", "follow the 7 steps", etc.). Matching frameworks get a `review_flag` with `defect: "meta_reference_steps"` so they're caught before hitting production.

### Defense in depth

These three changes form layers: Change 1 prevents most truncation. Change 2 catches cases where truncation still happens. Change 3 catches anything that slips through both.

---

## DEFECT-002: Five Strategic Questions for AI Hype Events — Incomplete Steps

**Status:** IDENTIFIED
**Date identified:** 2026-03-22
**Severity:** High (broken reasoning at runtime)
**Framework ID:** `five-strategic-questions-for-ai-hype-events`
**Failure mode:** Broken reasoning

### What happened

Step 4 literally says: *"Ask questions 4 and 5 (implied but not fully shown in the excerpt)"*. The framework claims to be a 5-question tool but only contains 3 actual questions. At runtime, the agent receives an incomplete framework and either stalls, invents questions 4 and 5, or awkwardly skips them.

### Root cause

Same truncation issue as DEFECT-001 — the source post content was cut off before questions 4 and 5 could be extracted. The extractor acknowledged the gap inline rather than flagging it.

### Recommended fix

Backfill questions 4 and 5 from the source post. If they can't be found, restructure as a 3-question framework matching what was actually extracted. The pipeline changes from DEFECT-001 (incompleteness flag, meta-reference validator) should prevent this class of issue going forward.

---

## DEFECT-003: Token Management Audit — Fabricated Dimension Names

**Status:** IDENTIFIED
**Date identified:** 2026-03-22
**Severity:** High (fabricated content presented as author's voice)
**Framework ID:** `token-management-audit`
**Failure mode:** Wrong voice

### What happened

The framework's `_quality_note` explicitly confirms: the five dimension names (Intelligence Retention, Reuse Leverage, Capability Compounding, Spend Concentration, Measurement Maturity) were *inferred* by the extractor, not sourced from Nate. The framework carries `confidence: "low"` but no gate prevents it from being injected at runtime. The agent would confidently present fabricated framework components as Nate's proprietary thinking.

### Root cause

The source post references "five dimensions of intelligence spend" but the actual dimension names live in a linked prompt kit (promptkit.natebjones.com), which wasn't accessible to the extraction pipeline. The extractor fabricated plausible-sounding names.

### Recommended fix

Backfill the actual dimension names from the prompt kit. Until then, either gate injection on `confidence: "low"` or add a `review_flag` to prevent runtime use.

---

## DEFECT-004: Architecture of a Prompt / Universal Prompt Anatomy — Classifier Collision

**Status:** IDENTIFIED
**Date identified:** 2026-03-22
**Severity:** Medium (mismatch — user gets incomplete guidance)
**Framework IDs:** `the-architecture-of-a-prompt`, `universal-prompt-anatomy-context-role-task-constraints-examp`
**Failure mode:** Mismatch

### What happened

Two high-confidence prompt-structuring frameworks exist with heavily overlapping `when_to_apply` triggers:

- **Architecture of a Prompt** — 5 components: Context, Output, Interrogative, Constraints, Examples
- **Universal Prompt Anatomy** — 7 components: Context, Role, Task, Constraints, Examples, Output Spec, Fallback

A user asking "how do I structure my prompts" or "I keep getting vague output" would match both. The classifier picks whichever scores marginally higher, and the user misses the other framework's unique components (e.g., Fallback handling, Interrogative mode).

### Recommended fix

Either merge into a single canonical prompt structure framework, or sharpen `when_to_apply` to create non-overlapping routing: Architecture of a Prompt for beginners building their first prompt, Universal Prompt Anatomy for production system prompts.

---

## DEFECT-005: Tokenizable Data Tiers — Empty Steps

**Status:** IDENTIFIED
**Date identified:** 2026-03-22
**Severity:** Medium (broken reasoning — no diagnostic procedure)
**Framework ID:** `tokenizable-data-tiers`
**Failure mode:** Broken reasoning

### What happened

`steps` array is empty. The framework defines Tier A/B/C classifications in `principles` but provides no diagnostic procedure. At runtime, the agent receives tier definitions but no way to walk the user through classifying their specific data — it recites Tier A/B/C generically instead of running Nate's structured assessment.

### Recommended fix

Add steps that guide the user through: list data sources, apply the napkin test to each, classify into tiers, and sequence AI initiatives by tier readiness.

---

## DEFECT-006: The Narrow-Pipe Law — Empty Steps

**Status:** IDENTIFIED
**Date identified:** 2026-03-22
**Severity:** Medium (broken reasoning — no diagnostic procedure)
**Framework ID:** `the-narrow-pipe-law`
**Failure mode:** Broken reasoning

### What happened

`steps` array is empty. A user asking "our AI gives hedged, wishy-washy answers" gets the principle ("tighten the pipe") but no diagnostic procedure to identify *where* noise enters their pipeline or *what* to cut.

### Recommended fix

Add steps: audit the input pipeline for noise sources, identify what data the model doesn't need, strip inputs to the minimum viable context, and A/B test output quality before/after.

---

## DEFECT-007: Aquatic Problem Taxonomy — Empty Steps

**Status:** IDENTIFIED
**Date identified:** 2026-03-22
**Severity:** Medium (broken reasoning — no diagnostic flow)
**Framework ID:** `aquatic-problem-taxonomy`
**Failure mode:** Broken reasoning

### What happened

`steps` array is empty. Seven named problem types exist in `principles` (Goldfish, Eel, Tuna, Orca, Snow crab, Shark, Blue whale) but the agent has no diagnostic flow to classify which type the user faces. At runtime, it dumps all 7 definitions and asks the user to self-select — generic LLM behavior, not Nate's approach.

### Recommended fix

Add diagnostic steps that probe the user's situation with discriminating questions: "Is the answer different depending on unstated assumptions?" (Goldfish), "Do we not know the root cause?" (Eel), etc.

---

## DEFECT-008: Entropy-Based Model Routing — Hardcoded Model Names

**Status:** IDENTIFIED
**Date identified:** 2026-03-22
**Severity:** High (harmful/misleading — becomes actively wrong over time)
**Framework ID:** `entropy-based-model-routing`
**Failure mode:** Harmful or misleading

### What happened

Steps hardcode `"select Gemini 3"` and `"select ChatGPT 5.1"` as routing targets. Principles also reference these specific models. Within one model generation cycle, the agent will recommend obsolete models to users making real procurement and architecture decisions.

### Recommended fix

Replace hardcoded model names with capability profiles: "route to the model optimized for multimodal context compression" / "route to the model optimized for extended reasoning." Add a note that specific model recommendations should be validated against current releases.

---

## DEFECT-009: Document Pipeline / Writing Dev Stack — Hardcoded Model Names

**Status:** IDENTIFIED
**Date identified:** 2026-03-22
**Severity:** Medium (harmful/misleading — prescribes specific models that age out)
**Framework ID:** `document-pipeline-writing-dev-stack`
**Failure mode:** Harmful or misleading

### What happened

Principles hardcode specific models into fixed pipeline stages: o3 for drafting, Opus for review, Perplexity for fact-checking, Sonnet for polish. While the `steps` use better capability-profile language, the `principles` still name specific models that the agent would relay to users. The advice becomes wrong as models are updated or deprecated.

### Recommended fix

Replace model names in principles with capability requirements at each stage (reasoning depth, adversarial rigor, search-grounding, fluency) and let the user map current models to those requirements. The steps already model this pattern — bring principles in line.

---

## DEFECT-010: Workflow Routing by Visual Intensity — Hardcoded Model Names

**Status:** IDENTIFIED
**Date identified:** 2026-03-22
**Severity:** Medium (harmful/misleading — dated routing advice)
**Framework ID:** `workflow-routing-by-visual-intensity-and-context-type`
**Failure mode:** Harmful or misleading

### What happened

Steps reference routing to `"Gemini 3"` specifically and include a `"not yet"` list tied to specific model limitations at the time of writing. Principles also reference `"Gemini 3"` as the routing target for high-visual-intensity workflows. The agent gives dated routing advice that becomes actively wrong as model capabilities shift.

### Recommended fix

Replace model-specific routing with capability-profile routing (e.g., "route to your strongest multimodal model") and parameterize the "not yet" list as a diagnostic the user runs against current model capabilities rather than a static blocklist.

---

## DEFECT-011: Shopping Mode Classification — Classifier Magnet

**Status:** FIXED (removed)
**Date identified:** 2026-03-22
**Date fixed:** 2026-03-22
**Severity:** Medium (wrong framework injected at runtime)
**Framework ID:** `shopping-mode-classification-the-five-jobs-of-black-friday-s`
**Failure mode:** Classifier magnet / false positive

### What happened

A consumer shopping taxonomy ("Five Jobs of Black Friday Shoppers") with broad `when_to_apply` triggers about user segmentation and behavioral patterns. On a B2B strategy agent, any question about customer segmentation or behavioral analysis would match this framework, causing the agent to deliver consumer retail shopping advice instead of business strategy.

### Fix applied

Removed from `frameworks_index.json`.

---

## DEFECT-012: The Exhausted Person's Prompt — Literal Prompt Template

**Status:** FIXED (removed)
**Date identified:** 2026-03-22
**Date fixed:** 2026-03-22
**Severity:** High (agent recites template instead of reasoning)
**Framework ID:** `the-exhausted-person-s-prompt-ask-me-what-you-need-to-know`
**Failure mode:** Literal prompt template

### What happened

A meta-circular prompt template ("Ask Me What You Need to Know") where the steps are literally "paste this prompt into ChatGPT." The agent would recite the prompt template text to the user instead of applying any reasoning. No agent-applicable logic exists — it's instructions for a human to copy-paste.

### Fix applied

Removed from `frameworks_index.json`.

---

## DEFECT-013: Custom Instructions Decision Grid — Literal Prompt Template

**Status:** FIXED (removed)
**Date identified:** 2026-03-22
**Date fixed:** 2026-03-22
**Severity:** Medium (irrelevant UI tutorial)
**Framework ID:** `custom-instructions-decision-grid`
**Failure mode:** Literal prompt template

### What happened

A ChatGPT-specific settings UI tutorial. Steps describe navigating the ChatGPT custom instructions panel. Not transferable reasoning — the agent can't help users configure another product's UI, and the advice is platform-specific, not strategic.

### Fix applied

Removed from `frameworks_index.json`.

---

## DEFECT-014: JSON Prompt Translator Framework — Literal Prompt Template

**Status:** FIXED (removed)
**Date identified:** 2026-03-22
**Date fixed:** 2026-03-22
**Severity:** Medium (agent recites image-gen templates)
**Framework ID:** `json-prompt-translator-framework`
**Failure mode:** Literal prompt template

### What happened

Steps are image generation prompt templates (structured JSON for Midjourney/DALL-E). The agent would recite JSON prompt structures instead of reasoning about the user's strategy or workflow question. No overlap with the agent's actual domain.

### Fix applied

Removed from `frameworks_index.json`.

---

## DEFECT-015: Collapse Position Audit — Self-Assessment Trap

**Status:** FIXED (removed)
**Date identified:** 2026-03-22
**Date fixed:** 2026-03-22
**Severity:** Medium (vague, unactionable)
**Framework ID:** `collapse-position-audit`
**Failure mode:** Self-assessment trap

### What happened

Three vague self-assessment bullets with zero diagnostic logic. Steps ask the user to "reflect on" and "assess" their position with no discriminating questions, scoring criteria, or decision branches. The agent has nothing to reason with — it would produce generic self-help phrasing.

### Fix applied

Removed from `frameworks_index.json`.

---

## DEFECT-016: Accessibility Audit Framework — Literal Prompt Template

**Status:** FIXED (removed)
**Date identified:** 2026-03-22
**Date fixed:** 2026-03-22
**Severity:** Medium (agent recites prompts instead of reasoning)
**Framework ID:** `accessibility-audit-framework-four-prompt-decision-point-sys`
**Failure mode:** Literal prompt template

### What happened

Steps are literally "run this prompt" instructions. A four-prompt decision-point system where each step is a prompt to copy-paste into a different tool. The agent would recite the prompts to the user rather than applying any diagnostic reasoning about their accessibility situation.

### Fix applied

Removed from `frameworks_index.json`.

---

## DEFECT-017: Adversarial Investigation Framework — Literal Prompt Template (rewritten)

**Status:** FIXED (rewritten)
**Date identified:** 2026-03-22
**Date fixed:** 2026-03-22
**Severity:** High (agent recites 7 copy-paste prompts)
**Framework ID:** `adversarial-investigation-framework-fighting-institutional-p`
**Failure mode:** Literal prompt template

### What happened

Original steps were 7 copy-paste prompts for investigating institutional power structures. The agent would recite the prompt text instead of reasoning through the user's situation. The underlying framework concept (adversarial investigation methodology) was sound — the extraction just captured prompts instead of reasoning.

### Fix applied

Rewrote `steps` array to convert from prompt templates to diagnostic reasoning steps the agent can apply: identify the institution, map information asymmetries, find structural leverage points, assess disclosure risks, etc.

---

## DEFECT-018: Document Pipeline / Writing Dev Stack — Literal Prompt Template (rewritten)

**Status:** FIXED (rewritten)
**Date identified:** 2026-03-22
**Date fixed:** 2026-03-22
**Severity:** Medium (model-specific prescriptions that age out)
**Framework ID:** `document-pipeline-writing-dev-stack`
**Failure mode:** Literal prompt template

### What happened

Original steps prescribed specific models at each pipeline stage (o3 for drafting, Opus for review, Perplexity for fact-checking, Sonnet for polish). The agent would relay outdated model advice as authoritative recommendations.

### Fix applied

Rewrote `steps` to use capability-profile language: "use a model optimized for extended reasoning" instead of "use o3." The reasoning structure (multi-stage document pipeline) was preserved; only the model-specific prescriptions were abstracted. (Note: `principles` still contain hardcoded model names — see DEFECT-009.)

---

## DEFECT-019: Four-Layer Eval Architecture — Process Spec Not Reasoning Tool (rewritten)

**Status:** FIXED (rewritten)
**Date identified:** 2026-03-22
**Date fixed:** 2026-03-22
**Severity:** Medium (month-by-month build plan, not diagnostic reasoning)
**Framework ID:** `four-layer-eval-architecture`
**Failure mode:** Process spec, not reasoning tool

### What happened

Original steps described a month-by-month build plan for constructing a four-layer evaluation system. The agent can't execute a multi-month project — it needs to reason about the user's current eval gaps in conversation.

### Fix applied

Rewrote `steps` to diagnostic reasoning: identify which of the four layers the user's current system covers, find which failure modes aren't caught, determine the highest-leverage missing layer, and recommend the architectural fix.

---

## DEFECT-020: Frontier Operations — No Agent-Applicable Reasoning

**Status:** IDENTIFIED (flagged for manual review)
**Date identified:** 2026-03-22
**Severity:** Medium (broken reasoning — no diagnostic procedure)
**Framework ID:** `frontier-operations`
**Failure mode:** Broken reasoning

### What happened

`steps` array is empty. Five operations are named in `principles` (boundary sensing, seam design, failure model maintenance, capability forecasting, leverage calibration) but the agent has no procedure to diagnose which operations a user or team needs to develop. At runtime, the agent recites the five operation names without reasoning through the user's specific situation.

### Recommended fix

Add steps that turn each operation into a diagnostic question: "Where is the boundary between AI-reliable and human-required work in your current workflow?" (boundary sensing), "What breaks when AI capability shifts?" (failure model maintenance), etc.

---

## DEFECT-021: The 201 Gap Framework — No Agent-Applicable Reasoning

**Status:** IDENTIFIED (flagged for manual review)
**Date identified:** 2026-03-22
**Severity:** Medium (broken reasoning — no diagnostic procedure)
**Framework ID:** `the-201-gap-framework`
**Failure mode:** Broken reasoning

### What happened

`steps` array is empty. Six meta-skills are named in `principles` (context assembly, quality judgment, task decomposition, iterative refinement, workflow integration, frontier recognition) but the agent has no diagnostic logic to assess which ones a user or team is missing. At runtime, the agent lists all six and tells the user to "work on" them generically.

### Recommended fix

Add diagnostic steps that probe for each meta-skill gap: "When you use AI, do you provide context about your goals or just the task?" (context assembly), "Can you tell when AI output is 80% right vs. 95% right?" (quality judgment), etc.

---

## DEFECT-022: The Finishing Framework — Process Spec Not Reasoning Tool

**Status:** PARTIALLY FIXED
**Date identified:** 2026-03-22
**Date partially fixed:** 2026-03-21
**Severity:** Medium (steps describe a project plan, not conversational reasoning)
**Framework ID:** `the-finishing-framework`
**Failure mode:** Process spec, not reasoning tool + tool-specific config embedded

### What happened

Steps describe running a 20-task diagnostic bank across five failure-mode buckets, scoring on 7 axes (0-4 per axis), implementing artifact spines (PLAN.md, TODO.md, etc.), and adding LangGraph production primitives. This is a multi-week engineering project plan. The agent cannot run head-to-head benchmarks or implement LangGraph primitives in conversation.

Additionally, the original framework had 10 steps. Steps 7–10 (Part 3) contained Claude Code-specific configuration: `set up CLAUDE.md via /init`, `configure permissions across four modes`, `build team-scale workflows via .claude/commands with $ARGUMENTS support`, `follow the explore→plan→code→commit workflow discipline`. These are tool-specific CLI commands inappropriate for an advisory agent.

### Partial fix applied (2026-03-21)

Part 3 (steps 7–10) removed — tool-specific config eliminated. Framework trimmed from 10 steps to 6. Parts 1–2 retained (7-axis diagnostic, comparison protocol, architecture patterns).

### Remaining issue

The 6 remaining steps are still a process spec. Steps 5–6 ("implement the artifact spine," "add LangGraph production primitives") describe infrastructure build-outs the agent cannot perform in conversation.

### Recommended fix (remaining)

Rewrite steps to focus on what the agent *can* do: diagnose WHY an agent system fails to finish by probing which of the 7 axes is weakest, identify whether the bottleneck is harness-level or model-level, and recommend the architectural pattern (from Anthropic's composable patterns) most likely to address the specific failure mode.

---

## DEFECT-023: The Manifold Probe — Process Spec Not Reasoning Tool

**Status:** IDENTIFIED (flagged for manual review)
**Date identified:** 2026-03-22
**Severity:** Medium (steps include actions the agent cannot execute)
**Framework ID:** `the-manifold-probe`
**Failure mode:** Process spec, not reasoning tool

### What happened

Steps describe a four-phase protocol: Interview, Design, Run, Score. Phase 3 ("Run — execute scenarios head-to-head across the models being compared") requires actually running model comparisons, which the agent cannot do. The framework concept is sound, but the steps include execution phases the agent can't perform.

### Recommended fix

Rewrite steps to focus on phases the agent *can* help with: designing the right evaluation (defining failure costs, identifying constraint-shift scenarios, building scoring rubrics from user success criteria) while clearly framing Phase 3 as something the user executes with the agent's designed test plan.

---

## DEFECT-024: Locus of Control Circle Exercise — Self-Assessment Trap

**Status:** FIXED (rewritten)
**Date identified:** 2026-03-21
**Date fixed:** 2026-03-21
**Severity:** Medium (agent recites pen-and-paper instructions)
**Framework ID:** `locus-of-control-circle-exercise`
**Failure mode:** Self-assessment trap

### What happened

Original 4 steps were physical self-assessment instructions: "Draw a circle on a piece of paper," "Place each element inside or outside the circle." The agent cannot observe the user drawing, has no way to facilitate the exercise, and would recite the instructions as a to-do list.

### Fix applied

Rewrote to 6 conversational diagnostic steps: ask for a stuck situation, have user name blocking factors, probe for agency ("what could you do to influence that?"), identify the pattern (contracted/calibrated/expansive control circle), surface the finding, and work through one element the user placed outside their control.

---

## DEFECT-025: AI Fluency Assessment Framework — Self-Assessment Trap

**Status:** FIXED (rewritten)
**Date identified:** 2026-03-21
**Date fixed:** 2026-03-21
**Severity:** Medium (agent recites scoring rubric instead of assessing)
**Framework ID:** `ai-fluency-assessment-framework`
**Failure mode:** Self-assessment trap

### What happened

All 8 original steps were "Score yourself on X" directives. The agent became a rubric dispenser — reading out scoring criteria and asking the user to self-rate. No diagnostic reasoning, no interview, no agent-derived insight.

### Fix applied

Rewrote to 8 interview steps: (1) ask permission before starting, (2–6) agent asks a concrete question per dimension and scores from the response (Prompt Mastery 40%, Technical Understanding 15%, Practical Application 20%, Critical Evaluation 15%, Workflow Design 10%), (7) calculate weighted composite, (8) present score with single prioritized improvement. Agent now derives the score instead of asking the user to self-assign one.

---

## DEFECT-026: Three Kinds of Reading — Empty Framework Shell

**Status:** FIXED (removed)
**Date identified:** 2026-03-21
**Date fixed:** 2026-03-21
**Severity:** Medium (agent has nothing to apply)
**Framework ID:** `three-kinds-of-reading`
**Failure mode:** Broken reasoning

### What happened

Empty `steps: []`, empty `example_application: ""`, empty `source_posts: []`. Three reading modes named but no classification criteria, no diagnostic logic, no content for the agent to work with. Injecting it would produce a response indistinguishable from the agent operating without a framework.

### Fix applied

Removed from `frameworks_index.json`.

---

## DEFECT-027: Nine Principles of Business Writing with AI — Empty Framework Shell

**Status:** FIXED (removed)
**Date identified:** 2026-03-21
**Date fixed:** 2026-03-21
**Severity:** Medium (claimed content never extracted)
**Framework ID:** `nine-principles-of-business-writing-with-ai`
**Failure mode:** Broken reasoning

### What happened

Empty `steps: []`, empty `example_application: ""`, empty `source_posts: []`. The `principles` field contained meta-observations *about* nine principles ("each principle addresses...") but never listed the actual nine principles. The agent would reference a framework that doesn't contain its own content.

### Fix applied

Removed from `frameworks_index.json`.

---

## DEFECT-028: Six Axes of Hard Difficulty — Referenced Content Never Extracted

**Status:** FIXED (backfilled from source)
**Date identified:** 2026-03-21
**Date fixed:** 2026-03-21
**Severity:** High (framework's core content missing)
**Framework ID:** `six-axes-of-hard-difficulty-framework`
**Failure mode:** Broken reasoning

### What happened

Steps said "decompose the task across all six difficulty axes" but the six axes were never named or defined. The agent would instruct users to decompose across unnamed dimensions.

### Fix applied

Rewrote 6 steps with verified axis names from source post id 188837484: **(1) Reasoning, (2) Effort, (3) Coordination, (4) Emotional Intelligence, (5) Domain Expertise, (6) Ambiguity.** Each axis includes definitions, examples, and automation timelines from the source post. Confidence raised to `high`.

---

## DEFECT-029: Magnifying Glass vs Tiger Team — Empty Steps

**Status:** FIXED (diagnostic steps added)
**Date identified:** 2026-03-21
**Date fixed:** 2026-03-21
**Severity:** Medium (rich principles but no diagnostic flow)
**Framework ID:** `magnifying-glass-vs-tiger-team-company`
**Failure mode:** Broken reasoning

### What happened

`steps: []` despite rich principles clearly defining the two organizational archetypes. The agent would dump both archetype descriptions and ask the user to self-select rather than diagnosing which one applies.

### Fix applied

Added 7 diagnostic steps: 4 probing questions (AI budget concentration, crisis response pattern, time-on-legibility vs. time-on-work, metric gaming behavior), classification, and archetype-specific advice for each path.

---

## DEFECT-030: Ten Components of Good Judgement — Empty Steps

**Status:** FIXED (diagnostic steps added)
**Date identified:** 2026-03-21
**Date fixed:** 2026-03-21
**Severity:** Medium (rich principles but no diagnostic flow)
**Framework ID:** `ten-components-of-good-judgement`
**Failure mode:** Broken reasoning

### What happened

`steps: []` despite all 10 components being fully enumerated in the `principles` array. The agent would list all 10 components generically instead of diagnosing the user's weak spots. All 10 component names verified against the source post's numbered list.

### Fix applied

Added 5 diagnostic steps: ask for a recent decision, probe against each of the 10 components, identify the 2–3 weakest, give targeted development advice, and reframe judgment as 10 distinct capabilities with 1–2 to deliberately practice.

---

## DEFECT-031: LLM Decision Safety Rules — Empty Steps

**Status:** FIXED (diagnostic steps added)
**Date identified:** 2026-03-21
**Date fixed:** 2026-03-21
**Severity:** Medium (rich principles but no application flow)
**Framework ID:** `llm-decision-safety-rules`
**Failure mode:** Broken reasoning

### What happened

`steps: []` despite all 7 rules being fully enumerated in the `principles` array. The agent would recite the rules as tips rather than actively interrogating the user's decision process against each one. All 7 rule names verified against the source post's numbered list.

### Fix applied

Added 9 diagnostic steps: ask about the decision and AI tools consulted, then apply each of the 7 rules sequentially (probing the user's process against each), and synthesize a verdict on whether the decision process is sound.

---

## Patterns

Six structural patterns account for all 31 defects in this log.

**Pattern 1: Truncation-caused incomplete extraction** (DEFECT-001, DEFECT-002, DEFECT-005, DEFECT-006, DEFECT-007, DEFECT-020, DEFECT-021, DEFECT-026, DEFECT-027, DEFECT-028, DEFECT-029, DEFECT-030, DEFECT-031)
The extraction pipeline's flat character truncation cut off source post content before framework substance was reached. Manifests as empty `steps` arrays, meta-reference steps ("work through all 12 questions"), inline gaps ("implied but not fully shown in the excerpt"), or empty shells where the entire framework is a name with no content. The pipeline changes in DEFECT-001 (priority-based section selection, incompleteness flag, meta-reference validator) address the root cause for future extractions. DEFECT-026 through DEFECT-031 represent a batch of frameworks where principles were extracted but steps were lost — the extractor captured the "what is this framework" framing but not the "how to apply it" operational detail. These have been fixed by backfilling steps from source posts or deriving diagnostic flows from the existing principles.

**Pattern 2: Fabricated content from inaccessible source material** (DEFECT-001, DEFECT-003, DEFECT-028)
When the source post referenced content living behind a link (a prompt kit, a linked guide), the extractor couldn't access it and either fabricated plausible-sounding specifics or gestured at them with meta-references. The result is framework components presented in Nate's voice that he never wrote. DEFECT-028 (Six Axes) was a variant where the axis names existed in the source post but were lost to truncation — backfilled with verified names. Fix requires accessing the original linked material and backfilling. Until then, frameworks with `confidence: "low"` and `_quality_note` fields should be gated from runtime injection.

**Pattern 3: Hardcoded model names** (DEFECT-008, DEFECT-009, DEFECT-010, DEFECT-018)
Frameworks name specific models (Gemini 3, ChatGPT 5.1, o3, Opus, Perplexity, Sonnet) as prescriptive recommendations rather than using capability-profile language. These become harmful advice within one model generation cycle. The fix is consistent: replace model names with capability descriptions and let users map current models to those descriptions. This is a content authoring problem, not a pipeline problem — it should be addressed in the source posts or as a post-processing rule in the extraction pipeline.

**Pattern 4: Literal prompt templates masquerading as frameworks** (DEFECT-012, DEFECT-013, DEFECT-014, DEFECT-016, DEFECT-017, DEFECT-018)
The extraction pipeline treated copy-paste prompt templates, UI tutorials, and image-generation JSON structures as if they were reasoning frameworks. At runtime, the agent recites the template text verbatim instead of applying any diagnostic logic. This is the single most common defect class (6 of 31). The root cause is that the extractor has no filter for "is this a reasoning framework vs. a prompt to copy-paste?" — it treats any structured content from a thought leader post as extractable. **Recommended pipeline fix:** Add a post-extraction classifier that checks whether `steps` contain imperative reasoning ("identify," "assess," "determine") vs. template language ("paste this prompt," "use this JSON," "navigate to settings"). Flag the latter for review.

**Pattern 5: Process specs and project plans instead of conversational reasoning** (DEFECT-019, DEFECT-022, DEFECT-023)
Frameworks whose steps describe multi-week execution plans, head-to-head benchmarking protocols, or infrastructure build-outs that the agent cannot perform in a conversation. The underlying frameworks are conceptually sound — the problem is that the extractor captured the "how to do this yourself" version instead of the "how to think about this" version. DEFECT-022 also exhibited a sub-variant: **tool-specific config embedded in otherwise valid frameworks** — Claude Code CLI commands (`CLAUDE.md`, `/init`, `$ARGUMENTS`, `.claude/commands`) baked into Part 3 of The Finishing Framework. The tool-specific steps were removed; the process-spec steps remain. **Recommended pipeline fix:** Add a feasibility filter that checks whether steps require actions outside the agent's capability (running benchmarks, deploying code, conducting month-long evaluations). Also scan for tool-specific command syntax (`.claude/`, `$ARGUMENTS`, `/init`, specific CLI flags) and flag for removal. Steps that fail either filter should be rewritten to the diagnostic/advisory version the agent can actually deliver.

**Pattern 6: Self-assessment traps** (DEFECT-024, DEFECT-025)
Steps are instructions the *user* executes on themselves — "Score yourself on X," "Draw a circle," "Rate yourself 1–10." The agent becomes a rubric dispenser rather than an assessor. Distinct from Pattern 4 (prompt templates) because the content is a legitimate assessment framework, just captured in the wrong modality. The extractor preserved the self-administered version instead of converting to an agent-administered version. **Recommended pipeline fix:** Scan steps for self-assessment language ("score yourself," "rate yourself," "draw a," "on a piece of paper," "assess where you"). Flag frameworks where ≥50% of steps are second-person self-directed. The fix pattern is consistent: convert to an agent-interview format where the agent asks questions and derives scores from responses.
