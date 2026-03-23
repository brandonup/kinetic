# Framework Schema Recommendations

**Status:** Draft
**Date:** 2026-03-22
**Author:** Jared (Product)
**Source:** Third-party consultant write-up on knowledge injection schema design, reviewed against Kinetic's locked framework architecture.

---

## Context

A third-party consultant delivered a write-up proposing a three-layer framework schema (routing layer, type-specific scaffold layer, guidance field) optimized for LLM reasoning quality at injection time. After review, five recommendations were identified that improve Kinetic's framework feature without introducing unnecessary structural complexity.

These recommendations do not adopt the consultant's full type-specific scaffold architecture. They pull the highest-leverage ideas — authoring voice, runtime payload trimming, new fields, updated upload format, and re-extraction — into Kinetic's existing schema and pipeline.

---

## Recommendation 1: Rework the Extraction Pipeline for Mode 3 Authoring Voice

### Problem

The current Pass 1 and Pass 2 extraction prompts don't enforce how scaffold content is written. The consultant identifies three authoring modes:

| Mode | What It Produces | Quality |
|---|---|---|
| Mode 1: Instructions to the LLM | Scripted, rigid responses — agent follows procedure regardless of user input | Poor |
| Mode 2: Reference material | Book reports — agent summarizes framework instead of applying it | Poor |
| Mode 3: Declarative assertions | Applied reasoning — agent absorbs assertions as beliefs and evaluates user's situation through them | Target |

Mode 3 means writing `principles` and `steps` as sharp, opinionated assertions the LLM reasons *from* — not definitions, not instructions, not textbook descriptions.

### What Changes

**Pass 1 system prompt** — Add explicit voice guidance and negative examples:

- "Write each principle as a declarative assertion a smart colleague would wield in conversation, not a definition they'd file away."
- "Do not write instructions to the LLM ('When the user asks about X, walk them through...'). Write assertions the LLM can reason from ('X is actually Y. The common mistake is Z.')."
- Include the consultant's three-mode examples as few-shot demonstrations of what to produce and what to avoid.

**Pass 2 enrichment prompt** — Add a rewrite pass:

- "For each framework, evaluate whether `principles` and `steps` read as Mode 3 (declarative assertions) or Mode 1/2 (instructions or reference material). Rewrite any Mode 1/2 content into Mode 3."
- "Authoring heuristic: if you pasted this sentence into a conversation with a smart colleague, would they use it to think differently about a problem — or would they just nod and file it away? If they'd file it away, rewrite it."

**Quality gate** — Add to `framework_quality_edge_cases.md`:

- Issue Type 5: Mode 1/2 Content
- Detection: principles/steps that contain second-person procedural language ("First, ask the user...", "Walk them through...") or encyclopedia-style definitions ("X can be defined as...")
- Fix: Rewrite as declarative assertions with built-in diagnostics

### Why This Matters

This is the single highest-leverage change. It transforms every framework from something the agent *tells the user about* into something the agent *thinks through*. The consultant's Mode 3 examples demonstrate a measurable difference in LLM output quality — the agent stops summarizing and starts applying.

---

## Recommendation 2: Rework the DB Schema

### Problem

The current schema stores routing fields and metadata in the same object that gets injected at runtime. Every token spent on `when_to_apply`, `category`, `source_posts`, `confidence`, `origin`, and `related_frameworks` inside the prompt is wasted context window — the agent doesn't need to know *why* the framework was selected or where it came from.

Additionally, two high-value fields identified in the consultant's design have no equivalent in the current schema:

- `guidance` — a behavioral nudge telling the agent what move to make first
- `core_question` — the single underlying question a user is wrestling with when this framework is the right tool

### What Changes

