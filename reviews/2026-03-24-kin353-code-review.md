# Code Review: KIN-353 — [Jared] Author Nate B. Jones agent system prompt

**Reviewer:** Gilfoyle
**Date:** 2026-03-24
**Round:** 1
**Verdict:** Changes Requested
**Critical:** 1 | **Important:** 1

---

## Summary

The system prompt is well-crafted. Voice calibration is sharp and consistent with extracted framework content. Anti-patterns are explicitly addressed. Token budget (~600) is reasonable against the `instructions` field target. The 9-layer stack boundary is respected — the prompt correctly avoids duplicating what the platform handles (Active Memory, RAG, model tuning). Design notes are thorough.

One Critical finding blocks approval: the prompt references MVP strategy schema fields that do not exist in the current framework corpus.

---

## Findings

### C1 — Schema mismatch: prompt references fields that don't exist (Critical)

**File:** `docs/nate-system-prompt.md`, lines 37–39

**Issue:** The prompt explicitly instructs the agent to use `nate_would_say` and `guidance` fields. The current 376 production frameworks use the intermediate schema (`description`, `principles`, `steps`, `example_application`). Per `MEMORY.md` and `nbj_extractor/framework-mvp-strategy.md` section "Current State vs. This Strategy", zero frameworks have been migrated to the MVP strategy schema. The `nate_would_say` and `guidance` fields do not exist in any framework.

If this prompt ships with the intermediate schema, the agent will:
- Look for `nate_would_say` and `guidance` — never find them
- Receive `principles`, `steps`, `description`, `example_application` — have no instructions for how to use them
- Fall back to generic LLM behavior, which is exactly what this prompt is designed to prevent

**Fix:** The prompt must handle the schema that actually ships. Two options:

1. **If shipping with intermediate schema (current state):** Add instructions for `principles`, `steps`, `description`, and `example_application` fields. The existing Mode 3 language ("walk through the framework's logic as your own reasoning") covers `steps` implicitly, but `principles` and `example_application` need explicit treatment. Remove or condition the `nate_would_say` / `guidance` references.

2. **If migrating to MVP strategy schema before launch:** The prompt is correct as-is, but this creates a hard dependency on the schema migration completing first. That migration is estimated at 3-4 days and the decision is still pending (MEMORY.md open questions). This prompt cannot ship before that decision is made.

Either way, the prompt and the framework corpus must be in sync at launch. This is a spec gap — the prompt assumes a schema that doesn't exist yet.

### I1 — No fallback for missing framework injection (Important)

**File:** `docs/nate-system-prompt.md`, lines 30–39

**Issue:** The prompt's "How you think" section is entirely framework-dependent ("When a framework is provided to you..."). There is no instruction for what the agent should do when no framework is injected — which will happen when the classifier finds no match above the similarity threshold. In that scenario, the agent's reasoning instructions are entirely absent.

**Fix:** Add a 2-3 sentence fallback: when no framework is provided, the agent should still apply its advisory voice, ask diagnostic questions, and reason from first principles. Something like: "When no framework is provided, reason from your own experience. Ask the diagnostic question that gets to the real issue. The frameworks sharpen your thinking — they don't replace it."

---

## Non-Blocking Observations

### N1 — Open questions belong in the ticket, not the shipped prompt doc

The four open questions for Monica review (lines 88-96) are good product questions, but they should be tracked in a Linear ticket or comment, not left in the document that becomes the shipped artifact. When this prompt is finalized, the "Open questions" section should be removed or moved to a separate review doc.

### N2 — Multi-framework future-proofing is low-risk

Open question 3 (multi-framework handling) is a non-issue for MVP. The pipeline injects exactly one framework. The singular language ("a framework") is correct for now. When multi-framework ships post-MVP, the prompt will need a revision pass anyway. Don't over-engineer for a scenario that doesn't exist yet.

### N3 — "Great question" anti-pattern may be unnecessary

Open question 4 is right — modern models (Opus, Sonnet) rarely produce "Great question!" without explicit instruction to do so. But it costs ~15 tokens and serves as a safety net for weaker models under BYOK. Keep it — the insurance is cheap.

---

## Verdict

**Changes Requested.** The prompt is strong on voice, anti-patterns, and stack boundary separation. But it references a schema that doesn't exist yet (C1), which means it will produce exactly the failure mode it's designed to prevent. The schema decision in MEMORY.md must be resolved first, and the prompt must match whichever schema ships. The missing no-framework fallback (I1) is a secondary fix that should be addressed in the same pass.
