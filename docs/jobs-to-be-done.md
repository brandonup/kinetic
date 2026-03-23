# Kinetic — Jobs to Be Done

**Status:** Draft
**Last updated:** 2026-03-21
**Owner:** Brandon (CEO)

---

## How to Read This Doc

Each job follows the format:
> **When** [trigger situation], **I want** [action or capability], **so I can** [outcome that matters].

Jobs are organized by category. Each includes a brief note on why it's important to the product.

---

## 1. Decision-Making Under Uncertainty

**JOB-01**
When I'm facing an important decision with incomplete information, I want the key facts, tradeoffs, and risks specific to my situation surfaced clearly, so I can make a sound decision without getting stuck in analysis paralysis.

> The AI knowing my company, constraints, and history is what makes this useful — generic pros/cons lists aren't.

---

**JOB-02**
When I need to make a time-sensitive call, I want to pressure-test my instinct against my own goals, constraints, and past decisions, so I can move with confidence rather than second-guessing myself.

> This is the "sanity check" job. The value is in Kinetic already knowing the context so the user doesn't have to reconstruct it under pressure.

---

**JOB-03**
When a decision has significant downstream consequences, I want to stress-test it by thinking through failure modes and second-order effects relevant to my situation, so I don't discover the flaw after I've committed.

> Pre-mortem thinking, grounded in the user's actual project and company context.

---

## 2. Problem Diagnosis & Root Cause

**JOB-04**
When a problem keeps resurfacing across projects, teams, or workflows, I want the underlying pattern or root cause identified, so I can solve the real issue instead of treating symptoms.

> Requires memory across projects — Kinetic's persistent project memory and agent thought stream (with opt-in cross-company retrieval) make this possible over time.

---

**JOB-05**
When something isn't working and I can't articulate why, I want a structured diagnostic that draws on my full context, so I can name the problem precisely and stop spinning.

> The "I know something's wrong but I don't know what" job. Especially valuable for founders who are close to the problem.

---

**JOB-06**
When I'm troubleshooting a complex situation with multiple contributing factors, I want help separating signal from noise and ranking causes by likely impact, so I can focus effort where it will move the needle.

---

**JOB-07**
When I'm evaluating a client's company or project, I want help identifying unrecognized problems and blind spots the client may not be aware of, so I can proactively pitch solutions and deliver more value.

> The consultant's "find hidden problems" job. Requires deep company and project context to surface non-obvious issues.

---

## 3. Strategy & Planning

**JOB-08**
When I'm evaluating possible paths forward, I want help from trusted perspectives comparing options against my goals, constraints, and past decisions, so I can choose the best course of action with confidence.

> The comparison only has teeth when it's grounded in the user's actual situation — not hypothetical examples.

---

**JOB-09**
When I'm starting a new initiative, I want a strategy built on what I know about my company, market, and how I think — not generic frameworks — so I can move with a plan that actually fits my situation.

> The "blank page" problem. Users have context; they need it activated and organized into a coherent plan.

---

**JOB-10**
When I'm planning a project, I want to think through scope, dependencies, risks, and sequencing in light of my current constraints and capacity, so I don't build a plan that collapses on contact with reality.

> Especially valuable for consultants managing multiple client engagements simultaneously.

---

## 4. Thinking With Trusted Perspectives

**JOB-11**
When I'm stuck on a hard problem, I want to invoke the perspective of a thinker I trust — grounded in their actual reasoning, not a generic impression — so I can break through my blind spots and see the problem differently.

> The thought leader agent feature is the primary delivery mechanism. This job validates why that feature matters.

---

**JOB-12**
When I'm making a judgment call in a domain where I have a trusted expert in mind, I want to ask "how would [person] approach this?" and get a grounded answer, so I can benefit from their thinking without guessing.

> Distinct from JOB-11 — this is about applying a specific person's decision logic, not just their worldview.

---

**JOB-13**
When I'm challenging my own thinking, I want a devil's advocate perspective that argues the opposite case with the same intelligence and context I have, so I can find the holes in my reasoning before they find me.

> A dedicated "challenger" agent persona — this job motivates the value of multiple different agents.

---

## 5. Context Continuity & Memory

**JOB-14**
When I return to a project after time away, I want to pick up exactly where I left off — with full context about decisions made, constraints, and open questions — so I don't waste time reconstructing what I already knew.

> The "Monday morning" job. Core to Kinetic's memory system justification. Active Memory + Thought Stream together ensure nothing is lost.

---

**JOB-15**
When I start a new work session, I want my AI to already know who I am, what I'm working on, and what matters to me, so every interaction starts from intelligence rather than scratch.

> The zero cold-start promise. This is the job that the entire context stack is built to serve.

---

**JOB-16**
When something important happens in a project — a decision, a change in direction, a new constraint — I want it captured in a way that future sessions will automatically know about, so my AI stays current without me having to manually maintain it.

> The memory write job. The Thought Stream handles intake; the Active Memory promotion loop handles curation. The answer must feel effortless.

---

## 6. Multi-Company & Context Switching

**JOB-17**
When I switch between clients or companies, I want to carry my personal context and agent library with me while keeping company-specific information cleanly separated, so I can context-switch fast without mixing or losing anything.

> The core multi-company job. Motivates the active company switcher in the UI. Structural scoping (company_id, project_id) on the Thought Stream ensures isolation.

