# Kinetic — Product Brief

**Status:** Draft
**Last updated:** 2026-03-21
**Owner:** Brandon (CEO)

---

## Vision

Kinetic is a context-rich AI workspace for knowledge workers. It eliminates the cold-start problem of generic AI tools by maintaining persistent, layered context about who you are, what you're working on, and how you want to think — and surfaces that context through custom AI agents you build and invoke on demand.

Every generation in Kinetic is pre-loaded with what matters: your background, your company's goals, your project's current state, and the perspective of thinkers you trust. The result is AI output that reasons like a well-briefed collaborator, not a blank slate.

Beyond reasoning, Kinetic is a productivity layer: it captures context from meetings, emails, and quick thoughts; auto-extracts deliverables and due dates; and proactively briefs you before client meetings — so your AI stays current without manual maintenance.

---

## Target Users

**Primary:** Consultants and founders working across multiple clients or companies who need AI that understands their full operating context — not just the current message.

**Secondary:** Knowledge workers broadly (executives, PMs, analysts, strategists) who do high-stakes thinking work and find generic AI too shallow to be consistently useful.

**What they have in common:**
- They work across multiple contexts (companies, projects, clients)
- They do complex, judgment-heavy work — decisions, strategy, planning, problem-solving
- They've tried ChatGPT/Claude and hit the ceiling: the tool doesn't know enough about them to be truly useful
- They admire specific thinkers and want to think more like them
- They lose context between sessions and waste time reconstructing what they already knew

---

## Jobs to Be Done (Summary)

**1. Make better decisions faster.**
Users need an AI that already knows their constraints, goals, and operating context — so they're not re-explaining themselves every session and the output is actually relevant to their situation.

**2. Think through hard problems from a trusted perspective.**
Users want to invoke the reasoning style of thinkers they admire — not generic AI advice, but "how would [specific person] approach this given my context?"

**3. Build and maintain institutional knowledge that compounds.**
Project memory, agent memory, and company context should grow over time. Each session should be smarter than the last, not starting from zero.

**4. Capture context effortlessly and stay prepared.**
Users want meeting transcripts auto-processed, quick thoughts captured on the fly, and pre-meeting briefings generated — so their AI stays current without manual maintenance.

**5. Manage client relationships with full context.**
Consultants want relationship details, interaction history, and personal context about client contacts surfaced automatically — so every interaction feels informed and personal.

> See `docs/jobs-to-be-done.md` for the full JTBD catalog.

---

## Core Entities

| Entity | What it is |
|---|---|
| **User** | Profile with personal context: role, bio, background, working style, strengths |
| **Company** | A company the user is associated with: mission, product, goals, business plan. Users can have multiple; one is active at a time |
| **Contact** | A person the user interacts with in the context of a Company. Holds relationship context for briefings and personalization. |
| **Project** | An in-app workspace for a specific initiative. Has its own Instructions, Active Memory, Thought Stream, and Knowledge Base. Belongs to one Company. |
| **AgentDefinition** | The shared blueprint for an AI persona: system prompt, knowledge base, frameworks. Can be private, shared, or public. |
| **AgentInstance** | A user's personal runtime state for an AgentDefinition: active memory, thought stream, framework overrides. Created per-user on first invocation. |
| **Knowledge Base** | A structured, searchable document store attached to a Project or AgentDefinition. The RAG layer. Supports folders and tags; AI auto-suggests metadata on upload. |
| **Document** | A single item inside a Knowledge Base — transcript, report, article, code file, etc. Chunked and embedded for retrieval. |
| **Active Memory** | Persistent, AI-curated facts injected directly into every prompt. Exists at the Project level and the AgentInstance level. Distinct from the Knowledge Base. |
| **Thought Stream** | pgvector-backed semantic search layer for lightweight captured context: thoughts, meeting extracts, email snippets, quick notes. Scoped by company + project. |
| **Framework** | A named reasoning tool attached to an AgentDefinition. Classifier-selected at query time and injected whole. |

> See `docs/domain-model.md` for full entity definitions, attributes, relationships, and context stack assembly.

---

## Key Differentiators

**Zero cold-start.** Every generation is pre-loaded with the context stack: user profile → active company → active project → invoked agents. Users don't re-explain themselves.

**Thought leader agents.** Upload a corpus of someone's writing or transcripts. Kinetic auto-generates a system prompt that captures their reasoning style. The user refines it. The agent becomes invocable as a perspective — "how would this person think about this?"

**Three-tier memory.** Active Memory (curated facts, always injected) + Thought Stream (ambient capture, pgvector semantic search) + Knowledge Base (uploaded documents, RAG-retrieved). Capture is low-friction and append-only; context serving is structured and deterministic. Users never hit a context ceiling, and the AI stays current through a natural promotion loop between tiers.

**Ambient capture.** Meeting transcripts, email snippets, quick thoughts, and AI-generated extracts flow into the Thought Stream automatically. The AI proposes promotions to Active Memory at session boundaries. Context compounds without manual maintenance.