**Add columns to `frameworks` table (table 14):**

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `guidance` | `text` | — | 1-2 sentences: what move the agent should make first. Not a procedure — a nudge. |
| `core_question` | `text` | — | The underlying question a user is wrestling with when this framework applies. Written from the user's perspective, not the thought leader's terminology. |
| `anti_triggers` | `text[]` | — | Situations where this framework looks like a match but isn't. Added surgically for frameworks that show routing collisions. |
| `adjacent_ids` | `text[]` | — | `framework_id` values of commonly related frameworks. Supports conversational follow-on ("Now that we've applied X, you might also want to think about Y"). |
| `type` | `text` | — | Descriptive metadata only (not structural). Values: `distinction`, `taxonomy`, `diagnostic`, `reframe`, `decision_heuristic`, `failure_catalog`, `matrix`, `evaluation_criteria`, `procedure`, `general`. Open list — new values addable without migration. |

**Add `core_question` to trigger embedding pipeline:**

Embed `core_question` as an additional vector in `framework_trigger_embeddings` (table 15), alongside the existing per-trigger vectors. This gives the embedding retrieval step a high-signal "what problem is the user trying to solve?" vector in addition to the situational trigger vectors.

**Runtime injection trimming:**

At injection time, strip the following fields from the payload before inserting into the prompt:

| Field | Reason |
|---|---|
| `when_to_apply` | Routing surface — already served its purpose in selection |
| `category` | Admin/browsing metadata |
| `source_posts` | Content operations metadata |
| `confidence` | Extraction metadata |
| `origin` | Extraction metadata |
| `related_frameworks` | Used by application logic for follow-on suggestions, not needed in prompt |
| `anti_triggers` | Routing surface |
| `core_question` | Routing surface |

**Injected payload after trimming:**

```
name, description, type, principles, steps, example_application, adjacent_ids, guidance
```

Target: 400-600 tokens per injected payload. `adjacent_ids` included because the agent can reference follow-on frameworks conversationally.

### Why This Matters

`guidance` gives the agent a starting move — the difference between an agent that says "According to this framework..." and one that asks the discriminating question. `core_question` improves routing accuracy by giving the embedding pipeline a "what problem is the user solving?" signal. `anti_triggers` prevent wrong-pick scenarios that the consultant correctly identifies as worse than no injection. `adjacent_ids` support multi-turn framework traversal. Runtime trimming recovers 100-400 tokens of context window per query.

---

## Recommendation 3: Add `anti_triggers` and `adjacent_ids` as Launch Fields

### Problem

The consultant treats `anti_triggers` as optional ("add surgically for objects that show routing collisions in testing") and `adjacent_ids` as future-proofing. Both should be launch fields.

### Rationale: `anti_triggers`

With 115 frameworks and topical clusters (multiple frameworks about strategy, multiple about team dynamics, multiple about AI adoption), routing collisions are inevitable. The consultant's own document says "a wrong pick means the agent applies an irrelevant lens, producing a response worse than no injection at all." If wrong picks are catastrophic, the mitigation can't be optional.

`anti_triggers` give the LLM reranker (Haiku, step 3 of the selection pipeline) negative signal to work with. Without them, the reranker only has positive matching surface and must infer what doesn't fit.

**Extraction impact:** Pass 2 prompt adds an instruction: "For each framework, identify 1-3 situations where this framework would appear to match but would produce a wrong or misleading application. Write these as `anti_triggers`."

### Rationale: `adjacent_ids`

Kinetic's core use case is conversational — the user talks to an agent over multiple turns. After the agent applies one framework, the natural next move is often a related framework. "Now that we've identified this is a performative clarity problem, here's a diagnostic for whether the root cause is strategic courage or structural misalignment."

Without `adjacent_ids`, the agent has no way to make this connection. With them, the application layer can suggest or auto-select a follow-on framework when the conversation warrants it.

**Extraction impact:** Pass 2 prompt already has access to the full framework index. Add an instruction: "For each framework, identify 0-3 other frameworks that are commonly applied in sequence or that address related aspects of the same problem. Reference by `id`."

---

## Recommendation 4: Update the Upload Format

### Problem

The current upload format doesn't include the new fields (`guidance`, `core_question`, `anti_triggers`, `adjacent_ids`, `type`). The extraction script output and the upload validation logic need to match.

### What Changes

**Updated framework object in upload JSON:**

