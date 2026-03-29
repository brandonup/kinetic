# Validation, Evaluation, and Safe Rollout of the Pass 1 Injected-Framework Standard

## Executive answer

The fastest rigorous way to validate the Pass 1 framework-design recommendation is to treat it as **product logic** and test it like a skill: **(prompt + injected framework) → captured run (trace + artifacts) → deterministic checks + rubric grading → score trend over time**. This “skill-eval” framing is directly aligned with how entity["company","OpenAI","ai lab, san francisco, us"] describes agent-skill evaluation: measuring both outcomes and whether the system followed the intended process, not “vibes.” citeturn10view0turn10view1

To determine whether Pass 1 actually improves reasoning (not just structure), your eval suite should be built around three principles:

First, **separate the system into two evaluated components**: (a) **routing** (framework selection) and (b) **framework application** (did the model apply the expert logic correctly once selected). This decomposition is standard in modern routing systems evaluation (a router’s errors can dominate perceived “framework quality” if uncontrolled). citeturn6search14turn6search3

Second, **prioritize artifact-causal tests over “nice-looking explanations.”** There is strong evidence that chain-of-thought style reasoning text can be **unfaithful** (models can produce plausible rationales that are not the real determinants of their answers), and that models may partially ignore intermediate reasoning text depending on task/model size. Your framework design deliberately tries to avoid this by emphasizing artifacts; your eval should mirror that by verifying (1) artifact quality, (2) artifact→answer consistency, and (3) counterfactual dependence on artifacts. citeturn0search0turn0search1turn5search1

Third, **use a layered evaluation stack** that mixes (a) cheap deterministic checks (instruction-following / schema compliance), (b) scenario-based grading (expert rubric + calibrated LLM-judges), (c) adversarial + misfire probes, and (d) online A/B experiments with guardrails. This is consistent with both research emphasizing multi-metric evaluation across scenarios (HELM) and production guidance emphasizing repeatable eval harnesses to prevent regressions. citeturn1search1turn10view0turn10view1turn1search12

If you do only one “deep” thing beyond standard offline A/B, make it: **counterfactual framework-use verification**, where you intervene on the produced artifacts (or swap them) to test whether the final answer meaningfully changes in the expected direction—and whether the model catches inconsistencies. That is the cleanest operational signal separating real reasoning change from format mimicry. citeturn0search0turn0search1turn9search0

## Pass 1 recommendation summary

Pass 1’s working standard is a **hybrid “tool spec”** format for injected expert frameworks: a compact, consistently formatted framework that includes (a) applicability gates, key terms/distinctions, required inputs, output contract, quality checks, and failure-mode guidance, and (b) **optionally** a short procedural spine (roughly 3–7 steps) when ordering/completeness/computation matter. fileciteturn0file0

A central Pass 1 design choice is: **prefer steps that emit intermediate artifacts** (labels/tables/scores/hypothesis sets) over steps that narrate reasoning. The intent is to reduce “reasoning theater,” increase verifiability, and make downstream answer generation measurably shaped by intermediate state. fileciteturn0file0

Pass 1 also explicitly warns about constraints that matter for production reliability: long context and attention limitations, “lost in the middle,” and the need to keep frameworks compact and structurally separated (e.g., via tags/delimiters) so they parse as a tool rather than conversational prose. fileciteturn0file0 citeturn0search2turn10view3

A brief potential flaw to note (but still treat as the working standard): in some advisory domains, “every step emits an artifact” can increase verbosity and encourage pseudo-quantification if the artifacts are not tightly defined; this raises the importance of **artifact-quality rubrics** and “false precision” checks during eval and monitoring. fileciteturn0file0 citeturn4search7turn8search0

## Top failure modes

What follows is a prioritized set of real-world failure modes for the Pass 1 standard, each with “what it looks like,” causes, severity, detection, and mitigations that can be operationalized in evals and production.

