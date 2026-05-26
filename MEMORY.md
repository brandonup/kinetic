# Kinetic — Project Memory

_Updated at the end of each working session._

---

## Tracking

- **System:** Linear
- **Workflow:** `agents/linear-workflow.md`
- **Team:** Kinetic
- **Project:** Kinetic MVP
- **URL:** https://linear.app/brandonup/team/KIN

## GitHub Repo

**URL:** https://github.com/brandonup/kinetic

**Full decision log:** See `decisions-archive.md`.

---

## What Kinetic Is

Context-rich AI workspace SaaS for knowledge workers. Persistent, layered context (user → company → project → agents). Users build custom AI personas grounded in RAG + system prompts. BYOK model. MVP ships with Active Memory + KB (Thought Stream is post-MVP).

---

## Entities (locked)

**MVP:** User, Company, Project, Conversation, AgentDefinition, AgentInstance, Knowledge Base, Document, Active Memory, Framework

**Post-MVP:** Contact, Thought Stream

---

## Implementation Status (as of 2026-05-24)

Codebase at `projects/kinetic/packages/`. 565+ API tests passing, TypeScript clean. Full historical detail of shipped work lives in Linear tickets.

**Core platform shipped:** Auth/profiles/companies/projects/admin, active memory, conversations (CRUD + streaming), generation engine (9-layer context + SSE streaming + citations + agent activation + periodic memory + framework overrides), agents (list/create/chat), KB UI, trigger embeddings (KIN-412/413, ADR-007), llm_models seed (54 rows × 5 providers, KIN-416), debug_prompt + admin endpoint (KIN-419/411).

**MCP servers live:** Local "Kinetic Brain" plugin (5 tools, Cowork, `claude_desktop_config.json`) and Remote MCP at Supabase Edge Function (6 tools + dynamic prompts via native Connectors, ported to official SDK in KIN-464, 2026-04-06). Rate-limit RPC applied prod + dev. BYOK crypto validated.

**Deployment:** Railway prod ([kinetic-production-b568.up.railway.app](https://kinetic-production-b568.up.railway.app), KIN-434), Vercel prod ([kinetic-ashy-beta.vercel.app](https://kinetic-ashy-beta.vercel.app), KIN-436), dev environment with separate Supabase instance (KIN-455). `git push` auto-deploys to prod — dev verification is mandatory before push. Dev MCP connector removed 2026-04-04 (single prod connector only). See `docs/setup/environment-architecture.md`.

**Ingestion (2026-04-08):** Chunk overlap 38→75 (KIN-469), contextual chunk headers (KIN-468), semantic chunker behind `SEMANTIC_CHUNKING_ENABLED` (KIN-470). All depend on KIN-467 (Gemini embeddings).

**Recency-aware retrieval (2026-05-23/24):** Components A/B/C/D + eval runner shipped behind `RECENCY_ENABLED` flag (byte-identical off-state). KIN-481/482/483/484/485/489/492/495 done. Remaining: KIN-487 (tuning run, blocked on KIN-496). Baseline eval at RECENCY_WEIGHT=0.15: recency 4/6 PASS (66.7%); 2 fresh docs not retrieved (signal for KIN-487 weight tuning). Generation cases (contradiction/over_flagging) require `EVAL_GENERATION_API_KEY` env var to score.

**Eval suites passing (2026-05-24):** Both `kb_retrieval` and `framework_selection` pass all 4 launch bars on prod Nate corpus under Gemini regime. Thresholds raised for Gemini's compressed-range outputs (`SIMILARITY_THRESHOLD: 0.3→0.65`, `FRAMEWORK_MIN_SIMILARITY: 0.62→0.85`, `HIGH_CONFIDENCE_THRESHOLD: 0.75→0.95`). KIN-494/497. Datasets regenerated via `gemini-2.5-flash`. Baselines: `docs/evals/2026-05-24-kin497-*-gemini.md`.

**Substack sync — Nate KB (2026-05-23, KIN-479):** Daily scrape of `natesnewsletter.substack.com` active, 569 pre-seeded posts deduped. Latent missing-deps bug fixed via KIN-480.

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
