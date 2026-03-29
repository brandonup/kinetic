# Kinetic — Project Memory

_Updated at the end of each working session._

---

## Linear Board

**URL:** https://linear.app/brandonup/team/KIN — Team: `KIN`

## GitHub Repo

**URL:** https://github.com/brandonup/kinetic

**Full decision log:** See `decisions-archive.md`

---

## What Kinetic Is

Context-rich AI workspace SaaS for knowledge workers. Persistent, layered context (user → company → project → agents). Users build custom AI personas grounded in RAG + system prompts. BYOK model. MVP ships with Active Memory + KB (Thought Stream is post-MVP).

---

## Entities (locked)

**MVP:** User, Company, Project, Conversation, AgentDefinition, AgentInstance, Knowledge Base, Document, Active Memory, Framework

**Post-MVP:** Contact, Thought Stream

---

## Implementation Status (as of 2026-03-28)

Codebase at `projects/kinetic/packages/`. 486 API tests passing, 6 skipped, TypeScript clean.

**Shipped:** Auth, profiles, companies, projects, admin (models/users), active memory, conversations (CRUD + end + store_message), generation engine (9-layer context + SSE streaming + citations + agent activation + periodic memory + title auto-gen + framework overrides), MCP server (78 tests, 7 E2E journeys), agents list + create flow, KB UI (folders, tags, upload, status), chat UI polish.

**Pending commits:** Various commit scripts at `packages/api/commit_kin3XX.sh` and `/private/tmp/claude-501/`.

---

## MVP Boundaries

**In:** Auth, profiles, companies, projects, agents (system prompt + KB + frameworks + MCP), 9-layer context stack, per-query model selection, BYOK.

**Post-MVP:** Thought Stream, Contacts, cross-company retrieval, shared visibility, agent permissions, agent transparency.

**Out of V1:** Real-time collab, agent autonomy/scheduling, third-party integrations, desktop sync, agent-to-agent, marketplace.

---

## Open Questions (as of 2026-03-23)

| Question | Owner |
|---|---|
| Ship current framework schema or migrate to MVP strategy schema? | Monica → Brandon |
| Nate B. Jones system prompt — who authors it and when? | Brandon |
| Cluster-aware trigger refinement — before or after launch? | Monica → Brandon |
| Token profiling of framework injection payloads | Monica |
