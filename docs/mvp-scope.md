# Kinetic — MVP Scope

**Status:** Draft
**Last updated:** 2026-03-21
**Owner:** Brandon (CEO)

---

## Purpose

This document defines the minimum viable product for Kinetic. It is a subset of the full V1 spec in the domain model and product brief. Features listed here ship first. Everything else in V1 ships later.

---

## MVP Feature Set

### Auth & Admin
- **Registration:** Email-only. User provides email → account is auto-created via Google OAuth. No approval flow, no invite codes, no password setup.
- **Login:** Google OAuth only. No magic link, no password management in MVP.
- **Admin section:** List users, disable accounts. No roles beyond admin/user.

### User Profile
- Two fields: **Name** and **Short bio** (optional)
- API key management: Anthropic, OpenAI, Google, Groq (encrypted at rest)
- Default model selection

### Companies
- User can create multiple companies
- Company profile: two fields — **Name** and **Short description** (optional)
- One active company at a time; user switches between them

### Projects
- User can create projects within a company
- Project Instructions: one free-form text field (optional, always injected into context)
- Project Knowledge Base: upload documents (chunked, embedded, RAG-retrieved)
- Project Active Memory: AI-curated dynamic facts (≤1000 tokens, always injected). AI proposes updates at session boundaries; user can manually edit.
- **Conversation history**: past conversations shown in a left column (like Claude). Conversations belong to a Project, are timestamped, and persist between sessions.

### Agents (AgentDefinition / AgentInstance split)

**AgentDefinition (shared across all users):**
- User can create agents
- Agent Instructions: one free-form text field (the system prompt — always injected when agent is invoked)
- Knowledge Base: upload documents (chunked, embedded, RAG-retrieved)
- Framework Library: structured reasoning tools. Uploaded as a JSON file (extraction happens outside Kinetic via separate script). Stored as structured entities; `when_to_apply` triggers embedded in pgvector for classifier selection.
- Visibility toggle: **private** (default, owner only) or **public** (any Kinetic user)
- MCP connection: agents are accessible from external AI tools (Claude, ChatGPT, Cursor). MCP exposes system prompt + KB (RAG) + frameworks (selection pipeline). Read-only.

**AgentInstance (per-user, created on first invocation):**
- Active Memory: AI-curated facts about this user's relationship with the agent (≤500 tokens, always injected). Learned patterns, preferences, interaction style.
- Framework overrides: pinned or excluded frameworks for this user

### Generation Engine (Context Stack)

Every query assembles context from these layers, in order:

**Always injected (deterministic):**

| Layer | Source | Size |
|---|---|---|
| 1. User profile | Name + bio | ~100 tokens |
| 2. Active company | Name + description | ~100 tokens |
| 3. Project instructions | Free-form text field | ~500 tokens |
| 4. Project active memory | AI-curated facts | ≤1000 tokens |
| 5. Agent system prompt(s) | AgentDefinition instructions | ~500 tokens each |
| 6. Agent active memory | AgentInstance memory | ≤500 tokens each |

**Classifier-selected (query-dependent):**

| Layer | Source | Behavior |
|---|---|---|
| 7. Matched framework | AgentDefinition frameworks | 4-step pipeline: embedding retrieval → expertise boost → LLM reranker → inject whole |

**RAG retrieval (query-dependent, chunked):**

| Layer | Source | Behavior |
|---|---|---|
| 8. Project knowledge base | Project KB docs | Top-K chunks relevant to query |
| 9. Agent knowledge base | AgentDefinition KB docs | Top-K chunks relevant to query |

**Per-query model selection:** User picks which LLM to use via a UI selector. Defaults to user's preferred model. Context stack is model-agnostic.

### UI Summary

- **Chat interface** with model selector
- **Left column**: conversation history (per project)
- **User profile page**: name, bio, API keys, default model
- **Company pages**: create/edit companies, switch active company
- **Project pages**: create/edit projects, instructions field, KB upload, active memory view/edit
- **Agent profile page**: instructions (system prompt), KB upload, framework library (browse/edit), visibility toggle, MCP connection URL
- **Admin panel**: user list, registration management

---

## Explicitly Deferred (post-MVP, still in V1 roadmap)

| Feature | Why deferred | Dependency |
|---|---|---|
| Thought Stream (pgvector ambient capture) | Adds complexity to MVP; Active Memory covers the core memory job | None — can be added independently |
| Contacts entity | Requires Thought Stream for full value (relationship context surfacing) | Thought Stream |
| Cross-company retrieval opt-in | Depends on Thought Stream | Thought Stream |
| Agent `shared` visibility (specific users) | Private/public covers MVP. Shared adds permissions complexity. | Agent permissions model |
| Agent permissions (owner/editor/invoker) | Not needed with private/public toggle. Required when `shared` is added. | Shared visibility |
| Agent transparency (transparent/opaque) | All agents transparent in MVP. Needed for marketplace IP protection. | Agent marketplace |
| Pre-meeting auto-briefings | Requires calendar integration | Third-party integrations |
| Email-based thought capture | Requires email integration | Third-party integrations |
| Meeting transcript auto-extraction | Requires integration pipeline | Third-party integrations |
| Agent marketplace (payment layer) | Requires visibility tiers, transparency, payments infrastructure | Multiple |

---

## Entities in MVP

| Entity | In MVP | Notes |
|---|---|---|
| User | Yes | Name, bio, API keys, default model |
| Company | Yes | Name, description |
| Project | Yes | Instructions, Active Memory, Knowledge Base, Conversations |
| Conversation | Yes (new) | Belongs to Project. Has messages. Timestamped. Shown in left column. |
| AgentDefinition | Yes | Instructions, KB, Frameworks, visibility (private/public), MCP |
| AgentInstance | Yes | Active Memory, framework overrides. Per-user. |
| Knowledge Base | Yes | Attached to Project or AgentDefinition |
| Document | Yes | Inside Knowledge Base. Chunked + embedded. |
| Framework | Yes | Structured entity on AgentDefinition. Classifier-selected. |
| Active Memory | Yes | On Project and AgentInstance |
| Contact | Deferred | Post-MVP |
| Thought Stream | Deferred | Post-MVP |

---

## Open Questions for MVP

1. **Active Memory write UX:** Does the AI propose memory updates at session end (user approves/rejects), or does the user manually trigger "save to memory"? Or both?
2. **Conversation scope:** Do conversations belong to a Project only, or can there be company-level or agent-level conversations outside a project context?
3. **MCP authentication:** How does the MCP connector URL authenticate the external client? API key in URL, OAuth, or token-based?
