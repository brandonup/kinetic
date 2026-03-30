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

## Implementation Status (as of 2026-03-29)

Codebase at `projects/kinetic/packages/`. 565 API tests passing, 6 skipped, TypeScript clean.

**Shipped:** Auth, profiles, companies, projects, admin (models/users + `is_admin()` RPC + request-trace page KIN-418), active memory, conversations (CRUD + end + store_message), generation engine (9-layer context + SSE streaming + citations + agent activation + periodic memory + title auto-gen + framework overrides), MCP server (78 tests, 7 E2E journeys), agents list + create flow + agent chat with streaming conversation view (KIN-420), KB UI (folders, tags, upload, status), chat UI polish, trigger embeddings (KIN-412 background job + KIN-413 admin backfill, ADR-007), ingestion reliability fixes (KIN-408), llm_models seed migration (KIN-416, 54 rows across 5 providers), ModelSelector auto-selects first available model, `debug_prompt` written on assistant messages + admin endpoint (KIN-419, KIN-411).

**Kinetic Brain (MCP):** Shipped 2026-03-29. Local MCP server (`son_of_anton/kinetic-brain/`) connects Cowork to Kinetic's Supabase. All 4 tools live: persona, memory, framework selection, KB search. Configured via `claude_desktop_config.json`, not Cowork plugin system. Created `match_chunks` RPC and fixed `match_framework_triggers` vector schema (`extensions.vector`). See `kinetic-brain/docs/deployment-guide.md`.

**Remote MCP Server:** Implementation complete 2026-03-30 (KIN-428, KIN-429, KIN-433). Supabase Edge Function at `kinetic-brain/supabase/functions/kinetic-mcp/`. Auth (Bearer token + SHA-256), BYOK crypto (HKDF-SHA256 + AES-256-GCM ported to Deno Web Crypto), 5 MCP tools, dynamic prompts per user's agents, Hono + JSON-RPC 2.0. Cross-language crypto test vectors validated. Pending: Brandon deploys via `supabase functions deploy kinetic-mcp --no-verify-jwt`.

**Railway Deployment:** Config files ready 2026-03-30 (KIN-434). Dockerfile (multi-stage, handles `unstructured[all-docs]` native deps), `railway.toml`, `Procfile`, health endpoint at `/health`. Pending: Brandon creates Railway project, sets env vars, triggers first deploy. Guide at `docs/deploy-railway.md`.

**Known issue:** L7/L8/L9 (framework selection + RAG retrieval) not firing in the Kinetic web app despite user having BYOK OpenAI key configured. `fetch_user_key_async` returning None — root cause undiagnosed. (Note: these layers work correctly in the MCP server, which uses the service role key directly.)

**Pending commits:** Various commit scripts at `packages/api/commit_kin3XX.sh` and `/private/tmp/claude-501/`.

---

## MVP Boundaries

**In:** Auth, profiles, companies, projects, agents (system prompt + KB + frameworks + MCP), 9-layer context stack, per-query model selection, BYOK.

**Post-MVP:** Thought Stream, Contacts, cross-company retrieval, shared visibility, agent permissions, agent transparency.

**Out of V1:** Real-time collab, agent autonomy/scheduling, third-party integrations, desktop sync, agent-to-agent, marketplace.

---

## Open Questions (as of 2026-03-29)

| Question | Owner |
|---|---|
| Ship current framework schema or migrate to MVP strategy schema? | Monica → Brandon |
| Nate B. Jones system prompt — who authors it and when? | Brandon |
| Cluster-aware trigger refinement — before or after launch? | Monica → Brandon |
| Token profiling of framework injection payloads | Monica |
| MCP conversation logging — reuse `messages` table or new table? | Jared (spec in progress) |