```json
{
  "id": "kebab-case-unique-id",
  "name": "Framework Name",
  "type": "distinction",
  "description": "One-sentence description",
  "category": "strategy",
  "core_question": "The underlying question a user is wrestling with when this framework applies",
  "when_to_apply": [
    "Trigger phrase 1",
    "Trigger phrase 2"
  ],
  "anti_triggers": [
    "Situation where this looks like a match but isn't"
  ],
  "principles": [
    "Declarative assertion 1 (Mode 3 voice)",
    "Declarative assertion 2"
  ],
  "steps": [
    "Step 1 (if procedural — empty array if not)"
  ],
  "example_application": "2-3 sentence concrete scenario",
  "guidance": "1-2 sentences: what move the agent should make first",
  "adjacent_ids": [
    "related-framework-id"
  ],
  "related_frameworks": [
    "other-framework-id"
  ],
  "source_posts": [
    {
      "id": "post_id",
      "title": "Post Title",
      "date": "2026-01-15",
      "url": "https://example.com/post"
    }
  ],
  "confidence": "high",
  "origin": "extracted"
}
```

**Validation updates:**

| Field | Required | Validation |
|---|---|---|
| `id` | Yes | Non-empty, kebab-case, unique per agent |
| `name` | Yes | Non-empty |
| `type` | No | If present, must be non-empty string |
| `description` | No | — |
| `category` | No | — |
| `core_question` | No | — |
| `when_to_apply` | Yes | Non-empty array, each element non-empty string |
| `anti_triggers` | No | If present, array of non-empty strings |
| `principles` | Yes | Non-empty array |
| `steps` | No | Array (can be empty) |
| `example_application` | No | — |
| `guidance` | No | — |
| `adjacent_ids` | No | If present, array of strings; referential integrity check against other `id` values in the upload |
| `related_frameworks` | No | Array of strings |
| `source_posts` | No | If present, array of objects with `id` and `title` |
| `confidence` | Yes | `high` or `medium` |
| `origin` | Yes | `extracted` or `manual` |

**Merge behavior unchanged:** matching `id` = update, new `id` = add, missing = retain, per-framework validation with partial import.

**Backward compatibility:** Existing upload files missing the new fields will pass validation (all new fields are optional). Frameworks uploaded without `guidance` or `core_question` simply won't have those fields populated — they work as they do today, just without the enhancement.

---

## Recommendation 5: Re-Extract All 115 Frameworks

### Problem

The current 115 frameworks were extracted under the old pipeline prompts. They contain Mode 1/2 content in `principles` and `steps`, lack `guidance`, `core_question`, `anti_triggers`, `adjacent_ids`, and `type` fields, and don't benefit from the quality improvements in the updated extraction prompts.

Transforming existing frameworks (mapping current fields into new fields) would be faster but misses the quality improvement that comes from a fresh Mode 3 extraction pass.

### What Changes

**Full re-extraction from source corpus.** Not a transformation of existing output — a fresh run through the updated Pass 1 + Pass 2 pipeline.

