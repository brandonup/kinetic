# Framework Quality Edge Cases
**Purpose:** Log of quality issues found during manual review that the extraction script does not currently catch. Use this to improve automated validation so future extractions surface these problems before human review.

**Reviewed against:** `frameworks_index.json` (123 frameworks, extraction date 2026-03-20)
**Review date:** 2026-03-21
**Reviewer action:** 5 frameworks fixed/removed initially; 6 additional frameworks fixed 2026-03-21 (Issue Type 4); 115 remain unchanged.

---

## Issues Found

### Issue Type 1: Self-Assessment Trap
**Definition:** Framework steps are instructions the *user* executes on themselves. The agent can only read them back as directions, which is unhelpful when the user expects the agent to apply reasoning on their behalf.

**Frameworks affected:**
- `locus-of-control-circle-exercise` — Steps included "Draw a circle on a piece of paper" and "Place each element inside or outside the circle." Physical exercise; agent cannot observe or facilitate it.
- `ai-fluency-assessment-framework` — All 8 steps were "Score yourself on X" followed by references to prompts the user should run separately. Agent was a rubric-dispenser, not an assessor.

**Detection heuristic for the script:**
- Scan `steps` array for phrases: `"score yourself"`, `"rate yourself"`, `"draw a"`, `"write down"`, `"list your own"`, `"on a piece of paper"`, `"pull up your"`, `"look at your own"`, `"assess where you"`.
- Flag any framework where ≥50% of step strings begin with a second-person self-directed verb ("Score", "Rate", "Draw", "Write", "List", "Audit your own", "Identify your own").
- Auto-flag if `steps` array contains the word "yourself" in more than 2 entries.

**Fix pattern:** Rewrite steps so the agent conducts an interview and derives the assessment from user responses. Add an explicit permission-ask step when the assessment is structured and multi-question.

---

### Issue Type 2: Empty Framework Shell
**Definition:** Framework has no `steps`, no `example_application`, and no `source_posts`. The framework name and description exist, but there is no content for the agent to apply. Injecting it produces the same generic response the agent would give without any framework.

**Frameworks affected:**
- `three-kinds-of-reading` — Empty `steps: []`, empty `example_application: ""`, empty `source_posts: []`. Three reading modes named but no classification criteria or diagnostic logic.
- `nine-principles-of-business-writing-with-ai` — Empty `steps: []`, empty `example_application: ""`, empty `source_posts: []`. The `principles` field describes meta-observations *about* the 9 principles but never lists them. Agent cannot apply content that doesn't exist.

**Detection heuristic for the script:**
- Hard rule: flag any framework where `steps` is empty AND `example_application` is an empty string.
- Soft rule: flag any framework where `steps` is empty AND `source_posts` is empty (indicates the source content was never successfully extracted).
- Soft rule: flag any framework where `principles` contains phrases like "each principle addresses" or "the principles work as a checklist" without the principles themselves being enumerable — e.g., if the principles list has fewer entries than the numeric claim in the description ("nine principles" but only 5 generic meta-statements listed).

**Fix pattern:** Either populate from the source post or remove. Do not retain shells in the index.

---

### Issue Type 3: Partial Process Spec (Tool-Specific Configuration Embedded in Otherwise Valid Framework)
**Definition:** A framework contains genuinely useful diagnostic reasoning in Parts 1–2 but embeds tool-specific setup instructions in a later section. When injected, the agent will eventually reach the setup steps and start reciting configuration commands rather than giving advisory reasoning.

**Frameworks affected:**
- `the-finishing-framework` — Parts 1–2 are a strong 7-axis diagnostic for evaluating agentic harnesses. Part 3 was entirely Claude Code-specific: `set up CLAUDE.md via /init`, `configure permissions across four modes`, `build team-scale workflows via .claude/commands with $ARGUMENTS support`. The agent is a thought leader advisor, not a setup wizard.

**Detection heuristic for the script:**
- Scan `steps` for tool-specific command syntax: references to `.claude/`, `CLAUDE.md`, `/init`, `$ARGUMENTS`, `LangGraph`, specific CLI flags, or file paths that only make sense inside a particular tool's environment.
- Flag any framework where ≥1 step contains a tool-specific command string (e.g., regex for `/\.\w+\/`, `via /init`, `$[A-Z_]+`).
- Also flag if a step string starts with "Part 3" or contains the phrase "Power-User Patterns (for" — this naming convention signals a tool-specific section was appended to a general framework.

**Fix pattern:** Split the framework into a general advisory version (Parts 1–2) and a separate tool-specific implementation guide. Keep only the advisory version in the classifier index.

---

