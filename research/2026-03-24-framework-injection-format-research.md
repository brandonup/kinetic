# Injecting Structured Domain Knowledge into LLM Context: Optimal Format for Advisory Reasoning

**Research synthesis for Monica | 2026-03-24**

---

## Key Findings

### 1. Hybrid formats outperform any single format — but the hybrid must be carefully composed

No single format (declarative assertions, procedural steps, worked examples, or decision trees) consistently dominates across models and tasks. The evidence points toward **layered hybrids** as the highest-performing approach for advisory reasoning:

- **Natural language outperforms structured formats (JSON, YAML, XML) for reasoning tasks specifically.** The paper "Does Prompt Formatting Have Any Impact on LLM Performance?" (Salewski et al., 2024) found that natural language produced better reasoning than constrained structured formats, with the notable exception of GPT-3.5-Turbo. Larger models (GPT-4 class) are more robust to format variation but still favor natural language for reasoning. [arxiv.org/html/2411.10541v1](https://arxiv.org/html/2411.10541v1)

- **Format constraints degrade reasoning.** "Let Me Speak Freely?" (Ren et al., 2024) demonstrated that strict format restrictions (JSON-mode, constrained decoding) significantly degrade reasoning performance. The degradation is worse with stricter constraints. The recommended mitigation is a two-step approach: reason in natural language first, then convert to structured format. This has a direct implication for framework injection — the framework itself should be in natural language or light markup, not rigid schema. [arxiv.org/abs/2408.02442](https://arxiv.org/abs/2408.02442)

- **TMK (Task-Method-Knowledge) is the strongest empirical result for injected reasoning frameworks.** A 2025 paper from Georgia Tech found that injecting TMK-structured knowledge models into prompts increased planning accuracy from 31.5% to 97.3% on symbolic tasks. TMK provides three layers: *what* the task is, *how* to accomplish it (method), and *why* each step matters (knowledge/rationale). The key finding: TMK works not merely as context but as a mechanism that steers the model away from default linguistic modes into more formal reasoning pathways. [arxiv.org/abs/2602.03900](https://arxiv.org/abs/2602.03900)

### 2. Procedural + teleological (the "why") beats pure procedural or pure declarative

- **Declarative assertions alone underperform procedural guidance for complex tasks.** Research comparing declarative and procedural knowledge in LLMs (ACL 2024) found that procedural scores exceed declarative scores on mathematical reasoning tasks (GSM8K, MultiArith), while declarative knowledge is stronger for factual recall. For advisory reasoning — which requires the model to *apply* frameworks, not just *know* them — procedural formats are more effective. [aclanthology.org/2024.lrec-main.980](https://aclanthology.org/2024.lrec-main.980.pdf)

- **The critical addition is teleological structure — explaining *why* each step exists.** The TMK research found that unlike other hierarchical frameworks (HTN, BDI), TMK's explicit representation of *why* actions are taken is what drives the performance gain. Pure procedural steps without rationale leave the model guessing about when to deviate or adapt. This is directly relevant to advisory frameworks: a diagnostic model should encode not just "ask about X" but "ask about X *because* it distinguishes condition A from condition B." [arxiv.org/html/2602.03900](https://arxiv.org/html/2602.03900)

### 3. Worked examples remain powerful but have diminishing returns for complex multi-step reasoning

- **Few-shot (worked examples) consistently outperforms zero-shot for moderately complex tasks.** This is well-established across the literature (Wei et al., 2022; Brown et al., 2020). More examples improve accuracy and consistency up to a point. [arxiv.org/abs/2201.11903](https://arxiv.org/abs/2201.11903)

- **For truly complex reasoning, zero-shot CoT can match or exceed few-shot.** Modern reasoning models (o3, Claude with extended thinking) are strong enough that zero-shot chain-of-thought ("think step by step") often matches few-shot CoT. This suggests that for advisory reasoning, *one or two* worked examples are valuable for calibrating the model's application of the framework, but saturating the context with many examples yields diminishing returns and wastes context budget. [machinelearningmastery.com](https://machinelearningmastery.com/zero-shot-and-few-shot-learning-with-reasoning-llms/)

- **The optimal pattern for advisory frameworks: 1-2 worked examples showing framework application, combined with the procedural/teleological framework itself.** The examples serve as calibration — showing the model what "good application" looks like — while the framework provides the reasoning scaffold.

### 4. Prompt specificity improves reasoning, but over-specification constrains it

- **The "DETAIL Matters" paper (2024) found that increased prompt specificity improves accuracy, especially for smaller models and procedural tasks.** However, the relationship is non-linear: very detailed prompts can constrain the model's reasoning pathways. The optimal point depends on model capability — more capable models need less specification. [arxiv.org/abs/2512.02246](https://arxiv.org/abs/2512.02246)

- **Anthropic's guidance aligns: aim for the "Goldilocks" balance.** Overly specific prompts with complex if-else logic become brittle; vague guidance fails to give concrete signals. The optimal prompt is specific enough to guide behavior but flexible enough to let the model use its intelligence. [anthropic.com/engineering/effective-context-engineering-for-ai-agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

### 5. Voice and addressee matter — but not in the way you might expect

- **Second-person instructions to the model ("You should...") are the standard and well-supported format.** Modern instruction-tuned LLMs are trained on user/assistant turn-based conversations, and structuring content to align with this paradigm improves performance.

- **Expert persona assignment helps with style and structure but does NOT improve factual accuracy.** A large-scale study of 162 personas across multiple LLM families (PRISM, 2025) found that expert personas improve alignment-dependent tasks (style, tone, structured formatting, reasoning *approach*) but reliably damage accuracy on pretraining-dependent knowledge retrieval. For advisory frameworks, this means: persona framing can help the model *adopt* a framework's reasoning style, but the framework's actual knowledge content must be explicit — don't rely on the persona to supply domain knowledge. [arxiv.org/html/2603.18507](https://arxiv.org/html/2603.18507)

- **Impersonal assertions ("The diagnostic model states...") function as reference material the model may or may not engage with. Direct instructions ("When the user describes X, apply framework Y by...") are more reliably followed.** This is consistent across Anthropic and OpenAI guidance — instructions addressed to the model produce more predictable behavior than passive knowledge dumps.

- **Aggressive/emphatic language ("CRITICAL!", "YOU MUST", "NEVER EVER") actively hurts newer Claude models.** Calm, direct instructions produce measurably better results. [thomas-wiegold.com](https://thomas-wiegold.com/blog/prompt-engineering-best-practices-2026/)

### 6. Context positioning is critical — the "Lost in the Middle" effect is real and large

- **Performance degrades by 20-30% when relevant information is in the middle of the context window.** Liu et al. (2023) demonstrated a U-shaped attention curve: models attend most to the beginning and end of context, with significant degradation for middle-positioned information. This is caused by rotary position embedding (RoPE) decay. [arxiv.org/abs/2307.03172](https://arxiv.org/abs/2307.03172)

- **For injected frameworks: place the framework definition and core reasoning scaffold at the beginning of the system prompt (primacy position). Place worked examples and application instructions near the end (recency position). Avoid burying critical framework components in the middle of long context windows.** This is the single most actionable structural finding.

### 7. Context rot means less is more — tighter frameworks outperform comprehensive ones

- **Every frontier model tested shows continuous performance degradation as input token count increases.** Chroma's "Context Rot" research (2025) tested 18 models and found universal degradation, with more severe effects on complex multi-step reasoning tasks. The "effective context window" where models perform well is often far smaller than the advertised limit. [research.trychroma.com/context-rot](https://research.trychroma.com/context-rot)

- **Reasoning performance starts degrading around 3,000 tokens, with 150-300 words as a practical sweet spot for most tasks** (Levy, Jacoby & Goldberg, 2024). This is a severe constraint for framework injection: a 5,000-word framework encyclopedia will actively hurt reasoning quality compared to a 300-word distilled version.

- **Anthropic's core principle: find the smallest possible set of high-signal tokens that maximize the likelihood of the desired outcome.** For frameworks, this means aggressive compression — every sentence should earn its token cost.

### 8. Cognitive scaffolding architectures show promise but are early-stage

- **The "Fuzzy, Symbolic, and Contextual" paper (2025) proposes a three-layer scaffolding architecture:** (1) Boundary Prompt for domain knowledge definition, role framing, and scaffolding policy; (2) Fuzzy Schema for decisions under uncertainty; (3) Symbolic Memory Schema for session tracking. Removing any layer degrades key cognitive behaviors including abstraction, adaptive probing, and conceptual continuity. [arxiv.org/abs/2508.21204](https://arxiv.org/abs/2508.21204)

- **Multi-dimensional reasoning prompts based on cognitive architecture significantly change reasoning model behavior** when the prompt structures encode multiple reasoning dimensions simultaneously (e.g., causal + temporal + stakeholder analysis). [discuss.huggingface.co](https://discuss.huggingface.co/t/make-your-llm-think-differently-multi-dimensional-reasoning-prompts/159175)

### 9. Injected scaffolds interact with — and can redirect — the model's own chain-of-thought

- **Thinking Intervention research (2025) demonstrates that strategically inserted reasoning tokens can redirect LLM reasoning processes,** achieving up to 6.7% accuracy gains in instruction-following and 40% increases in refusal rates for unsafe prompts. The key mechanism: injected structure doesn't just *inform* the model, it *steers* which reasoning pathways activate. [arxiv.org/html/2503.24370v3](https://arxiv.org/html/2503.24370v3)

- **TMK prompting specifically steers reasoning models away from default linguistic/heuristic modes toward formal reasoning pathways.** This is the most important interaction effect: a well-structured injected framework doesn't compete with the model's CoT — it *shapes* the CoT by providing a reasoning skeleton the model then elaborates.

- **The NL-to-Format two-step pattern applies here too:** let the model reason freely using the injected framework as scaffolding, then structure the output separately. Don't force structured output during the reasoning phase.

### 10. XML tags (Claude) and Markdown headers (GPT) improve structural parsing

- **Anthropic specifically recommends XML tags for Claude** (e.g., `<framework>`, `<diagnostic_steps>`, `<examples>`) — Claude is tuned to attend to XML structure. [docs.anthropic.com](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview)

- **GPT-4 class models favor Markdown headers** for section delineation. [arxiv.org/html/2411.10541v1](https://arxiv.org/html/2411.10541v1)

- **Both approaches serve the same function: creating unambiguous semantic boundaries** between different types of injected content (framework definition vs. application instructions vs. examples vs. constraints). The key principle is clear delineation, not the specific syntax.

---

## Implications for Framework Injection Format

Based on the evidence, the optimal format for injecting a cognitive/diagnostic framework into an LLM's context for advisory reasoning is:

### Recommended Structure (in priority order within the context)

**1. Framework Identity and Purpose (beginning of context — primacy position)**
- 1-3 sentences: what this framework is, when it applies, what it produces
- Written as direct instruction to the model: "You use the [Framework Name] to..."
- Keep under 100 words

**2. Procedural Scaffold with Teleological Annotations (immediately after)**
- Numbered steps showing the reasoning procedure
- Each step annotated with *why* it matters (the TMK "knowledge" layer)
- Format: natural language with light markup (XML tags for Claude, Markdown headers for GPT)
- Keep under 300 words total
- Example pattern:
  ```
  Step 1: [Action]. This matters because [rationale — what it distinguishes or reveals].
  Step 2: [Action]. This matters because [rationale].
  ```

**3. Decision Logic (if applicable)**
- Conditional branching expressed in natural language, not formal decision tree notation
- "If [condition], then [path] because [reason]"
- Avoid deep nesting — flatten to 2 levels max
- Keep under 200 words

**4. 1-2 Worked Examples (near end of context — recency position)**
- Show the framework applied to a realistic case
- Include the reasoning process, not just the input/output
- These calibrate the model's understanding of "what good application looks like"
- Keep each example under 200 words

**5. Output Expectations (end of context — recency position)**
- What the advisory output should contain
- Quality criteria the model should self-check against

### Anti-Patterns to Avoid

- **Encyclopedic framework dumps** — context rot means 5,000 words of framework detail will actively degrade reasoning quality
- **Rigid structured formats (JSON/YAML)** — they degrade reasoning compared to natural language
- **Impersonal knowledge-base style** ("The framework defines X as...") — direct instructions are more reliably followed
- **Many worked examples** (5+) — diminishing returns; 1-2 high-quality examples is optimal
- **Critical content in the middle** of long system prompts — it will be under-attended
- **Aggressive/emphatic language** — newer models respond worse to CAPS and exclamation marks
- **Over-specification** — highly detailed if-else logic becomes brittle; trust the model to apply the framework intelligently given clear principles

### Token Budget Guideline

Based on the context rot research, the total injected framework (all sections combined) should target **500-800 words** (roughly 700-1,100 tokens) for optimal reasoning quality. This is aggressive compression, but the evidence strongly supports it: a concise, well-structured 600-word framework injection will produce better advisory reasoning than a comprehensive 3,000-word version.

---

## Open Questions / Insufficient Evidence

1. **No direct A/B testing of framework injection formats exists.** The TMK paper is the closest, but it tests planning tasks, not open-ended advisory reasoning. No published research specifically compares formats for injecting diagnostic/advisory frameworks. The recommendations above are synthesized from adjacent findings.

2. **Model-specific tuning effects are under-documented.** Claude is tuned to attend to XML structure; GPT-4 favors Markdown. But whether these preferences extend to *reasoning scaffold* content (not just structural parsing) is untested.

3. **Interaction between framework injection and extended thinking / reasoning models is barely studied.** The TMK paper tested with reasoning models and found the scaffold *redirects* reasoning pathways, but the mechanism is not well understood. It is unclear whether reasoning models (o3, Claude with extended thinking) benefit more or less from injected frameworks compared to standard models.

4. **Optimal example count for advisory tasks specifically is not empirically established.** The "1-2 examples" recommendation is extrapolated from general few-shot research. Advisory reasoning may benefit from more examples that show framework application across diverse problem types.

5. **Context rot thresholds vary by model and are continuously shifting** as architectures improve. The 3,000-token degradation onset finding may not hold for the latest models. The safe recommendation is to keep frameworks tight regardless, but the precise budget is uncertain.

6. **The voice/addressee question lacks controlled experiments.** The recommendation for direct model-addressed instructions is based on practitioner consensus and alignment with instruction-tuning paradigms, not on published comparisons of "instruct the model" vs. "instruct the user" vs. "impersonal assertion" for the same content.

7. **Multi-framework interaction is unstudied.** If an advisory agent uses multiple cognitive frameworks, how they should be organized relative to each other (sequentially? conditionally? hierarchically?) has no published guidance.

8. **Dynamic framework selection vs. static injection is an open design question.** Should all frameworks be in the system prompt, or should a retrieval layer select the relevant framework per query? The context rot research argues for the latter, but the latency and accuracy tradeoffs are undocumented for advisory use cases.

---

## Sources

### Research Papers
- [Does Prompt Formatting Have Any Impact on LLM Performance? (Salewski et al., 2024)](https://arxiv.org/html/2411.10541v1)
- [Let Me Speak Freely? A Study on the Impact of Format Restrictions on Performance of LLMs (Ren et al., 2024)](https://arxiv.org/abs/2408.02442)
- [Knowledge Model Prompting Increases LLM Performance on Planning Tasks (TMK paper, 2025)](https://arxiv.org/abs/2602.03900)
- [Lost in the Middle: How Language Models Use Long Contexts (Liu et al., 2023)](https://arxiv.org/abs/2307.03172)
- [Chain-of-Thought Prompting Elicits Reasoning in Large Language Models (Wei et al., 2022)](https://arxiv.org/abs/2201.11903)
- [DETAIL Matters: Measuring the Impact of Prompt Specificity on Reasoning (2024)](https://arxiv.org/abs/2512.02246)
- [Fuzzy, Symbolic, and Contextual: Enhancing LLM Instruction via Cognitive Scaffolding (2025)](https://arxiv.org/abs/2508.21204)
- [Effectively Controlling Reasoning Models through Thinking Intervention (2025)](https://arxiv.org/html/2503.24370v3)
- [Expert Personas Improve LLM Alignment but Damage Accuracy — PRISM (2025)](https://arxiv.org/html/2603.18507)
- [Evaluating Declarative and Procedural Knowledge in LLMs (ACL 2024)](https://aclanthology.org/2024.lrec-main.980.pdf)
- [Enhancing Chain of Thought Prompting via Reasoning Patterns (2024)](https://arxiv.org/html/2404.14812v2)
- [Context Rot: How Increasing Input Tokens Impacts LLM Performance (Chroma, 2025)](https://research.trychroma.com/context-rot)
- [Cognitive Foundations for Reasoning and Their Manifestation in LLMs (2025)](https://arxiv.org/html/2511.16660v1)
- [Why Prompt Design Matters and Works: A Complexity Analysis (ACL 2025)](https://www.atailab.cn/seminar2025Spring/pdf/2025_ACL_Why%20Prompt%20Design%20Matters%20and%20Works%20A%20Complexity%20Analysis%20of%20Prompt%20Search%20Space%20in%20LLMs.pdf)
- [When "A Helpful Assistant" Is Not Really Helpful: Personas in System Prompts (2024)](https://www.researchgate.net/publication/386182602_When_A_Helpful_Assistant_Is_Not_Really_Helpful_Personas_in_System_Prompts_Do_Not_Improve_Performances_of_Large_Language_Models)

### Official Documentation and Guides
- [Anthropic: Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Anthropic: Prompting Best Practices (Claude API Docs)](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview)
- [Anthropic: Long Context Prompting Tips](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/long-context-tips)
- [OpenAI: Prompt Engineering Guide](https://platform.openai.com/docs/guides/prompt-engineering)
- [OpenAI: GPT-4.1 Prompting Guide](https://cookbook.openai.com/examples/gpt4-1_prompting_guide)
- [OpenAI: GPT-5 Prompting Guide](https://cookbook.openai.com/examples/gpt-5/gpt-5_prompting_guide)
- [Palantir: Best Practices for LLM Prompt Engineering](https://www.palantir.com/docs/foundry/aip/best-practices-prompt-engineering)

### Practitioner Sources and Guides
- [Context Engineering Guide (Prompting Guide)](https://www.promptingguide.ai/guides/context-engineering-guide)
- [Deepset: Context Engineering — The Next Frontier Beyond Prompt Engineering](https://www.deepset.ai/blog/context-engineering-the-next-frontier-beyond-prompt-engineering)
- [FlowHunt: Context Engineering — The Definitive 2025 Guide](https://www.flowhunt.io/blog/context-engineering/)
- [Thomas Wiegold: Prompt Engineering Best Practices 2026](https://thomas-wiegold.com/blog/prompt-engineering-best-practices-2026/)
- [Prompt Engineering Guide: Reasoning LLMs](https://www.promptingguide.ai/guides/reasoning-llms)
- [Zero-Shot and Few-Shot Learning with Reasoning LLMs (MachineLearningMastery)](https://machinelearningmastery.com/zero-shot-and-few-shot-learning-with-reasoning-llms/)
- [Claude Agent Skills: A First Principles Deep Dive](https://leehanchung.github.io/blogs/2025/10/26/claude-skills-deep-dive/)
