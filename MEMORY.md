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

## Implementation Status (as of 2026-03-30)

Codebase at `projects/kinetic/packages/`. 565 API tests passing, 6 skipped, TypeScript clean.

**Shipped:** Auth, profiles, companies, projects, admin (models/users + `is_admin()` RPC + request-trace page KIN-418), active memory, conversations (CRUD + end + store_message), generation engine (9-layer context + SSE streaming + citations + agent activation + periodic memory + title auto-gen + framework overrides), MCP server (78 tests, 7 E2E journeys), agents list + create flow + agent chat with streaming conversation view (KIN-420), KB UI (folders, tags, upload, status), chat UI polish, trigger embeddings (KIN-412 background job + KIN-413 admin backfill, ADR-007), ingestion reliability fixes (KIN-408), llm_models seed migration (KIN-416, 54 rows across 5 providers), ModelSelector auto-selects first available model, `debug_prompt` written on assistant messages + admin endpoint (KIN-419, KIN-411).

**Kinetic Brain (MCP):** Shipped 2026-03-29. Local MCP server (`packages/mcp/`) connects Cowork to Kinetic's Supabase. 5 tools live: persona, memory, framework selection, KB search, assemble_context. Configured via `claude_desktop_config.json`, not Cowork plugin system. Created `match_chunks` RPC and fixed `match_framework_triggers` vector schema (`extensions.vector`). See `packages/mcp/docs/deployment-guide.md`.

**Remote MCP Server:** Live 2026-03-30 (KIN-428, KIN-429, KIN-433, KIN-438). Supabase Edge Function at `supabase/functions/kinetic-mcp/`. All 5 tools + dynamic prompts working end-to-end via **native Connectors** (paste URL, no local setup). Transport: SSE response negotiation, `Mcp-Session-Id` header, spec-compliant CORS/DELETE/GET. Slug migration applied (`nate` slug, public visibility). BYOK crypto validated in production.

**Railway Deployment:** Live 2026-03-30 (KIN-434). URL: `https://kinetic-production-b568.up.railway.app`. Health check passing. Dockerfile handles `unstructured[all-docs]` native deps. Guide at `docs/deploy-railway.md`.

**Vercel Deployment:** Live 2026-03-30 (KIN-436). URL: `https://kinetic-ashy-beta.vercel.app`. Login page renders, Google OAuth working. Root directory: `packages/web`, Framework Preset: Next.js. Remaining: update Railway CORS_ORIGINS + ADMIN_PORTAL_URL to Vercel URL (Step 6 of KIN-436), then KIN-437 smoke test.

**Known issue:** L7/L8/L9 (framework selection + RAG retrieval) not firing in the Kinetic web app despite user having BYOK OpenAI key configured. `fetch_user_key_async` returning None — root cause undiagnosed. (Note: these layers work correctly in the MCP server, which uses the service role key directly.)

**Dev Environment:** Live 2026-03-30 (KIN-455). Separate dev Supabase instance, Docker API (`kinetic-api-dev`), local frontend. `git push` auto-deploys to prod (Railway + Vercel) — dev verification is mandatory before push. See `docs/environment-architecture.md`.

**Pending commits:** Various commit scripts at `packages/api/commit_kin3XX.sh` and `/private/tmp/claude-501/`.

---

## MVP Boundaries

**In:** Auth, profiles, companies, projects, agents (system prompt + KB + frameworks + MCP), 9-layer context stack, per-query model selection, BYOK.

**Post-MVP:** Thought Stream, Contacts, cross-company retrieval, shared visibility, agent permissions, agent transparency.

**Out of V1:** Real-time collab, agent autonomy/scheduling, third-party integrations, desktop sync, agent-to-agent, marketplace.

---

## Open Questions (as of 2026-03-30)

| Question | Owner |
|---|---|
| Ship current framework schema or migrate to MVP strategy schema? | Monica → Brandon |
| Nate B. Jones system prompt — who authors it and when? | Brandon |
| Cluster-aware trigger refinement — before or after launch? | Monica → Brandon |
| Token profiling of framework injection payloads | Monica |
| ~~MCP conversation logging — reuse `messages` table or new table?~~ | **Decided 2026-03-30:** New `messages_mcp` table (Gilfoyle identified 7 schema friction issues with reusing `messages`). One row per `assemble_context` call, fire-and-forget write. Implementation: KIN-452 (blocked by KIN-454). Future Option C revisit: KIN-453. |
