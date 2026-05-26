# JTBD — Nate B. Jones Agent

**Status:** Draft
**Last updated:** 2026-05-24
**Owner:** Brandon (CEO)
**Scope:** The Nate B. Jones thought leader agent specifically — not Kinetic platform jobs (see `jobs-to-be-done.md`)

---

## Context

Nate B. Jones is Kinetic's demo thought leader agent and the primary proof-of-concept for the agent feature. He is grounded in Nate B. Jones's published body of work on AI transformation and business strategy. The agent surfaces inside any tool with an MCP connection — Claude, Slack, Codex, WhatsApp, Discord — in the context of whatever the user is already working on.

**Primary value propositions (not framework injection — that is an implementation detail, not the VP):**
- **Functional VP:** Expert-level guidance on AI transformation decisions, grounded in a real practitioner's knowledge — not generic AI advice.
- **Convenience VP:** Persistent and portable. Nate and the context he has about you — your company, your projects, your situation — travels with you across every collaboration surface with an MCP connection (Slack, Claude, Codex, WhatsApp, Discord). No switching apps. No re-explaining context. Available 24/7, mid-task.

---

## Target Personas

Three primary user types — each with a distinct context and pressure profile. Each maps to a separate eval set.

**Persona A — The Founder / Startup CEO** *(Eval A)*
A tech founder or startup CEO making company-level strategic bets on AI. They are navigating decisions where the right answer depends on how AI will shift competitive dynamics over the next 12–24 months. They have no strategy team. They are the decision-maker, and they need expert guidance in the moment — mid-Claude session, mid-document, mid-board prep.

**Persona B — The Business Consultant / Advisor** *(Eval B)*
A consultant or fractional advisor who uses Nate with clients to sharpen advice and outperform peers in their category. Nate is a competitive differentiator — they deliver better answers faster without proportionally more research time. The job is not just "get good advice" but "deliver advice that makes me look sharper than any other consultant in the room."

**Persona C — The SMB Owner** *(Eval C)*
A small business owner — marketing agency, logistics company, law firm, trade business — watching AI erode their competitive position and trying to figure out what it means for their specific business. Less runway than a founder, no strategy team, and they are both the operator and the decision-maker. The question is not abstract: "Will AI take my clients? What do I do before it does?"

---

## Customer Jobs

### Functional Jobs

- Get expert guidance on an AI transformation decision in the context I'm already working in — without switching tools, re-explaining my situation, or waiting for a scheduled call.
- Diagnose whether an AI threat or opportunity is real and what it means for my specific business — not a generic "here's what AI means for your industry" answer.
- Stress-test an assumption I'm building on before I act on it or share it with someone whose opinion matters.
- Get a sharp outside take when I'm too close to the problem to see it clearly.
- Help my clients make better decisions about AI faster than they could without me (consultant persona).

### Social Jobs

- Be perceived as a strategically sharp, forward-looking leader by my team, board, investors, or clients.
- Appear decisive and informed — not reactive, confused, or behind on what's happening with AI.
- Deliver advice that positions me as the consultant who sees around corners better than competitors (consultant persona).

### Emotional Jobs

**Seeking:**
- Clarity and confidence before acting. The feeling of: *"I know how to think about this now."*
- Decisiveness after sitting in ambiguity — especially on decisions where the right answer depends on how AI will develop.

**Avoiding:**
- The fear of making a major strategic error because they misread AI's trajectory.
- The anxiety of feeling exposed in front of a board, investor, or client who has more conviction than they do.
- The paralysis of having too many conflicting inputs and no trusted frame for sorting them.

---

## Pains

### Challenges

- Every current source of strategic advice — consultants, ChatGPT, peers, boards — requires either extensive context-setting or delivers generic advice that could apply to any company.
- There is no expert on AI transformation available on-demand, in context, at the moment the decision is live.
- Advice that doesn't account for their specific company, market, and situation is not actionable — it adds inputs without reducing uncertainty.

### Costliness

- Consultants with real AI transformation expertise are expensive, slow, and unavailable in the moment — engagements take weeks to produce output.
- Reconstructing context every time they want advice (for ChatGPT or a new consultant) is friction that compounds — users give up before they get value.
- Asking peers takes social capital and rarely produces a structured diagnostic.

### Common Mistakes

