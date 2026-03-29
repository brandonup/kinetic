# Framework Library Production Review Prompt

You are reviewing a framework library for a production AI product. Your job is to identify major issues only — things that will cause the agent to give users unhelpful, confusing, or actively wrong responses at runtime.

Do not flag: minor wording issues, incomplete trigger coverage, low example quality, or formatting inconsistencies. Flag only issues that will degrade the user experience when a framework is injected.

**Skip any framework that already has a `review_flag` or `review_flags` field — these have been identified in a prior review and are pending manual revision.**

Framework Library: frameworks_index.json

## System Context

Kinetic is a context-rich AI workspace. Users invoke a "Nate B. Jones" agent — a thought leader agent built from Nate's corpus. When a user sends a message, a classifier selects the single best-matching framework from this library and injects it in full into the prompt, alongside the agent's system prompt and RAG-retrieved knowledge chunks.

The injected framework tells the agent how to think about the user's problem — which lens to apply, which steps to follow, which principles to invoke.

What a good injection looks like: The user asks something. The framework tells the agent to apply a named, structured approach. The agent reasons through the user's situation using that approach and gives specific, grounded advice.

What a bad injection looks like: The framework is injected and the agent either (a) produces a generic list-dump the user could have gotten from any LLM, (b) tries to apply a tool that doesn't translate from the author's first-person usage to the agent's advisory role, (c) gives the user instructions for something they should do themselves rather than advice the agent can deliver, or (d) injects irrelevant reasoning that derails the response.

## Your Task

Read the full `frameworks_index.json` file. For each framework (excluding those with a `review_flag` or `review_flags` field), ask: "If this gets injected when a user asks a business/strategy/AI question, does the agent produce a useful response — or does something go wrong?"

Flag only frameworks with one or more of these major defects:

1. **Self-assessment trap**: The framework is written as a checklist or evaluation the user runs on themselves. The agent cannot apply it — it can only read it back to the user as instructions, which is unhelpful.
2. **Literal prompt template**: The framework is a prompt — it gives the user copy-paste instructions to give to an LLM. The agent cannot improve on this; injecting it just makes the agent recite prompt templates at the user.
3. **Process spec, not reasoning tool**: The framework describes how to build a system, run a program, or execute a project. It's a how-to guide, not a reasoning lens. The agent ends up walking the user through implementation steps when they asked for strategic advice.
4. **Classifier magnet / false positive risk**: The `when_to_apply` triggers are so broad that this framework will fire on a wide range of unrelated queries, hijacking the response with an irrelevant lens.
5. **No agent-applicable reasoning**: The framework has no steps, no diagnostic logic, no principles the agent can apply — just vague observations. Injecting it adds nothing; the agent would produce the same response without it.

## Output Format

Return a numbered list. For each flagged framework:

```
[Framework Name]
Defect type: [1–5 from above]
Why it fails at runtime: [1–2 sentences — be specific about what the agent will actually do wrong]
Recommendation: Remove | Rewrite triggers only | Rewrite steps | Flag for manual review
```

If a framework is borderline, err on the side of keeping it. Only flag things you're confident will cause real production problems.

At the end, give a 2-sentence summary of the overall library health.