**Framework is ignored or only partially attended to.**  
What it looks like: the response follows generic assistant patterns; the framework’s core distinctions don’t appear; required artifacts are missing; or the model behaves as if no gate/inputs were present.  
Why it happens: long-context attention limits and position effects (“lost in the middle”) can reduce use of mid-context instructions, and accumulated context can degrade retrieval (“context rot” / finite attention budget). citeturn0search2turn10view3  
Severity: high, because it collapses your product premise (expert logic reliably applied).  
How to detect: (a) deterministic “must-pass” checks for required outputs/artifacts, modeled after verifiable instruction-following evaluation; (b) position-stress tests where the same framework is moved earlier/later in context; (c) token-budget correlation (non-use rises as context grows). citeturn7search0turn0search2turn10view3  
Mitigation: shorten frameworks; place them in consistently “high-attention” positions; enforce high-salience delimiters; add a minimal “framework checksum” requirement (e.g., output must include the core labels defined by the framework) that is deterministically testable. citeturn11view2turn10view3 fileciteturn0file0

**Surface-level restatement instead of application.**  
What it looks like: the model paraphrases definitions and steps, but the recommendation doesn’t reflect them; artifacts (if present) are generic or uninformative; decisions don’t change when inputs change.  
Why it happens: LLMs can generate plausible reasoning narratives without those narratives being causally responsible for the answer (unfaithful explanations), so “looking like you used the framework” is easier than actually using it. citeturn0search1turn0search0  
Severity: very high, because it yields false confidence and can pass naïve rubrics that reward structure.  
How to detect: (a) minimal-pair tests where one input variable should flip the framework decision; (b) artifact→answer consistency checks; (c) counterfactual artifact intervention (swap or corrupt artifacts and see if the answer changes appropriately or flags inconsistency). citeturn0search1turn0search0turn9search0  
Mitigation: require artifacts whose fields are decision-relevant (not descriptive), and add explicit “decision rules tied to artifact fields” so you can unit-test whether rules fired. fileciteturn0file0

**Mechanical structure compliance with degraded reasoning quality.**  
What it looks like: the model produces all sections in the output contract, fills tables, and runs through steps, but the content is shallow, misses key hypotheses, or fails to ask clarifying questions.  
Why it happens: step-by-step prompting can improve multi-step reasoning on many tasks, but it can also induce rigid checklist behavior and “over-deliberation” dynamics; recent evidence shows chain-of-thought prompting can reduce performance for certain task families, meaning procedure can be actively harmful when misapplied. citeturn2search0turn2search1turn3search14  
Severity: high in advisory contexts (users may interpret completeness as correctness).  
How to detect: compare performance on “easy” vs “hard/exception” cases; include cases where the correct move is to *not* apply the full procedure (skip/branch), then score whether the model appropriately uses escape hatches. citeturn3search14turn10view0 fileciteturn0file0  
Mitigation: strengthen applicability gates; make “escape hatch usage” an explicit evaluated behavior; cap procedural depth; prefer branching checklists over long linear scripts. fileciteturn0file0 citeturn3search0turn3search14

**Artifact theater: artifacts are produced but do not shape the conclusion.**  
What it looks like: a score table says “Option A highest,” but the recommendation prioritizes Option B with no explanation; hypothesis set is generated, but the advice assumes a different hypothesis; the artifact is internally inconsistent with the final answer.  
Why it happens: intermediate text can be generated as a “compliance performance” without being used; both faithfulness and causality issues in chain-of-thought style reasoning can produce this pattern. citeturn0search0turn0search1  
Severity: very high because it specifically defeats Pass 1’s intended safeguard (artifacts as causal anchors).  
How to detect: enforce artifact→decision consistency as a scored criterion; run “artifact swap” tests; run “artifact corruption” tests where one field is perturbed and you check whether the conclusion changes correspondingly or the model flags the mismatch. citeturn0search0turn9search0  
Mitigation: tighten artifact schemas; add rule-based validators; require the model to cite which artifact fields drove each recommendation (not as free-form rationale, but as pointer-to-field). citeturn7search0turn10view0 fileciteturn0file0