### Issue Type 4: Referenced Content Never Extracted (No Agent-Applicable Reasoning)
**Definition:** Framework steps or description reference a specific number of named items (axes, dimensions, questions, components, rules) that are central to the framework's value, but those items were never extracted from the source post. The agent has no substantive content to apply and will either hallucinate the missing items or produce generic advice indistinguishable from a default LLM response.

**Frameworks affected and fixes applied (2026-03-21):**

**a) `six-axes-of-hard-difficulty-framework`**
- **Defect:** Steps said "decompose the task across all six difficulty axes" but the six axes were never named or defined.
- **Fix:** Rewrote steps with the six verified axis names from source post id 188837484: **(1) Reasoning, (2) Effort, (3) Coordination, (4) Emotional Intelligence, (5) Domain Expertise, (6) Ambiguity.** Each axis includes definitions and examples from the source post. Automation timelines verified from same post.
- **Confidence raised to `high`** — axis names and definitions verified against source post content.

**b) `token-management-audit`**
- **Defect:** Steps said "score the organization across five dimensions of intelligence spend" but the five dimensions were never listed.
- **Fix:** Rewrote steps to include five inferred dimension names (Intelligence Retention, Reuse Leverage, Capability Compounding, Spend Concentration, Measurement Maturity) with scoring rubric and classification thresholds.
- **Confidence remains `low`** with `_quality_note` — source post id 188436740 confirms the "five dimensions" concept but does not enumerate them in the post body. The dimension names are in the linked prompt kit (promptkit.natebjones.com/20260213_d03_promptkit_1). **Requires backfill from prompt kit when accessible.**

**c) `magnifying-glass-vs-tiger-team-company`**
- **Defect:** Empty `steps: []`. Principles clearly defined the two archetypes but the agent had no diagnostic questions to classify the user's organization.
- **Fix:** Added 4 diagnostic questions (AI budget concentration, crisis response pattern, time-on-legibility vs. time-on-work, metric gaming behavior) followed by classification and archetype-specific advice.
- **Confidence remains `high`** — diagnostic questions derived directly from the rich principles already in the framework.

**d) `the-moat-audit`**
- **Defect:** Description promised "12 structured diagnostic questions" but none appeared in the framework. The agent would generate generic competitive analysis.
- **Fix:** Rewrote steps to include 12 inferred diagnostic questions covering accuracy under distribution shift, real-world data resilience, data replicability, graceful degradation, feedback loops, time-to-replicate, moat layer identification, production-only failure modes, edge case exposure, provider dependency, pricing defensibility, and adversarial attack surface.
- **Confidence remains `low`** with `_quality_note` — source post id 182475814 confirms "Twelve questions that reveal whether your system will hold under pressure" but does not list them in the post body. The questions are in the linked guide/prompt kit. **Requires backfill from prompt kit when accessible to replace with Nate's exact 12 questions.**

**e) `ten-components-of-good-judgement`**
- **Defect:** Empty `steps: []`. The ten principles were rich and specific but the agent had no diagnostic flow — it would dump all ten as a list rather than diagnosing the user's weak spots.
- **Fix:** Added a diagnostic sequence that asks the user to describe a recent decision, then probes against each of the ten components (which were already fully enumerated in the `principles` array), identifies the 2-3 weakest, and gives targeted development advice.
- **Confidence remains `high`** — all ten components were already extracted correctly in the principles; only the diagnostic steps were missing.

**f) `llm-decision-safety-rules`**
- **Defect:** Empty `steps: []`. The seven rules were strong and specific in the `principles` array but the agent had no structured way to apply them — it would recite them as tips rather than actively interrogating the user's decision process.
- **Fix:** Added a 9-step diagnostic flow where the agent asks about the user's decision, then applies each of the 7 rules sequentially (probing the user's process against each one), and synthesizes a verdict on whether the decision process is sound.
- **Confidence remains `high`** — all seven rules were already extracted correctly in the principles; only the application steps were missing.

**Detection heuristic for the script:**
- Scan `description` and `steps` for numeric claims ("six axes," "five dimensions," "12 questions," "ten components") using regex: `\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)\s+(axes|dimensions|questions|components|rules|principles|steps|criteria|factors|elements)\b`
- Cross-reference: count the number of items actually present in `steps` and `principles` arrays that correspond to the claimed items
- Flag if the claimed count exceeds the actual enumerable items by more than 1
- Also flag if `steps` contains phrases like "across all [N]" or "work through all [N]" where the [N] items are never listed in any field

**Fix pattern:** Extract and embed the named items from the source post into the `steps` array. If source post is inaccessible, infer from context and lower `confidence` to `low` with a `_quality_note` field documenting that backfill is required.