**Multi-company context switching.** Users can maintain separate company contexts and switch between them without losing their personal profile or agent library. Built for consultants and founders from the start.

**Shareable and public agents.** AgentDefinitions can be private, shared with specific users, or published publicly. Each invoking user gets their own AgentInstance with private memory and thought stream. The shared definition (system prompt, KB, frameworks) stays uniform across all users.

**Client isolation by design.** Thought Stream and Active Memory are scoped by company and project via structural foreign keys — not tags. Cross-company retrieval on agent instances is opt-in per query, never default.

**MCP agent access.** AgentDefinitions are accessible via MCP from external AI tools (Claude, ChatGPT, Cursor, etc.). External clients get the agent's system prompt, frameworks, and KB — the full reasoning capability — without the per-user Active Memory and Thought Stream. Portable reasoning outside Kinetic; personalized reasoning inside it.

**BYOK model flexibility.** Users bring their own API keys (Anthropic, OpenAI, Google, Groq) and choose which model to use per query. No vendor lock-in — the same context stack works across any supported LLM.

---

## Context Stack (How Generation Works)

When a user sends a message, the final prompt is assembled in layers. **MVP ships with 9 layers; full V1 adds Thought Stream as Layer 7** (see deferred note below).

**Always injected (deterministic):**
1. **User profile** — always present (~100 tokens)
2. **Active company context** — the company currently selected (~100 tokens)
3. **Project instructions** — static rules for this project (~500 tokens)
4. **Project active memory** — AI-curated dynamic facts (≤1000 tokens)
5. **Agent system prompt(s)** — persona definition from AgentDefinition (~500 tokens each)
6. **Agent active memory** — learned patterns from AgentInstance (≤500 tokens each)

**Semantic search (query-dependent):**
7. **[DEFERRED — post-MVP] Thought stream** — top-K results from pgvector, scoped to active company + project + agent instance
7 (MVP) / 8 (V1). **Matched framework** — best-match reasoning tool via 4-step selection pipeline, injected whole

**RAG (query-dependent, chunked):**
8 (MVP) / 9 (V1). **Project knowledge base** — top-K relevant chunks
9 (MVP) / 10 (V1). **Agent knowledge base** — top-K relevant chunks from AgentDefinition's KB

Users control each layer. Agents can be added or removed mid-session.

---

## Scope: MVP vs. Full V1

> See `docs/mvp-scope.md` for the detailed MVP feature set and context stack.

### MVP (ships first)
- Auth & admin (registration, user management)
- User profile (name, bio, API keys, default model)
- Companies (name, description, multi-company switching)
- Projects (instructions, knowledge base, active memory, conversation history)
- AgentDefinition / AgentInstance split (shared definition + per-user state)
- Agent visibility: private/public toggle (private default)
- Agent MCP access (external AI clients invoke AgentDefinitions read-only)
- Framework library (structured entities, classifier-selected)
- Knowledge Bases on Projects and AgentDefinitions (upload docs, RAG)
- Project Active Memory (AI-curated, ≤1000 tokens, always injected)
- Agent Active Memory (per-user via AgentInstance, ≤500 tokens)
- 9-layer context stack + per-query model selection (BYOK)
- Conversation entity (belongs to Project, shown in left column)

### Post-MVP (still V1 roadmap)
- Thought Stream (pgvector ambient capture layer)
- Contacts entity (relationship context under Company)
- Cross-company retrieval opt-in for agent instances
- Agent `shared` visibility tier (specific users)
- Agent permissions model (owner/editor/invoker)
- Agent transparency (transparent/opaque)

### Out of scope for V1 entirely
- Real-time collaboration / multi-user workspaces (beyond agent sharing)
- Agent autonomy or scheduling (agents are manually invoked only)
- Third-party integrations (email, calendar, Notion, Slack) — Phase 2
- Local folder / desktop file sync
- Agent-to-agent interaction
- Agent marketplace (payment layer)
- Pre-meeting auto-briefings (requires calendar integration — Phase 2)
- Email-based thought capture (requires email integration — Phase 2)
- Meeting transcript auto-extraction (requires integration — Phase 2)

---

## Open Questions

1. **Company ↔ Project relationship:** Is company context attached to a project automatically (based on active company when the project was created) or does the user explicitly choose it per project? Can a project span multiple companies?

2. **Agent corpus scope:** Can one agent have multiple thought leader corpora (e.g., "think like Person A + Person B"), or is it one corpus per agent? If multiple, how does the auto-generated system prompt handle blending?

3. **Memory write triggers:** How does Active Memory get updated — AI-proposed at session boundaries, user-initiated ("save this to memory"), or both? This is a significant UX decision.

4. **Agent invocation UX:** Are agents invoked at the start of a session, mid-conversation, or both? Can multiple agents be active simultaneously?

5. **Conversation scope:** Do conversations belong to a Project only, or can there be company-level or agent-level conversations outside a project context?

6. **AgentDefinition update propagation:** When an owner updates a public agent's system prompt or frameworks, does this immediately affect all invokers? Should there be versioning?