**Framework overconstraint and tunnel vision.**  
What it looks like: the model fails to consider plausible off-framework factors; it treats the checklist as exhaustive; it misses “unknown unknowns,” especially in messy real-world scenarios.  
Why it happens: checklists can induce an inference that unlisted information is unlikely to matter; empirical work on checklists shows “selective vulnerability” to unlisted errors. citeturn3search3  
Severity: high in advisory domains (strategic, personal, ambiguous), where the right move may be to reframe or broaden scope.  
How to detect: include edge cases where the framework’s “what this misses” clause should trigger; grade whether the model acknowledges limitations and proposes additional hypotheses/questions. citeturn3search3turn1search1 fileciteturn0file0  
Mitigation: treat the quality-check section as mandatory and test it; add explicit “outside-the-framework check” prompts; implement a “max N steps before reconsider” rule for strategic frameworks. fileciteturn0file0 citeturn3search0turn3search14

**Wrong framework selection or misapplication to the user context.**  
What it looks like: classifier picks a mismatched expert tool; the model applies it even though applicability gates should fail; user gets irrelevant or harmful advice.  
Why it happens: routing is inherently noisy; routing evaluation research highlights tradeoffs between cost and quality under constraints, and misrouting can dominate system-level metrics if not isolated. citeturn6search14turn6search3  
Severity: very high because users experience “nonsense” as low trust, and in high-stakes domains misapplication can be dangerous.  
How to detect: maintain a dedicated “framework misfire” test set (true intent vs injected framework), and score “stop/decline/ask-clarify” behavior as a first-class metric. citeturn10view0turn7search2 fileciteturn0file0  
Mitigation: treat applicability gates as an enforceable contract; add “misapplied framework detection” rules; improve routing with explicit feedback loops (confusion labels) and monitor per-framework misfire rates in production. citeturn6search14turn10view0 fileciteturn0file0

**Longer frameworks reduce compliance; shorter frameworks lose nuance.**  
What it looks like: long frameworks cause missing step/artifacts; short frameworks produce vague, generic advice; performance becomes unstable as token budgets vary.  
Why it happens: long-context position effects + finite attention budget; as token count grows, effective retrieval and focus degrade, making “more instructions” a nonlinear risk. citeturn0search2turn10view3  
Severity: medium-to-high depending on traffic and how often contexts are long (multi-turn).  
How to detect: stratify evals by context length and “history depth”; add a “long-context stress suite” where you replay realistic conversation histories; measure compliance drop-off curves. citeturn0search2turn10view3turn8search2  
Mitigation: enforce maximum framework token budgets per type; use “capsule + expand on demand” patterns (short injected framework, with follow-up turns to elaborate); use caching strategies where relevant. citeturn10view3turn11view2 fileciteturn0file0

**Evaluation false positives: judges reward structure/verbosity instead of substance.**  
What it looks like: a framework variant “wins” offline because it produces longer, better formatted answers, but users don’t improve (or degrade), or the system regresses on hard cases.  
Why it happens: LLM-as-judge systems can have scoring biases (e.g., rubric order, scoring ID, reference-bias), and classic judge setups have known biases including verbosity-related effects; even frameworks like G-Eval explicitly note biases and limitations. citeturn4search7turn8search0turn8search2  
Severity: very high because it can drive you to ship placebo improvements.  
How to detect: (a) pairwise blind comparisons with randomized ordering; (b) multiple independent judges; (c) “format stripped” evaluation where headings and boilerplate are removed before judging; (d) periodic human-anchored audits. citeturn8search2turn8search0turn4search7  
Mitigation: treat LLM-judging as a calibrated instrument; keep a human evaluation budget; use judge-agreement checks; prefer deterministic metrics where possible for compliance. citeturn8search2turn7search0turn10view0

## Recommended eval architecture

This architecture is designed to test the *specific claims* implied by Pass 1: applicability gates matter, artifacts matter, short procedures help only in some cases, and output contracts reduce user-facing templating while maintaining reliability. fileciteturn0file0

### Offline evaluation stack

Your offline system should have three layers, each producing signals that are useful at different iteration speeds.

**Layer one: deterministic “spec compliance” tests (fast regression gate).**  
Model this after verifiable instruction-following benchmarks: check whether required sections/artifacts exist, constraints are met (e.g., “ask ≤N clarifying questions”), and disallowed behaviors are absent (e.g., quoting the framework verbatim if the contract forbids it). IFEval’s framing is directly relevant: make as many checks as possible objectively verifiable. citeturn7search0turn10view0

