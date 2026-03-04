# Kinetic Intelligence Layer — Design Document

**Date:** March 2026
**Status:** Approved
**Author:** Brandon Upchurch

---

## What the Intelligence Layer Is

The Intelligence Layer is Kinetic's primary differentiator and the foundation of the entire platform. It is not a feature — it is a design principle that transforms every AI-generated output in Kinetic.

Most AI tools help users do things faster. The Intelligence Layer changes what users are *aware of*, what they *question*, and how they *think*. It expands cognitive capacity in seven specific ways — and these seven capabilities are embedded in every system prompt, every agent, every output structure, and every interaction Kinetic produces.

**This is what makes Kinetic a co-pilot, not a tool.**

---

## The Seven Capabilities

### 1. Pattern Recognition
**Seeing what's actually there across fragmented information.**

Kinetic widens the user's aperture by detecting patterns across all connected sources that no human could reasonably hold in their head. A pain point mentioned by Client A connects to a trend from an article ingested last week and a lesson learned from Client B three months ago. These connections are surfaced automatically — not just when asked for.

**Where it manifests:**
- Post-Meeting Agent: scans other clients for cross-client pattern matches after every meeting
- Weekly Review: "Emerging Patterns" section surfaces themes across recent meetings and knowledge
- Knowledge Relevance Agent: links new knowledge items to active client pain points
- `patterns` table: stores detected patterns as first-class data with source references

### 2. Generative Questioning
**Asking what you wouldn't think to ask.**

The most underrated form of intelligence isn't having answers — it's asking the right questions. The best advisors, partners, and mentors earn their value not by telling you what to do, but by asking the question you didn't know you needed to ask. Kinetic generates these questions proactively in every major output.

**Where it manifests:**
- Meeting Prep Briefs: "Questions You Haven't Asked" section — non-obvious questions generated from client context, knowledge gaps, and pattern analysis
- Post-Meeting Summaries: "What This Conversation Didn't Address" — gaps between what was discussed and what client goals/pain points suggest should have been
- Morning Briefing: "One Question Worth Asking" per meeting
- Weekly Review: "This Week's Uncomfortable Question" about the practice itself
- Chat Interface: when asked for recommendations, also surfaces the questions worth investigating first
- Shared prompt instruction: every synthesis output includes at least one generative question

### 3. Perspective Shifting
**Thinking from angles you wouldn't naturally take.**

Many consultants get trapped in their own frame — their role, their assumptions, their habitual way of seeing problems. Kinetic can model other perspectives because it has access to enough context about stakeholders, clients, and competitors to simulate how they might think.

**Where it manifests:**
- Meeting Prep Briefs: "How [Stakeholder] Might See This" section — perspective simulation grounded in stakeholder context from meetings and client memory
- Chat Interface: on-demand perspective simulation ("How would the CFO see this?", "What would a competitor argue?")
- Pre-Meeting Research Agent: "How this news might affect what [Contact] cares about"
- Client CLAUDE.md: instructions to consider stakeholder perspectives when helping with deliverables
- Requires: enough stakeholder data from meetings (works better after 2-3 meetings per client)

### 4. Counterfactual & Scenario Reasoning
**Exploring what could be — and what could go wrong.**

Most people think linearly: "If we do X, then Y." Kinetic enables branching exploration of multiple futures simultaneously, grounded in the user's actual data and constraints.

**Where it manifests:**
- Chat Interface: on-demand scenario exploration ("What if their budget gets cut?", "What happens if we pursue strategy A vs B?") — grounded in client context, not generic
- Client Context Dashboard: "Scenario Explorer" action — generate branching scenarios from current client state
- Recommendation Engine Agent: when generating recommendations, includes "If this doesn't work" contingency reasoning
- Weekly Review: "Scenarios Worth Considering" when significant client changes are detected
- This is primarily interactive (user-initiated), not passive — counterfactual reasoning without a specific trigger produces noise