---

**JOB-18**
When I spot a pattern or lesson from one engagement that applies to another, I want to apply that insight without cross-contaminating confidential context, so I can deliver better work across my portfolio without taking risks.

> A nuanced, high-value job for consultants. Agent Instance memory carries lessons across companies; cross-company Thought Stream retrieval is opt-in per query, not default.

---

## 7. Knowledge Synthesis

**JOB-19**
When I have a large body of inputs — research, notes, transcripts, articles — I want the key insights, tensions, and implications synthesized relative to my specific goals and context, so I can act on them without drowning in content.

> Motivates the Knowledge Base / RAG feature beyond just thought leader agents.

---

**JOB-20**
When I'm trying to form an opinion on a topic I don't fully understand, I want a clear briefing that draws on both my uploaded sources and my company context, so I can hold an informed position fast.

> The "get me up to speed" job. Particularly valuable for founders moving across multiple domains simultaneously.

---

## 8. Communication & Output Preparation

**JOB-21**
When I need to communicate a complex decision or strategy to stakeholders, I want help crafting a message that is clear, compelling, and grounded in our actual context, so I can land the idea without losing nuance.

> Outputs (docs, emails, decks) created in-project benefit from the full context stack automatically.

---

**JOB-22**
When I'm preparing for a high-stakes meeting or conversation, I want to think through the key points, likely pushback, and my position — grounded in my full context — so I walk in sharp rather than scrambling.

> "Prep me for this meeting" is a high-frequency, high-value use case that requires knowing the company, project, and any relevant prior decisions.

---

## 9. Ambient Capture & Productivity

**JOB-23**
When I meet with a client and save the transcript, I want deliverables, due dates, and action items automatically extracted and added to my to-do list, so nothing falls through the cracks.

> The auto-extraction job. Requires meeting transcript intake → Thought Stream → structured extraction. Phase 2 dependency: calendar integration for due dates.

---

**JOB-24**
When I have a quick idea, task, or reminder on the fly, I want to send it to Kinetic through any channel — email, the UI, or an external AI tool — and have it stored under the appropriate client and project, so I can capture without breaking my flow.

> The ambient capture job. The Thought Stream's intake channels and auto-routing (with inbox triage for unscoped items) are the delivery mechanism.

---

**JOB-25**
Before I meet with a client again, I want a summary of what I need to remember, what I need to prepare, and any personal relationship context — so I walk in informed without reviewing everything manually.

> The pre-meeting briefing job. Requires: Contact entity (relationship notes), Thought Stream (recent context), Active Memory (key facts), calendar integration (knowing the meeting is happening). Phase 2 dependency: calendar integration for automatic trigger.

---

**JOB-26**
When I onboard a new client, I want to set up their full context quickly — company details, key contacts, initial project scope, relevant documents — so I can start getting value from Kinetic immediately rather than after weeks of manual setup.

> The consultant onboarding job. Motivates auto-generation of company context from uploaded docs, bulk contact import, and project scaffolding.

---

## 10. Client Relationship Management

**JOB-27**
When I'm interacting with a client contact, I want personal context about them — their role, communication style, family details they've shared, recent conversations — surfaced automatically, so every interaction feels informed and personal.

> The relationship context job. Delivered via the Contact entity + Thought Stream entries tagged with contact_id. "Ask about her son's baseball game" is the canonical example.

---

**JOB-28**
When I'm looking for new business opportunities within an existing client, I want help identifying unaddressed problems, expansion areas, or follow-on projects based on my full engagement history, so I can grow the relationship proactively.

> The business development job for consultants. Requires cross-project context within a company — Thought Stream + Active Memory across all projects for that client.

---

## Priority Signal

Jobs most central to Kinetic's core value proposition and hardest to replicate without Kinetic's context architecture:

| Priority | Job | Why It's Core |
|---|---|---|
| 1 | JOB-15 — Zero cold-start | The foundational promise of the product |
| 2 | JOB-01 — Decision with incomplete info | High-frequency, high-stakes, context-dependent |
| 3 | JOB-11 — Trusted perspective on demand | Unique to Kinetic's thought leader agent feature |
| 4 | JOB-14 — Pick up where you left off | Memory system justification; compounds over time |
| 5 | JOB-17 — Context switching | Core to the consultant/founder use case |
| 6 | JOB-24 — Ambient capture on the fly | Thought Stream differentiator; low-friction context building |
| 7 | JOB-16 — Effortless memory maintenance | Three-tier memory + promotion loop = the answer |
| 8 | JOB-25 — Pre-meeting briefing | High-frequency consultant job; requires Contact + Thought Stream + calendar |

---

## Open Questions

1. Do any of these jobs suggest agent archetypes we should design for explicitly — e.g., a "Devil's Advocate" agent, a "Strategist" agent, a "Researcher" agent as defaults?
2. Which jobs are table stakes (users expect them) vs. jobs where Kinetic has a genuine edge worth highlighting in positioning?
3. Should JOB-26 (client onboarding) support auto-generation of company context from uploaded docs (e.g., upload a business plan → extract structured fields)? This would be a significant V1 feature addition.
4. How does JOB-25 (pre-meeting briefing) work in V1 without calendar integration? Can it be manually triggered ("brief me for my meeting with Client X")?