Concretely, implement:
- Output-contract presence checks (regex/JSON-schema when applicable). citeturn11view2  
- Artifact schema validation (field presence + type checks).  
- “Framework echo” detection via n-gram overlap / similarity to framework text (to detect quoting/parroting).  
- Token and latency budgets (efficiency goals are explicitly called out in agent-skill eval design). citeturn10view0turn10view3

**Layer two: scenario-based grading (reasoning quality + expert fidelity).**  
Use a fixed scenario suite grounded in your product’s real advisory intents. HELM is a useful conceptual reference: broad coverage across scenarios and multiple metrics, explicitly surfacing tradeoffs rather than collapsing everything into one score. citeturn1search1turn1search5

Design your scenario suite as:
- **Breadth slice:** many frameworks, fewer cases each, to catch “obviously broken” patterns early.  
- **Depth slice:** a smaller set of high-volume frameworks with many edge cases, to measure genuine robustness.  

A practical starting point that balances cost and signal:
- 8–12 pilot frameworks total.  
- ~40–60 scenarios per framework for “application eval” (framework fixed as correct), plus ~15–25 misfire scenarios per framework (wrong framework injected) to test applicability gates.  
This yields roughly ~500–900 total single-turn scenarios, which is enough to detect large regressions and compare framework variants with paired analysis, while not being so large that you can’t iterate weekly. This sizing is an engineering inference, but it follows the production advice to keep eval checks small, focused, and repeatable. citeturn10view0turn10view1

Scoring approach:
- Use a rubric-based judge setup inspired by MT-Bench (pairwise comparisons + rubric dimensions), but incorporate known judge-bias mitigations (randomized ordering; verbosity normalization; multi-judge). citeturn8search2turn8search0  
- Where you have domain experts, use them to label a calibration subset and periodically refresh it (human-anchored evaluation reduces judge drift). citeturn8search9turn4search7

**Layer three: adversarial + invariance tests (robustness).**  
Add metamorphic (semantic-preserving) transformations and adversarial prompt perturbations to detect brittle prompt/framework adherence and “format over substance.” Metamorphic testing has been applied to LLMs at scale and is a natural fit for framework invariants (“should not change decision under paraphrase”; “should change under specific variable flip”). citeturn9search0turn9search1

Include:
- Paraphrase/reordering/expansion/contraction variants of the same scenario (semantic invariance checks). citeturn9search0turn9search1  
- Conflicting or ambiguous user input (messy real-world).  
- Long-context placement tests (framework at beginning vs middle vs end). citeturn0search2turn10view3  
- Tooling-security tests where the user tries to override the framework or extract system/developer instructions; instruction hierarchy work and the entity["company","OpenAI","ai lab, san francisco, us"] Model Spec both highlight the importance of privilege separation and conflict handling. citeturn11view0turn6search2

### Framework-misfire and routing evaluation

Because your pipeline includes a classifier/router, you need two distinct offline test modes:

**Framework-fixed mode (isolating application quality).**  
You force-inject the *correct* framework so you can compare framework-structure variants without router noise.

**End-to-end routed mode (system reality).**  
You run the router normally and measure:
- Overall task success / user usefulness (rubric).  
- Router accuracy against labeled “best framework” ground truth.  
- “Graceful failure” behavior on low-confidence routing: ask clarifying questions, offer alternatives, or decline to apply. citeturn6search14turn10view0 fileciteturn0file0

Routing-specific metrics should follow router evaluation framing: per-query selection quality under constraints, plus cost/latency tradeoffs. citeturn6search14turn6search3

### Online evaluation and monitoring

Offline evals are necessary but insufficient for advisory products because user satisfaction and business outcomes are interactive and distribution-shifted. This is why online controlled experiments remain the gold standard for product changes; classic experimentation guidance emphasizes trustworthy A/B design to avoid misleading results. citeturn1search18turn1search6

Operational monitoring should include:
- Per-framework dashboards: misfire rate, fallback rate, user-reported “not relevant,” safety flags.  
- Drift monitors: sudden increases in token usage, refusal rates, or “asks too many questions.” citeturn10view0turn10view3  
- Regression gates: every framework version change must rerun Layer-one & Layer-two eval suites (OpenAI Evals framing: prompt changes are regressions unless proven otherwise). citeturn10view1turn1search12

## Measurement framework