### 5. Temporal Intelligence
**Connecting past, present, and future in ways humans can't.**

Humans have weak temporal reasoning. We forget what we said 3 months ago, we don't notice gradual shifts, and we're bad at predicting how current actions compound over time. Kinetic bridges these temporal gaps by reasoning across the full timeline of client interactions.

**Where it manifests:**
- Meeting Prep Briefs: "What's Changed Since Last Meeting" — compare current client memory to state at time of previous meeting, highlight shifts in goals, priorities, or concerns
- Weekly Review: "Gradual Shifts You Might Not Notice" — detect drift in client goals, relationship tone, or market positioning over 4+ week windows
- Post-Meeting Agent: when updating client memory, flag if new information contradicts or significantly updates prior memory entries
- Practice Memory: `drift_detected` memory type — stored when the system identifies a significant gradual shift
- Temporal comparison uses timestamps on existing client_memory entries — no new infrastructure needed, just chronological querying and comparison prompts
- Needs 30+ days of data before temporal comparisons are meaningful

### 6. Synthesis Under Complexity
**Compressing complexity into clarity.**

The highest-value form of intelligence isn't having more information — it's having the right mental model. When dealing with a complex situation involving multiple stakeholders, conflicting data, and uncertain outcomes, Kinetic can compress that into the essential structure.