**Pass 1 updates:**
- Mode 3 authoring voice enforcement (Recommendation 1)
- `type` classification per framework
- `core_question` generation
- `anti_triggers` generation (situations that look like matches but aren't)

**Pass 2 updates:**
- Mode 3 rewrite pass on any principles/steps that read as Mode 1/2
- `guidance` field generation (behavioral nudge per framework)
- `adjacent_ids` cross-referencing (requires full index visibility)
- All existing Pass 2 responsibilities (dedup, merge, category, trigger rewrite, example_application)

**Quality validation after re-extraction:**
- Run all existing quality edge case detections (self-assessment trap, empty shells, tool-specific config, referenced-but-not-extracted)
- Add Mode 1/2 detection (new Issue Type 5 from Recommendation 1)
- Compare framework count: expect ~115 +/- 10% (some may split, some may merge during dedup)
- Spot-check 10 frameworks across different types for Mode 3 voice quality

**Preserve existing `id` values where possible.** The re-extraction should attempt to match new frameworks to existing IDs so that any user-side references (pinned frameworks, excluded frameworks in AgentInstances) remain valid. Pass 2 prompt should include the existing framework index as a reference for ID stability.

---

## Impact Summary

| Area | Change | Effort |
|---|---|---|
| Extraction pipeline (Pass 1 prompt) | Mode 3 voice, type classification, core_question, anti_triggers | Medium |
| Extraction pipeline (Pass 2 prompt) | Mode 3 rewrite pass, guidance generation, adjacent_ids | Medium |
| Quality edge cases doc | Add Issue Type 5 (Mode 1/2 content) | Low |
| DB schema (table 14) | Add 5 columns: `guidance`, `core_question`, `anti_triggers`, `adjacent_ids`, `type` | Low |
| Trigger embedding pipeline (table 15) | Embed `core_question` as additional vector | Low |
| Runtime injection | Strip routing/meta fields before prompt insertion | Low |
| Upload format | Add new fields to JSON spec and validation | Low |
| Re-extraction | Full re-run of 115 frameworks through updated pipeline | High |

---

## Open Questions

1. **`guidance` generation timing.** Is `guidance` generated during Pass 2 extraction, or is it a manual authoring step? Recommendation: generate in Pass 2, allow manual override via UI edit. Pass 2 has full framework context and can produce a reasonable first-pass nudge.

2. **`core_question` embedding placement.** Should `core_question` be embedded as an additional row in `framework_trigger_embeddings` alongside per-trigger vectors, or should it be a separate signal fed to the reranker? Embedding it gives the retrieval step (step 1) access. Feeding it to the reranker (step 3) is cheaper but only affects precision on top-5 candidates.

3. **Token budget validation.** The consultant targets ~400 tokens per injection payload. After trimming routing/meta fields, do our current frameworks fit within 400-600 tokens? Run a token count across all 115 and identify outliers. If >20% exceed 600 tokens, we need compression guidelines or a hard trim policy.

4. **`adjacent_ids` vs. `related_frameworks`.** These overlap. `related_frameworks` currently exists in the schema. Options: (a) keep both with distinct semantics (`related_frameworks` = topically related, `adjacent_ids` = applied in sequence), (b) merge into one field, (c) drop `related_frameworks` in favor of `adjacent_ids`. Needs a decision.

5. **Type-specific scaffolds as a future path.** These recommendations keep a uniform schema with `type` as metadata only. If post-launch evals show that certain framework types (distinctions, diagnostics) consistently underperform, the `type` field gives us the data to evaluate whether type-specific scaffold schemas would help. This is the earned path to the consultant's full proposal — data first, structural change second.

---

## Pipeline Findings (2026-03-22 review)

Two additional issues identified during a final-pass review of the retrieval and injection pipeline against the JTBD ("expert-grade reasoning in a niche space for complex decisions").

### Finding 1: Multi-turn context blindness in retrieval

**Problem:** Step 1 (embedding) and Step 3 (reranker) operate on the current user message only. In multi-turn conversations — the primary usage pattern — follow-up messages are short and context-dependent ("what are the main risks here?" after 10 messages about pricing strategy). Without conversational context, the pipeline matches on the bare follow-up, not the actual topic.

**Fix:** Prepend the last 2-3 user messages (or a rolling summary) to the query before embedding and before passing to the reranker. Low cost, no architectural change.

**Status:** Comment added to KIN-259 (Gilfoyle ADR — Agents). Gilfoyle to spec the approach and token budget implications.

### Finding 2: No-injection confidence threshold is unspecified

**Problem:** The spec says "if the top score is below a threshold, no framework is injected," but the threshold value is undefined and there is no eval plan to calibrate it. Getting this wrong is asymmetric: too low → wrong frameworks applied (worse than no injection per the consultant's analysis), too high → frameworks rarely fire and the feature feels absent.

**Fix:** Build a framework selection eval (30-50 queries, including "no match" and ambiguous cases) and tune the threshold empirically before user testing.

**Status:** KIN-260 created for Jìan. High priority, blocks user testing.