A metric system that can distinguish “structure improvement” from “reasoning improvement” needs (a) a small set of **must-pass gates**, (b) a short set of **core graded dimensions** that predict user value, and (c) a few **diagnostic metrics** to explain failures.

This follows the production guidance to keep evaluation focused on the behaviors you care about most, mixing outcome/process/style/efficiency checks. citeturn10view0turn1search1

### Must-pass gates

These should be evaluated deterministically when possible (or with high-agreement judges), because they protect production.

**Applicability discipline:** if the framework’s “do not use when” applies, the model must not force-fit it; it must switch to clarifying questions or a safer generic approach. fileciteturn0file0

**Output contract compliance:** required sections present; no forbidden content (e.g., quoting the framework if disallowed). fileciteturn0file0 citeturn7search0turn11view2

**Artifact validity:** artifact fields present, coherent, and not self-contradictory; when a numeric score is claimed, it must be computed consistently within the stated rubric. citeturn7search0turn4search7

**Safety/instruction hierarchy compliance:** user attempts to override injected instructions should not succeed; system/developer instruction handling is a known vulnerability area, and instruction-hierarchy training is an explicit research direction for robustness. citeturn11view0turn6search2turn6search22

### Core graded dimensions

Score these on a 1–5 rubric (or pairwise preference) and treat them as your main offline “quality index.” To reduce judge bias, incorporate mitigations and periodic human anchoring. citeturn8search2turn8search0turn4search7

**Reasoning quality:** does the answer demonstrate correct decomposition, relevant factor coverage, and a coherent path from facts → analysis → recommendation, without obvious missing-step errors? Decomposition prompting work provides evidence that structured planning can reduce missing steps, but “reasoning quality” must be judged on content, not presence of steps. citeturn2search2turn2search1turn3search14

**Faithfulness to the framework:** did the model apply the framework’s rules/distinctions correctly, including gating and escape hatches, rather than merely paraphrasing? The need for this metric is strengthened by evidence of unfaithful rationales. citeturn0search0turn0search1

**Conceptual fidelity to expert distinctions:** are the expert’s categories used with correct boundaries under novel inputs, including messy phrasing? This is where metamorphic tests shine: evaluate stability under paraphrase and controlled perturbations. citeturn9search0turn9search1

**Decision quality and usefulness:** does the user get a recommendation that is actionable, context-aware, and appropriately qualified? Pairwise preference methods (as used in Chatbot Arena / MT-Bench) are often more reliable than absolute scores for “usefulness.” citeturn8search3turn8search2

**Robustness on messy inputs:** does the system ask clarifying questions when required inputs are missing, rather than hallucinating confident specificity? Agent benchmarks emphasize multi-turn decision-making and instruction-following failures as core obstacles in agent reliability. citeturn7search2turn10view0

**Calibration / uncertainty handling:** does the model appropriately signal uncertainty and identify what information would change the recommendation? Calibration research suggests models can be trained/prompted to better self-evaluate correctness under the right formats, making this both measurable and improvable. citeturn5search0turn5search1

**User-facing naturalness and verbosity control:** does the output avoid sounding robotic/templated and avoid unnecessary length while still meeting the contract? This matters because judge systems and users can both be biased by verbosity, and because token budgets are an operational constraint. citeturn8search2turn10view0turn10view3

### Diagnostic metrics

Use these to debug and prevent bad iteration incentives.

**Artifact-to-answer consistency score:** a deterministic or judge-graded measure of whether conclusions are consistent with artifacts. This is your single most direct signal against artifact theater. citeturn0search0turn0search1

**Framework echo / plagiarism score:** similarity between output and framework text (high similarity is often a failure if the output contract discourages quoting). fileciteturn0file0

**Overconstraint indicator:** count instances where the model fails to mention “what this misses” or fails to consider off-framework hypotheses in cases designed to require it (checklist vulnerability evidence motivates this). citeturn3search3

**Efficiency metrics:** tokens, latency proxies, and “thrash” behaviors; this directly follows agent-skill eval recommendations to track efficiency alongside outcomes. citeturn10view0turn10view3

## How to detect genuine framework use