**Source verification pass (2026-03-21):** All 6 source posts retrieved from `nate_b_jones_content.jsonl` and cross-referenced. Results: (a) Six Axes — all 6 axis names verified and corrected, confidence raised to `high`; (b) Token Management Audit — post confirms concept but 5 dimensions are in linked prompt kit, not post body, confidence remains `low`; (c) Magnifying Glass — post confirms archetypes, diagnostic questions derived from principles, confidence `high`; (d) Moat Audit — post confirms "12 questions" but they're in linked prompt kit, confidence remains `low`; (e) Ten Components — all 10 verified against post's numbered list, confidence `high`; (f) LLM Decision Safety Rules — all 7 verified against post's numbered list, confidence `high`. Remaining backfill needed: Token Management Audit dimensions and Moat Audit questions (both in prompt kits at promptkit.natebjones.com).

---

## Borderline Cases (Kept — Not Fixed)
These were reviewed and kept because the agent can still produce useful responses, but they are worth monitoring:

| Framework | Issue | Why Kept |
|-----------|-------|----------|
| `frontier-operations` | Empty `steps: []` | Principles are rich enough that agent can apply them as a diagnostic lens; named five operations give structure |
| `the-201-gap-framework` | Empty `steps: []` | Framework names the six missing meta-skills explicitly; agent can diagnose against them |
| ~~`magnifying-glass-vs-tiger-team-company`~~ | ~~Empty `steps: []`~~ | **FIXED 2026-03-21** — Diagnostic steps added (Issue Type 5 below) |
| `apple-vs-the-beaker-bell-labs-vs-apple-innovation-models` | Empty `steps: []` | Classification is self-contained; agent can apply it to a described launch strategy |
| `raft-rules` | Empty `steps: []` | Principles are specific and operational; agent can apply them as a survival-mode filter |
| `the-narrow-pipe-law` | Empty `steps: []`, single principle | Principle is specific and actionable; agent can apply it to data pipeline questions |
| `engineers-bet-with-code-product-bets-with-time` | Empty `steps: []` | Mental model is self-contained; agent can use it to reframe engineering vs. product risk |
| ~~`llm-decision-safety-rules`~~ | ~~Empty `steps: []`~~ | **FIXED 2026-03-21** — Diagnostic steps added applying each rule sequentially (Issue Type 5 below) |
| `tokenizable-data-tiers` | Empty `steps: []` | Three tiers are clearly defined with examples; agent can classify user data |
| `coordination-tax-audit` | Step 1 says "pull up your actual calendar" | Agent can ask user to share time data verbally; rest of steps are diagnostic |
| `collapse-position-audit` | Coaching-style steps | Agent can facilitate as a structured conversation |

**Monitoring recommendation:** Add a soft warning flag for frameworks with `steps: []` that still have `confidence: "high"`. These are the most likely to drift from useful to hollow as the framework library grows. Re-review them if the agent's response quality on related queries degrades.

---

## Recommended Script Validation Rules (Summary)

Add these checks to the extraction pipeline before committing any framework to the index:

```python
def validate_framework(fw):
    issues = []

    # Hard block: completely empty shell
    if not fw.get('steps') and not fw.get('example_application') and not fw.get('source_posts'):
        issues.append('BLOCK: Empty shell — no steps, no example, no source posts')

    # Hard block: nine-principles-style missing content
    desc = fw.get('description', '').lower()
    principles_count_claim = re.search(r'(\w+)\s+principles', desc)
    if principles_count_claim:
        word_to_num = {'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10}
        claimed = word_to_num.get(principles_count_claim.group(1))
        actual = len(fw.get('principles', []))
        if claimed and actual < claimed - 1:
            issues.append(f'WARN: Description claims {claimed} principles but only {actual} are listed')

    # Self-assessment trap
    self_assessment_phrases = ['score yourself', 'rate yourself', 'draw a circle',
                                'on a piece of paper', 'pull up your', 'assess where you',
                                'list your own', 'yourself' ]
    self_count = sum(1 for step in fw.get('steps', [])
                     if any(p in step.lower() for p in self_assessment_phrases))
    if self_count >= 2:
        issues.append(f'WARN: Self-assessment trap — {self_count} steps direct user to assess themselves')

    # Tool-specific configuration embedded
    tool_patterns = [r'\.claude/', r'CLAUDE\.md', r'/init\b', r'\$[A-Z_]+',
                     r'\.claude/commands', r'via /\w+']
    for step in fw.get('steps', []):
        for pattern in tool_patterns:
            if re.search(pattern, step):
                issues.append(f'WARN: Tool-specific config in step: "{step[:80]}..."')
                break

    # Soft warning: no steps but high confidence
    if not fw.get('steps') and fw.get('confidence') == 'high':
        issues.append('WARN: No steps defined but confidence is high — verify agent applicability')

    return issues
```

---

*Log maintained by: manual review*
*Next review trigger: next extraction run or when agent response quality degrades on flagged framework categories*
