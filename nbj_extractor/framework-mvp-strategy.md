# Framework Injection: MVP Strategy

## The Decision

Three recommendation documents propose overlapping but sometimes contradictory changes to the framework schema, extraction pipeline, and content authoring approach. This document synthesizes them into a single actionable strategy for the MVP, grounded in the JTBD and constrained by the defect patterns already observed.

---

## Where All Three Agree (Adopt Without Debate)

These points appear in every document. They're settled.

**The uniform steps/principles schema is wrong.** A distinction, a taxonomy, and a diagnostic procedure are different cognitive tools. Forcing all of them into `steps[]` + `principles[]` produces the exact defect patterns logged: fabricated steps, recited templates, generic list-dumps. The schema must be type-aware.

**Triggers must discriminate, not just match.** Writing triggers in isolation produces 16 frameworks that all fire on "AI adoption" queries. Triggers need to encode *why this framework and not its siblings.* This requires a cluster-aware pass where triggers are written with the competition visible.

**Content must cause reasoning, not recitation.** The agent should think *through* the framework, not *about* it. This means writing scaffold content as declarative assertions (Doc 3's "Mode 3"), not as instructions to the LLM or reference material about the framework.

---

## Where They Diverge (And What to Do)

### How many types?

| Doc | Types proposed |
|-----|---------------|
| Doc 1 (Design Recs) | 8: distinction, taxonomy, diagnostic, reframe, decision_tree, failure_modes, evaluation_criteria, mental_model |
| Doc 2 (Quality Recs) | 3: conceptual_model, diagnostic_procedure, decision_tool |
| Doc 3 (Schema Design) | 9: distinction, taxonomy, diagnostic, reframe, decision_heuristic, failure_catalog, matrix, evaluation_criteria, procedure |

**Decision: Use 7 types.** Doc 2's three meta-categories are too coarse — they don't give the extraction pipeline enough signal to generate the right scaffold shape. Doc 3's nine are the most precise, but `matrix` can be absorbed into `taxonomy` (a matrix is a multi-axis taxonomy), and `decision_heuristic` maps cleanly to `reframe` in practice (both are "the conventional view is X, but actually Y"). Final set:

| Type | What it is | Scaffold shape |
|------|-----------|---------------|
| `distinction` | Two+ things people conflate | Sides with signals, discriminating question, so-what |
| `taxonomy` | Classification system (including matrices) | Categories with diagnostic cues and implications |
| `diagnostic` | Branching questions that produce a verdict | Entry question, branches/conditions, terminal states |
| `reframe` | Challenge to conventional wisdom | Conventional view, reframe, argument, when conventional is right |
| `failure_catalog` | Enumerated failure modes with signals | Modes with patterns, early warnings, corrections |
| `evaluation_criteria` | Scoring rubric or assessment dimensions | Criteria with good/bad indicators, overall heuristic |
| `procedure` | Sequential steps with defined outputs | Steps with actions, common mistakes, done-state |

### Separate routing from injection, or one object?

Doc 1 keeps everything in one object. Doc 3 proposes a 3-layer architecture where routing fields are stripped before injection to save tokens.

**Decision: Adopt Doc 3's 3-layer architecture, but store as one object.** The requirements say cost and time are not an issue, but prompt bloating risk IS a concern. The simplest implementation: store one JSON object per framework, but at injection time, strip routing fields and meta fields. The classifier sees the full object; the LLM receives only scaffold + guidance. This is a runtime concern, not a schema concern — no need for two separate files.

### Token budget for injection payload

Doc 3 targets ~400 tokens. Doc 1 is richer (no explicit target). Requirements say no truncation and cost isn't an issue.

**Decision: Target 500-800 tokens for scaffold + guidance (the injection payload).** Opus 4.6 has a 200K context window. With a system prompt (~2K), RAG chunks (~3-5K), and conversation history, there's ample room. But Doc 3 is right that bloated injections dilute signal — the agent has to figure out what to prioritize. 500-800 tokens is generous enough for full scaffold content while staying lean enough that the framework doesn't dominate the prompt. Routing fields add zero runtime cost since they're stripped before injection.

### `core_question` for routing?

Doc 3 proposes `routing.core_question` — "the single underlying question this contribution answers." Docs 1 and 2 don't mention it.

**Decision: Add it.** This is the highest-leverage single addition for routing accuracy. Users don't ask for frameworks by name. They express a problem. `core_question` bridges that gap and gives the classifier a semantic anchor that's more stable than individual triggers. It's one field, one sentence, no cost.

### Voice injection: `nate_would_say` vs. `guidance` vs. nothing?

Doc 1 proposes `nate_would_say` (sharp voice line). Doc 3 proposes `guidance` (behavioral nudge to the agent). Doc 2 doesn't address it.

**Decision: Both, as separate fields.** They serve different purposes. `nate_would_say` gives the agent Nate's *stance* — the sharp, opinionated take that makes the response sound like Nate, not a consultant. `guidance` tells the agent what *move* to make — "listen for X, probe Y, don't just label." One is voice, the other is behavior. Both are 1-2 sentences. Together they add ~50-80 tokens.

### Kill `example_application`?

Doc 1 says cut it. Doc 3 doesn't include it. The current schema has it.

**Decision: Cut it from the injection payload.** A well-written scaffold with the right type-specific shape IS the example — the `so_what`, `implication`, and `discriminating_question` fields show the agent how to apply the framework. A separate example_application is redundant with good scaffold content and wastes tokens. Keep it in the extraction pipeline output for human reference, but strip it at injection time.

### Cluster-aware trigger refinement?

Doc 2 proposes a post-enrichment pass that groups frameworks by category, shows the LLM all triggers in a cluster, and asks it to rewrite for non-overlap.

**Decision: Add it as a pipeline step in Pass 2, after enrichment.** This directly addresses DEFECT-004 (classifier collision between two prompt-structuring frameworks). It's the only proposed mechanism that systematically prevents trigger overlap across the full index. Implementation: group by category, send each cluster to the LLM with all triggers visible, rewrite for mutual exclusivity.

### Anti-triggers / `not_when`?

Doc 1 proposes a `not_when` field. Doc 3 proposes `routing.anti_triggers`.

**Decision: Add `anti_triggers` to the routing layer, but only for collision pairs identified in testing.** Don't generate these upfront for every framework — that's make-work. Add them surgically when two frameworks keep firing on each other's queries. This is a tuning mechanism, not a launch requirement.

---

## The MVP Schema

```json
{
  "id": "middleware-trap-diagnostic",
  "name": "Middleware Trap Diagnostic",
  "type": "diagnostic",
  "confidence": "high",

  "routing": {
    "core_question": "Is this AI company building a durable product or renting a position in someone else's stack?",
    "triggers": [
      "My AI product depends on OpenAI's API and I'm worried they'll build what we do",
      "We're evaluating an AI startup for investment and need to know if the moat is real",
      "Our board is asking whether AWS could just ship our product as a feature"
    ],
    "anti_triggers": []
  },

  "scaffold": {
    "entry_question": "What happens to your product if your primary model provider ships your core feature tomorrow?",
    "branches": [
      {
        "condition": "Nothing survives — the product is orchestration on top of someone else's model",
        "then": "This is middleware. Good execution on the wrong layer doesn't create durable advantage. The product has a demo, not a business."
      },
      {
        "condition": "Proprietary data, workflow integration, or domain context survives",
        "then": "There may be a real business here. Assess whether the surviving assets create switching costs or are just execution speed that a well-funded competitor can replicate."
      }
    ],
    "terminal_states": [
      {
        "label": "Rented position",
        "prescription": "Pivot to acquiring defensible assets — proprietary data, deep workflow integration, or regulatory moats. Stop investing in model-layer differentiation."
      },
      {
        "label": "Durable position",
        "prescription": "Deepen the moat. The model layer is commoditizing — double down on what survives provider consolidation."
      }
    ]
  },

  "nate_would_say": "If your entire business disappears when OpenAI ships a new feature, you don't have a business — you have a demo. Stop polishing the demo and start building something that survives.",

  "guidance": "Probe whether the user's claimed moat is actually model-layer execution speed disguised as defensibility. Ask the entry question directly — most founders realize mid-answer that their 'unique value' is orchestration.",

  "source_posts": [
    {
      "id": "189945797",
      "title": "Most AI companies are renting their position.",
      "date": "2026-03-19"
    }
  ],

  "meta": {
    "category": "strategy",
    "origin": "extracted",
    "extraction_date": "2026-03-22",
    "related_frameworks": ["infrastructure-position-diagnostic", "the-moat-audit"]
  }
}
```

### What's injected at runtime (scaffold + nate_would_say + guidance)

The classifier sees the full object. The agent receives only:

```json
{
  "name": "Middleware Trap Diagnostic",
  "type": "diagnostic",
  "scaffold": { ... },
  "nate_would_say": "...",
  "guidance": "..."
}
```

Everything else — routing, source_posts, meta — is stripped. Estimated injection payload: ~400-600 tokens for this example. Room for richer scaffolds on more complex frameworks.

---

## What Changes in the Extraction Pipeline

The existing `extract_frameworks.py` pipeline changes we've already made (quality validators, quarantine, auto-remediation, no truncation) all carry forward. The additional changes for the new schema:

### Pass 1 Changes

**Update `PASS1_SYSTEM` and `PASS1_USER` prompts** to extract `type` alongside the existing fields. The extraction model classifies each framework into one of the 7 types based on the source content. This replaces the current instruction to extract `steps` and `principles` uniformly — instead, ask for the type and let that determine what content to extract:

- For distinctions: extract the two sides, signals, and the discriminating question
- For taxonomies: extract categories with diagnostic cues
- For diagnostics: extract questions/branches and terminal states
- For all types: extract a sharp 1-2 sentence `the_move` (replaces `description`)

### Pass 2 Changes

**Replace the uniform enrichment prompt** (`PASS2_ENRICH_SYSTEM`) with type-aware enrichment. The enrichment model receives the type and generates:

- `scaffold` content in the correct shape for that type (using Mode 3 authoring — declarative assertions, not instructions or reference material)
- `nate_would_say` — the sharp, opinionated voice line
- `guidance` — the behavioral nudge for the agent
- `routing.core_question` — the underlying question this framework answers
- Rewritten `when_to_apply` triggers (same as current)

**Add a cluster-aware trigger refinement step** after all frameworks are enriched. Group by category, show all triggers in each cluster, rewrite for non-overlap.

### Post-Processing

All existing validators carry forward:

- Quality validators (meta-reference, template, process-spec, self-assessment, model names)
- Auto-remediation (model name replacement)
- Quarantine (flagged frameworks excluded from production)
- Output validation (required fields, unique IDs, non-empty checks)
- Confidence gate (low = never injected, medium = tiebreaker penalty)

**Update output validation** `_REQUIRED_FIELDS` to reflect the new schema: `type`, `scaffold`, `guidance`, `nate_would_say`, `routing` replace `steps`, `principles`, `description`, `example_application`.

---

## How This Prevents the Six Defect Patterns

| Pattern | How the current pipeline handles it | How the new schema adds protection |
|---------|------------------------------------|------------------------------------|
| 1. Truncation-caused incomplete extraction | Full content sent (no truncation), extraction_incomplete flag, meta-reference validator | Type-specific scaffold shapes make empty/vague content more obvious — a distinction with no `side_a` is visibly broken in a way that empty `steps[]` wasn't |
| 2. Fabricated content | Incompleteness flag, quarantine | `scaffold` fields are type-constrained — harder to fabricate a plausible `discriminating_question` or `terminal_states` than to fabricate generic steps |
| 3. Hardcoded model names | Auto-remediation regex replacement, Pass 1 prompt instruction | Unchanged — already handled |
| 4. Literal prompt templates | Template classifier validator, Pass 1 prompt instruction | Type system prevents it structurally — a prompt template doesn't fit any of the 7 types. If it can't be classified as a distinction, taxonomy, diagnostic, etc., it doesn't enter the index |
| 5. Process specs | Feasibility filter, temporal/tool-specific validators | `procedure` type explicitly requires agent-executable steps with `common_mistake` per step. Build plans fail the "can the agent do this in conversation?" test at type classification |
| 6. Self-assessment traps | Self-assessment detector | Type-specific scaffolds are agent-facing by design — a `diagnostic` has `entry_question` the agent asks, not "score yourself." The modality conversion is built into the schema |

---

## Migration Path

**Phase 1 — Schema + Pipeline (1-2 days).** Update `extract_frameworks.py` with the new schema, type-aware prompts, and cluster-aware trigger refinement. Don't touch the existing `frameworks_index.json` yet.

**Phase 2 — Re-extract high-confidence frameworks (1 day).** Run the updated pipeline on the full corpus. The 66 high-confidence frameworks should extract cleanly with the new type-specific scaffolds. Compare output against the current index to verify quality improvement.

**Phase 3 — Triage medium-confidence (half day).** Review the ~39 medium-confidence extractions. Some will convert cleanly to the new schema, some will reveal they're duplicates or too thin. Merge or quarantine.

**Phase 4 — Runtime integration (half day).** Add injection-time stripping (remove routing + meta fields). Wire confidence as a hard gate in the classifier. Ship.

**Total: ~3-4 days to production.**

---

## What's Explicitly Out of Scope for MVP

- Semantic trigger overlap detection (nice-to-have tuning, not launch-blocking)
- Multi-framework injection (always inject exactly one)
- Dynamic scaffold compression (fixed schema, no runtime token optimization)
- `anti_triggers` population (add surgically post-launch based on collision data)
- Framework versioning (no need until the library is actively maintained)

---

## Current State vs. This Strategy (2026-03-23)

**This strategy document has NOT been executed.** The extraction pipeline completed 4 of 5 batches using the intermediate schema (`description` + `principles` + `steps` + `example_application` + `when_to_apply`). Zero frameworks have been migrated to the MVP strategy schema described above.

### What exists

- **376 production frameworks** in the intermediate schema (420 of 505 posts scanned, 85 remaining)
- Type-aware enrichment with Mode 3 content in `example_application`
- `core_question` generated during enrichment but stripped at output time
- 7-type classification implemented and working
- Quality validators, quarantine, auto-remediation all operational

### What does NOT exist

- `scaffold` field (type-specific structured content) — not generated
- `nate_would_say` field — not generated
- `guidance` field — not generated
- `routing.core_question` in the output — generated but stripped by `_clean_for_output()`
- Cluster-aware trigger refinement — not run
- Nate B. Jones system prompt — not authored
- Injection payload token profiling — not done
- Representative user query set for eval — not collected

### Open Decision

**Schema migration decision is pending.** Options:
1. **Ship with intermediate schema** — current runtime assembly (`description` + `principles` + `steps` + `example_application`) works. Evaluate effectiveness first, migrate if needed.
2. **Migrate to MVP strategy schema before launch** — re-run enrichment with new prompts to generate `scaffold`, `nate_would_say`, `guidance`. ~3-4 days per the migration path above.
3. **Hybrid** — keep intermediate schema for extraction/storage, add a runtime transformation layer that reshapes the injection payload without re-extracting.

This decision should be informed by Monica's evaluation of whether the current injection shape is cognitively effective enough to ship.