Your concern—models can *look* like they used a framework without using it—is well-founded. Both “faithfulness” and “unfaithful explanation” lines of work show that intermediate reasoning text can be decoupled from the underlying determinants of the answer. citeturn0search0turn0search1

The practical solution is to operationalize “genuine use” behaviorally and counterfactually.

### Behavioral signatures that distinguish use types

**Genuine framework use** looks like:  
- Decisions vary correctly across minimal pairs that target the framework’s decision boundaries. citeturn2search1turn9search0  
- Artifacts are information-dense and decision-relevant, and the final answer explicitly depends on artifact fields in consistent ways. citeturn0search0turn10view0  
- Applicability gates and escape hatches are invoked on misfires, preventing forced application. citeturn6search14turn10view0 fileciteturn0file0

**Surface-level restatement** looks like:  
- High lexical overlap with framework language; low sensitivity to input perturbations; generic artifacts. citeturn0search1turn11view2

**Style imitation** looks like:  
- The answer adopts headings and tone but fails invariance tests (paraphrase changes outcomes unexpectedly) and fails boundary-case flips. citeturn9search0turn9search1

**Artifact theater** looks like:  
- Artifacts produced, but artifact-to-answer consistency is low; artifact swaps don’t change the conclusion; or the model follows swapped artifacts even when inconsistent with the input (indicating a shallow “read the last table” behavior rather than grounded reasoning). citeturn0search0turn0search1

### Concrete detection methods you can implement

**Counterfactual artifact intervention (primary recommendation).**  
Run the system in two passes: Pass A generates the artifact; Pass B generates the final answer. Now intervene:
- Swap Pass A artifacts between similar scenarios.
- Perturb one artifact field that should change the decision (e.g., change a threshold-crossing score).
- Insert a logical inconsistency between input facts and artifact values.

Then evaluate:
- Does the final answer change appropriately when the artifact is perturbed?
- Does the model detect and repair inconsistencies (ideal), versus blindly following the artifact (artifact over-trust)?  
This is the most direct causal test available without internal model interpretability. It is specifically motivated by faithfulness concerns about intermediate reasoning. citeturn0search0turn0search1turn9search0

**Minimal-pair boundary suites (“expert distinction unit tests”).**  
For each framework’s core distinctions, create 10–30 minimal pairs where a single changed fact should flip classification/prioritization. This aligns with decomposition prompting research aims (reducing missing steps) while measuring conceptual boundary fidelity directly. citeturn2search1turn2search2turn9search0

**Metamorphic invariance tests (robustness of expert logic).**  
Apply paraphrase, reordering, expansion, and contraction transformations to the same scenario and check whether the framework outputs and decisions remain stable when semantics are stable. This is directly supported by work using metamorphic testing for LLM robustness. citeturn9search0turn9search1

**Ablation and placebo frameworks.**  
- Remove only the procedural spine; keep definitions and output contract.  
- Replace the true framework with a similarly formatted but irrelevant “placebo” tool spec.  
If the system’s behavior barely changes (or changes only cosmetically), your “framework effect” is likely superficial. This is a standard causality logic from experimental design, adapted to prompts. citeturn10view0turn1search18

**Format-stripped judging to reduce structural bias.**  
Before LLM/human judging, strip headings, boilerplate, and repeated phrases; evaluate substance only. This mitigates known LLM-judge biases (verbosity/format) and is consistent with judge-bias research directions. citeturn8search2turn8search0turn4search7

**Consistency under sampling (stability of decisions).**  
For decisions that should be stable, run multiple seeds and compute decision variance; self-consistency research shows sampling multiple reasoning paths can change outcomes, so measuring variance becomes part of robustness evaluation (and can be used to select a decoding/aggregation strategy). citeturn5search1turn3search0

## A/B testing and rollout

### A/B testing plan

A production A/B test should be designed to ask two questions simultaneously: (1) *does the Pass 1 structure improve user outcomes?* and (2) *if it does, which components are doing the work (artifacts, procedure, taxonomy/rules)?* The plan below uses a multi-arm design, but can be staged if traffic is limited. citeturn1search18turn10view0

**Variants to compare (minimum set requested).**  
- No framework (classifier runs but injection suppressed).  
- Framework-free baseline prompting (generic “be thorough,” no expert tool).  
- Declarative-only framework.  
- Taxonomy/rules framework.  
- Hybrid structured without procedural steps.  
- Hybrid structured with short artifact-emitting procedure. fileciteturn0file0