- Accepting generic AI advice as applicable to their specific situation when it isn't.
- Over-indexing on the opinions of whoever they last talked to rather than stress-testing against a consistent expert frame.
- Making AI strategy decisions reactively (in response to a news cycle or a competitor move) without a diagnostic process.

### Unresolved Problems

- No existing tool combines: AI transformation expertise + persistent knowledge of the user's company context + availability inside their active workflow.
- ChatGPT and Claude are fast but ungrounded in real expert thinking on AI transformation.
- Real consultants know the domain but don't live in Slack or Claude — there's no way to invoke them mid-task.

---

## Gains

### Expectations

- Nate already knows enough about my company and situation to give a specific diagnosis — I don't re-explain every session.
- Nate is available wherever I'm working — I invoke him mid-task, not by opening a separate tool.
- Nate gives me a direct, specific verdict — not a menu of options to consider.

### Savings

- Eliminate the setup cost of every advisory interaction — no briefing, no onboarding, no scheduling.
- Compress a multi-hour consultant engagement into a 5-minute conversation by meeting the user in context.
- Free the consultant (Persona C) from research time — they spend more time delivering value and less time getting smart on the domain.

### Adoption Factors

- Works inside tools the user already uses daily (Slack, Claude, Codex, WhatsApp, Discord) — no new app to adopt.
- Persistent — gets more useful over time as it accumulates context, rather than resetting every session.
- Trusted source — grounded in the real published thinking of Nate B. Jones, not a generic AI persona.

### Life Improvement

- Leaders can move faster on hard decisions without the anxiety of flying blind on AI strategy.
- Consultants can differentiate from peers and deliver visibly better work without proportionally more effort.
- Users stop feeling behind on AI transformation — they have a resource that helps them stay ahead.

---

## Trigger Situations

The moments that most reliably cause a user to invoke Nate:

1. **Mid-decision in Claude or another AI tool** — "I'm trying to decide X and don't know how to think about it given how fast AI is changing."
2. **Mid-collaboration in Slack or a meeting** — A problem surfaces in conversation that has no clear answer because the AI landscape is shifting.
3. **Before a high-stakes conversation** — Prepping for a board meeting, investor call, or client presentation where AI strategy will come up.
4. **After a competitive signal** — A competitor moves on AI, or a new model ships, and the user needs to quickly assess the implications.

---

## What "Hired" vs. "Fired" Looks Like

### Hired when:
The user has tried ChatGPT for the tenth time and gotten advice that could apply to any company in any industry. Or they've paid a consultant who took three weeks to deliver a deck that didn't account for what they're actually dealing with. They realize they need: expert thinking + their context + right now.

### Fired when:
Nate gives a response that is generic, hedged, or indistinguishable from a default ChatGPT answer. Or Nate requires the user to re-explain their company and situation before giving anything useful. Or Nate sounds like a textbook — citing a framework rather than diagnosing the situation.

---

## Eval Design Notes (for Jìan)

Three separate eval sets, one per persona. Each has a distinct trigger, pressure profile, and success bar.

| Eval | Persona | Primary trigger | Pass bar |
|---|---|---|---|
| Eval A | Founder / CEO | Strategic AI decision mid-work session | Specific verdict grounded in their company context; challenges the assumption they came in with |
| Eval B | Business Consultant | Client-facing advisory moment | Sharper and more specific than a generalist AI would produce; could be delivered directly to a client |
| Eval C | SMB Owner | "Is AI going to hurt my business and what do I do?" | Concrete, actionable guidance for their specific business type — not industry-generic platitudes |

**Shared pass/fail bar (all three evals):**
1. Does not require the user to re-explain context Kinetic already has
2. Gives a specific verdict — not a menu of considerations, not "it depends"
3. Sounds like Nate — direct, opinionated, no hedging, no filler
4. Reflects real AI transformation expertise — not generic AI-speak

The agent fails when a user could have gotten the same response from a generic ChatGPT prompt with no context injected.

**Test memory bank (V1 evals):**
Brandon's Claude Projects will serve as the test company/project memory bank for all eval runs. This is the stand-in for Kinetic's persistent context until a dedicated sync feature ships.

---

## Open Questions

1. What specific test cases and prompts map to each of the three eval sets? (Jìan to design, per persona.)
2. What is the minimum context Kinetic must have about a user's company before Nate is meaningfully better than ChatGPT? This threshold needs to be defined and communicated to users at onboarding. Requires a new feature: sync from Google Drive, Claude/GPT project, or another MCP-connected source. **Deferred post-MVP.**