**Where it manifests:**
- Shared prompt instruction: every synthesis output ends with a "Bottom Line" — 2-3 sentences that compress the essential structure
- Meeting Prep Briefs: "The Essential Situation" header — a compressed mental model of where things stand with this client
- Chat Interface: when asked to synthesize, produces both a detailed view and a compressed model
- Weekly Review: "The State of the Practice" — one-paragraph compression of where things stand across all clients and pipeline
- Synthesis Agent (Tier 3, #45): consolidated "state of knowledge" summaries per topic or client industry
- Client Context Dashboard: "Situation Summary" — auto-generated, auto-updated compression of the client's full context

### 7. Intellectual Honesty Engine
**Showing you what you don't want to see.**

This is the hardest capability and potentially the most valuable. Kinetic surfaces uncomfortable truths grounded in the user's own data — not as criticism, but as awareness that enables better decisions.

**Where it manifests:**
- Assumption Tracking: Post-Meeting Agent extracts assumptions stated or implied in meetings → stored as client_memory with type `assumption`
- Meeting Prep Briefs: "Assumptions at Risk" — checks tracked assumptions against recent evidence (meetings, knowledge items, company news) for contradictions
- Weekly Review: "What You Might Be Avoiding" — identifies neglected clients, unaddressed objections, or patterns you haven't acted on
- Morning Briefing: "Assumption to Revisit Today" — picks one tracked assumption with recent contradicting evidence
- Chat Interface: "Challenge my thinking on [topic]" — reviews tracked assumptions + evidence to provide specific, grounded pushback
- Follow-Up Quality Agent: flags when a follow-up message avoids addressing a known concern or objection
- This capability requires tracked data (assumptions, meeting history) to be specific rather than vague — generic "have you considered..." pushback is low value

---

## Integration Mechanisms

The Intelligence Layer integrates into Kinetic through four practical mechanisms:

### Mechanism 1: Shared Prompt Architecture

A shared `INTELLIGENCE_LAYER_PROMPT` block is injected into every system prompt in Kinetic. This is the single highest-leverage change — it ensures every LLM call produces output informed by the seven capabilities.

The shared prompt includes instructions for:
- Generative Questioning: "Surface 2-3 questions the user hasn't thought to ask, grounded in the provided context"
- Synthesis: "End with a Bottom Line that compresses the essential structure into 2-3 sentences"
- Perspective Shifting: "When stakeholder context is available, note how key stakeholders might view this differently"
- Pattern Recognition: "When multiple sources are provided, identify non-obvious connections between them"

Capabilities NOT in the shared prompt (they need specific data or triggers):
- Intellectual Honesty (needs tracked assumptions)
- Counterfactual Reasoning (needs user-initiated "what if")
- Temporal Intelligence (needs chronological data comparison)

### Mechanism 2: Output Structure

Every major AI-generated artifact includes Intelligence Layer sections:

**Meeting Prep Brief:**
| Section | Capability | Always/Conditional |
|---------|-----------|-------------------|
| The Essential Situation | Synthesis | Always |
| Background & Context | (baseline) | Always |
| Talking Points | (baseline) | Always |
| Questions You Haven't Asked | Generative Questioning | Always |
| What's Changed Since Last Meeting | Temporal Intelligence | After 2+ meetings |
| How [Stakeholder] Might See This | Perspective Shifting | When stakeholder data exists |
| Assumptions at Risk | Intellectual Honesty | When tracked assumptions exist |
| Recent Company News | (Pre-Meeting Research Agent) | When research runs |

**Post-Meeting Summary:**
| Section | Capability | Always/Conditional |
|---------|-----------|-------------------|
| Summary | (baseline) | Always |
| The Essential Takeaway | Synthesis | Always |
| Action Items | (baseline) | Always |
| Pain Points & Buying Signals | (baseline) | Always |
| Assumptions Stated or Implied | Intellectual Honesty | Always — extracted and stored |
| What This Conversation Didn't Address | Generative Questioning | Always |
| Patterns Across Clients | Pattern Recognition | When pattern matches found |

**Weekly Review:**
| Section | Capability | Always/Conditional |
|---------|-----------|-------------------|
| The State of the Practice | Synthesis | Always |
| Follow-ups Due | (baseline) | Always |
| Knowledge Captured This Week | (baseline) | Always |
| Emerging Patterns | Pattern Recognition | When patterns detected |
| Gradual Shifts You Might Not Notice | Temporal Intelligence | After 30+ days of data |
| This Week's Uncomfortable Question | Generative Questioning + Intellectual Honesty | Always |
| What You Might Be Avoiding | Intellectual Honesty | When neglected items detected |
| Scenarios Worth Considering | Counterfactual | When significant client changes detected |

**Morning Briefing (Slack DM):**
| Section | Capability | Always/Conditional |
|---------|-----------|-------------------|
| Today's Meetings | (baseline) | Always |
| One Question Worth Asking (per meeting) | Generative Questioning | Always |
| Follow-ups Due | (baseline) | Always |
| New Knowledge Worth Noting | (baseline) | When new items exist |
| Assumption to Revisit Today | Intellectual Honesty | When contradicting evidence exists |
| Gradual Shift Alert | Temporal Intelligence | When drift detected in last 7 days |

### Mechanism 3: Data Model Additions

Three changes to the existing data model:

**1. Expand `client_memory.memory_type` enum:**
Add: `"assumption"`, `"hypothesis"`
- Assumptions are beliefs about a client's situation extracted from meetings
- Hypotheses are predictions about what will happen or what a client needs
- Both are tracked over time and checked against new evidence

**2. Expand `practice_memory.memory_type` enum:**
Add: `"pattern_observed"`, `"drift_detected"`, `"bias_noted"`
- `pattern_observed`: cross-client pattern detected by agents
- `drift_detected`: gradual shift in client goals/priorities noticed over time
- `bias_noted`: self-identified tendency or blind spot

**3. New `patterns` table:**
- `id` (uuid, PK)
- `pattern_type` (enum: "cross_client", "market_trend", "behavioral", "knowledge_gap")
- `description` (text — what the pattern is)
- `evidence` (jsonb — array of source references: meeting_ids, knowledge_item_ids, contact_ids)
- `affected_contacts` (uuid[] — contacts this pattern is relevant to)
- `confidence` (enum: "emerging", "established", "fading")
- `first_detected` (timestamp)
- `last_reinforced` (timestamp)
- `embedding` (vector(1536))
- `created_at` (timestamp)

### Mechanism 4: Agent Behavior

Existing agents are instructed to apply Intelligence Layer thinking:

**Post-Meeting Agent — add three steps:**
- Extract assumptions stated or implied → store as client_memory type `assumption`
- Identify what was NOT discussed relative to client goals → include in summary as "Gaps"
- When pattern match found, write to `patterns` table with evidence references

**Morning Briefing Agent — add three sections:**
- Per meeting: "One question worth asking" (Generative Questioning)
- Global: "Assumption to revisit today" — pick one assumption with contradicting evidence (Intellectual Honesty)
- Global: "Gradual shift alert" — if drift detected for any client in last 7 days (Temporal Intelligence)

**Pre-Meeting Research Agent — add one step:**
- After finding company news: "How this news might affect what [Contact] cares about" grounded in client memory (Perspective Shifting)

**Weekly Review Agent (when built) — native Intelligence Layer output:**
- Built from the ground up with all 7 capabilities as core output sections

### Mechanism 5: Chat Interface

The chat interface is the natural home for on-demand Intelligence Layer capabilities:

| User prompt pattern | Capability activated |
|---|---|
| "How would [role] see this?" | Perspective Shifting |
| "What if [scenario]?" | Counterfactual Reasoning |
| "What's the essential structure here?" | Synthesis |
| "What am I wrong about with [Client]?" | Intellectual Honesty (uses tracked assumptions) |
| "What should I be asking about [Client]?" | Generative Questioning |
| "What patterns am I seeing across clients?" | Pattern Recognition (queries patterns table) |
| "What's changed with [Client] over time?" | Temporal Intelligence |

The chat system prompt includes the shared `INTELLIGENCE_LAYER_PROMPT` so even unprompted queries benefit from questioning, synthesis, and perspective capabilities.

### Mechanism 6: Per-Client CLAUDE.md

The generated `CLAUDE.md` for each client folder includes Intelligence Layer instructions:

```
## Intelligence Layer
When helping with deliverables for this client:
- Before recommending, surface 2 questions worth investigating first
- Flag if any recommendation contradicts a tracked assumption (query via MCP)
- When drafting, include a "How [stakeholder] might react" note for key stakeholders
- End complex analyses with a Bottom Line compression
- If the user asks for advice, also share what might go wrong (grounded in client context)
```

---

## What We Explicitly Don't Do

- **No unsolicited "you're wrong" notifications.** Intellectual Honesty is surfaced in outputs you're already reading (prep briefs, reviews, briefings) — not as random alerts.
- **No automated counterfactual generation.** Scenario reasoning is interactive (user-initiated in chat or dashboard) — passive "what if" generation produces noise.
- **No temporal intelligence in month 1.** Temporal comparisons need 30+ days of accumulated data. The prompts are there from day 1, but the sections are conditional — they appear only when meaningful comparisons exist.
- **No pattern detection with fewer than 3 clients.** Cross-client patterns require enough clients to have a meaningful sample. Pattern sections are conditional.
- **No fake depth.** If Kinetic doesn't have enough context for a capability to be grounded, it says so rather than generating vague platitudes. "Not enough data for temporal comparison yet" is better than a generic "things may have changed."

---

## Implementation Priority

| Change | Effort | When |
|--------|--------|------|
| Shared `INTELLIGENCE_LAYER_PROMPT` | Low — prompt engineering | Phase 1, baked into every system prompt from day 1 |
| Output structure (new sections in prep briefs, summaries, reviews) | Low — template changes | Phase 1-2, as each feature is built |
| Data model (assumption/hypothesis types, patterns table, drift_detected) | Low — schema additions | Phase 1, add to initial Supabase migration |
| Agent behavior (assumption extraction, gap detection, pattern writing) | Medium — agent prompt updates | Phase 2, when agents are built |
| Chat Intelligence Layer (perspective, counterfactual, honesty) | Medium — chat system prompt | Phase 2, when chat is built |
| CLAUDE.md Intelligence Layer instructions | Low — template text | Phase 2, when CLAUDE.md generator is built |