**What to randomize and at what unit.**  
Randomize at the **user-session / conversation** level (sticky assignment by user_id for a period) to prevent cross-variant contamination within a single advisory thread; this is standard experimentation hygiene for conversational products. citeturn1search18turn1search6

To isolate framework effects from routing/model effects:
- Freeze the model version and decoding parameters for the duration of the test (unless you explicitly run a factorial model×framework experiment). citeturn11view3turn10view0  
- Either (a) keep router constant across variants, or (b) run an additional “framework-fixed” online slice where a subset of traffic is force-assigned to a known-correct framework for canonical intents (best when you can reliably label intent). citeturn6search14turn10view0

**Primary outcomes to track.**  
Use a small set of outcomes that reflect user value and business value, consistent with trustworthy online experiments guidance. citeturn1search18turn1search6

At minimum:
- Conversation-level user satisfaction (explicit rating or implicit proxy).  
- Task completion / resolution proxy (did the user stop asking because they got what they needed?).  
- Escalation or abandonment (if applicable).  
- Safety and policy flags / refusal correctness (must not regress). citeturn6search0turn11view0

Also track diagnostic outcomes:
- Follow-up question count (too many indicates over-asking; too few indicates hallucinated certainty). citeturn10view0turn5search0  
- Token usage and latency (efficiency). citeturn10view0turn10view3  
- Per-framework misfire rate (users indicating irrelevance, or applicability gate failures). citeturn6search14turn10view0

**How to interpret ambiguous results.**  
Ambiguity is expected because some variants improve structure but increase length (which can improve perceived helpfulness while harming efficiency), and because judge/user preferences can be sensitive to verbosity. citeturn8search2turn10view3

Guard against false conclusions:
- If “hybrid + procedure” wins on satisfaction but loses on completion and token cost, you may be shipping verbosity, not reasoning.  
- If offline rubric improves but online does not, suspect judge bias and placebo structure effects. citeturn8search0turn4search7turn1search18  
- If only some framework types improve, you likely need conditional procedure inclusion (which Pass 1 already recommends). fileciteturn0file0

**How long to run.**  
In practice, run until your pre-registered minimum detectable effect on the primary outcome is achieved, stratified by top intents/framework types (to avoid Simpson’s paradox across heterogeneous traffic). The discipline of pre-specifying analysis plans and avoiding selective reporting is standard experimentation best practice. citeturn1search18turn1search6

### Recommendations by framework type

Your eval criteria should share a common spine (adherence, robustness, naturalness, calibration) but emphasize different “core correctness” signals by framework class, consistent with Pass 1’s view that procedures should be selective and artifact-oriented. fileciteturn0file0

**Diagnostic frameworks:** emphasize hypothesis coverage, disconfirmation thinking, and whether artifacts enumerate plausible causes plus what would change the conclusion; include tunnel-vision probes because checklists can hide unlisted errors. citeturn3search3turn7search2 fileciteturn0file0

**Classification frameworks:** emphasize boundary fidelity (minimal pairs), stability under paraphrase, and correct elicitation questions when input is underspecified; deterministic scoring is often feasible here, so use it heavily. citeturn7search0turn9search0turn2search1

**Prioritization frameworks:** emphasize artifact correctness (scores/criteria applied consistently), explicit tradeoffs, and resistance to false precision; include “catastrophic risk shouldn’t be averaged away” style probes (Pass 1 warns about false precision). fileciteturn0file0 citeturn4search7turn10view0

**Decision frameworks:** emphasize threshold/rule correctness when policy-like; for strategic decisions, emphasize option generation and reconsideration rather than rigid step completion (Tree-of-Thoughts style exploration is conceptually aligned with branching evaluation). citeturn3search4turn3search0turn3search14

**Reframing frameworks:** emphasize whether the model reliably generates alternative frames and chooses ones that change action; penalize procedural overconstraint and robotic templating; Step-Back prompting evidence supports abstraction-first reasoning improvements relevant here. citeturn3search1turn3search14 fileciteturn0file0

**Strategic reasoning frameworks:** emphasize system mapping artifacts, incentive/constraint consideration, and robustness under messy partial info; include long-context stress tests because strategic conversations tend to be multi-turn and context-heavy. citeturn3search0turn0search2turn10view3 fileciteturn0file0

### Rollout plan

Assuming Pass 1 is directionally correct, the safest rollout is staged, eval-gated, and versioned.

**Pilot scope.**  
Start with ~8–12 frameworks spanning 2–3 framework types where evaluation is easiest (classification + prioritization are usually most testable; include 1–2 diagnostic frameworks if they are high-volume). This follows the principle that you want strong, repeatable signals before scaling breadth. citeturn10view0turn10view1

**Eval harness before scale.**  
Before adding more frameworks, build:
- A reproducible offline runner (fixed seeds / multiple seeds),  
- Deterministic checks,  
- A rubric judge pipeline with bias mitigations,  
- Dashboards per framework version. citeturn10view0turn10view1turn8search0

**Versioning and change control.**  
Treat frameworks as versioned artifacts (semantic versioning + changelog). Any framework change triggers:
- Layer-one regression gate,  
- Layer-two scenario suite,  
- Focused misfire suite,  
- Small canary online test (if risk is nontrivial). citeturn10view1turn1search12turn10view0

**Ongoing retesting triggers.**  
Re-run suites on:
- Model upgrades (prompt sensitivity changes are expected; OpenAI’s prompting guide explicitly notes instruction-following differences across versions and recommends building evals and iterating empirically). citeturn11view3turn11view2  
- Router updates. citeturn6search14turn6search3  
- Major traffic distribution shifts (new intents).  
- Any sustained metric drift (token usage jump, satisfaction drop) indicative of context/attention issues. citeturn10view3turn0search2

**Detect failing frameworks in production.**  
Maintain per-framework SLOs:
- Misfire SLO (applicability-gate failures).  
- Artifact failure SLO (missing/invalid artifacts when required).  
- User dissatisfaction SLO (downshift vs baseline).  
Violation triggers automatic rollback or traffic reduction to that framework version. This mirrors how large labs describe structured evaluation prior to deployment and use suites to detect regressions and risks. citeturn6search0turn10view0

**Feedback loop organization.**  
Create a triad workflow:
- Product: defines “success” + user outcomes.  
- Prompt/eval engineering: encodes success into tests and metrics.  
- Domain experts: author framework invariants + review boundary/edge cases.  
This is consistent with “define success before you write the skill” guidance from production eval practice. citeturn10view0

## Final practical guidance

Checklist for a product team implementing Pass 1 validation and rollout:

- Establish a single canonical **framework schema** (purpose, applicability, distinctions, inputs, optional procedure, artifacts, quality checks, output contract) and enforce schema compliance as a deterministic gate. fileciteturn0file0 citeturn7search0  
- Split eval into **router eval** and **framework application eval**; do not let routing noise masquerade as “framework quality.” citeturn6search14turn6search3  
- Build a reusable eval harness: **prompt → trace+artifacts → checks → score**; store runs for diffing across versions. citeturn10view0turn10view1  
- Implement **artifact schema validation** and **artifact→answer consistency checks**; treat these as first-class metrics, not “nice to have.” citeturn0search0turn0search1  
- Add **counterfactual artifact intervention tests** (swap/perturb/corrupt artifacts) to directly measure genuine framework use. citeturn0search0turn0search1turn9search0  
- Create **minimal-pair boundary suites** for each framework’s expert distinctions; these are your “unit tests” for conceptual fidelity. citeturn2search1turn9search0  
- Add **metamorphic invariance tests** (paraphrase, reorder, expand/contract) to detect brittle, style-driven behavior. citeturn9search0turn9search1  
- Calibrate any **LLM-as-judge** pipeline with bias mitigations (randomized order, multi-judge, format stripping) and periodic human anchoring. citeturn8search2turn8search0turn4search7  
- In production experiments, randomize **per conversation**, run the required multi-arm comparison, and track a small set of primary outcomes plus diagnostic metrics (token/latency, misfire). citeturn1search18turn10view0turn10view3  
- Version frameworks and require eval gates on every change; re-run suites on model/router upgrades. citeturn10view1turn11view3turn6search14