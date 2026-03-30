# Skill Stack Reference — Agent Quick-Lookup

_Derived from "Evidence-Based Skill Stack for Shipping Kinetic with Claude Code." Consult when starting a task to see if a public or internal skill applies._

---

## How to Use This Doc

1. **Find your task type** in the table below.
2. **Check if any listed skills match** what you're about to do.
3. **Invoke the skill** if installed, or follow the pattern described if it's a reference-only skill.

Skills marked **Installed** are available via the Skill tool or as agent-file references. Skills marked **Adopt** should be installed from their source before first use (flag to Brandon). Skills marked **Reference** are pattern guides — read for principles, don't expect a runnable skill.

---

## Skill Lookup by Task Type

### Writing or Modifying Database Schema / Migrations

| Skill | Status | What it does | When to use |
|---|---|---|---|
| **supabase-postgres-best-practices** | Installed | Query performance, connection mgmt, RLS rules for Supabase/Postgres | Every migration, every new query, every RLS policy change |

**Key patterns:** Check RLS coverage for new tables. Validate index choices. Avoid N+1 queries. Use atomic operations for counters/sequences. Test multi-tenant isolation.

---

### Building or Modifying API Endpoints (FastAPI)

| Skill | Status | What it does | When to use |
|---|---|---|---|
| **verification-before-completion** | Installed | Forces format/lint/typecheck/tests before claiming done | Every ticket completion |
| **test-driven-development** | Installed | TDD workflow: write tests first, then implement | New endpoints, complex logic |
| **supabase-postgres-best-practices** | Installed | Query patterns, connection handling | Any endpoint touching the DB |

**Key patterns:** Validate inputs at boundary (Pydantic). Ownership check on every path param. Error shape: `{ error: { code, message } }`. Async Supabase client only. No bare `except:`.

---

### Building or Modifying Frontend (React / Next.js)

| Skill | Status | What it does | When to use |
|---|---|---|---|
| **vercel-react-best-practices** | Adopt | Perf rules: waterfalls, bundle size, caching, Suspense streaming, re-render optimization | Any React component work, especially chat UI or data-heavy views |
| **next-best-practices** | Adopt | Next.js file conventions, RSC boundaries, async patterns, error handling | Routing changes, layout changes, server component decisions |
| **webapp-testing** | Installed | Playwright E2E testing with server lifecycle management | Verifying UI flows: chat streaming, agent creation, KB upload, tenant switching |
| **frontend-design** | Installed | Distinctive, production-quality UI design | New pages, visual redesigns, component creation |

**Key patterns:** `params` is a Promise in Next.js 15 — must `await`. Use `pool: 'threads'` not `'forks'` for Vitest. Streaming chat needs explicit `viewBox` on SVG charts. Check for waterfall fetches.

---

### Working on the MCP Server

| Skill | Status | What it does | When to use |
|---|---|---|---|
| **mcp-builder** | Installed | Four-phase MCP workflow: research/plan, implement, test, evaluate. Schema quality, tool naming, error messages | Any MCP tool addition or modification |

**Key patterns:** Every tool needs Zod/Pydantic schema validation. Tool names should be verb_noun. Error messages must be actionable. Include evaluation questions for new tools.

---

### Working on RAG / Retrieval / Embeddings

| Skill | Status | What it does | When to use |
|---|---|---|---|
| **langchain-rag** | Reference | End-to-end RAG pipeline patterns: chunking, embedding, retrieval (MMR, metadata filtering) | Validating or modifying ingestion/retrieval pipeline |
| **supabase-postgres-best-practices** | Installed | pgvector query patterns, index choices | Vector search queries, embedding storage |

**Key patterns:** Chunk size/overlap defaults matter. Test retrieval with tenant scoping. Validate `match_chunks` and `match_framework_triggers` RPCs return correct results. Filter `deleted_at IS NULL` in all retrieval paths.

---

### Working on Prompts or Agent System Prompts

| Skill | Status | What it does | When to use |
|---|---|---|---|
| **langfuse-prompt-migration** | Adopt | Migrate hardcoded prompts to managed/versioned prompts with stable labels | Moving prompts out of code, prompt A/B testing |
| **prompt-builder** | Reference | Structured prompt authoring: persona/task/context/output/validation sections | Writing new agent system prompts or tool prompts |
| **ai-prompt-engineering-safety-review** | Reference | Evaluates prompts across safety/bias/security/effectiveness dimensions | Pre-ship review for high-stakes system prompts (tool calling, data access, refusal behavior) |

**Key patterns:** Prompts are code — version them. No hardcoded prompts in application logic. Every prompt gets an ID and version. Review Tier-1 prompts (agent root prompts, tool instruction prompts) for safety before shipping.

---

### Observability / Tracing / Debugging Production Issues

| Skill | Status | What it does | When to use |
|---|---|---|---|
| **langfuse-observability** | Adopt | Baseline tracing: model names, token usage, span hierarchy, tenant/session/user tags, data masking | Instrumenting LLM calls, debugging latency, tracking cost per tenant |
| **systematic-debugging** | Installed | Structured debugging methodology | Complex bugs with unclear root cause |

**Key patterns:** Tag every trace with session_id, user_id, tenant_id. Track tokens per context layer. Mask PII in traces. Use span hierarchy to isolate which layer adds latency.

---

### Security Review or Hardening

| Skill | Status | What it does | When to use |
|---|---|---|---|
| **llm-security** | Adopt | OWASP Top 10 for LLM Apps: prompt injection, system prompt leakage, vector weaknesses, unbounded consumption | Any work touching RAG boundaries, tool execution, multi-tenant scoping |
| **security-review** | Reference | Exploitability-focused code audit: trace attacker-controlled inputs, high-confidence findings only | Periodic hardening sweeps (not daily coding) |

**Key patterns:** Validate all MCP tool inputs. Rate-limit LLM calls per tenant. Never return 403 for unauthorized resources (use 404 to prevent enumeration). Validate redirect URLs. Check RLS policies with real JWT claims, not fake ones.

---

### Writing PRDs or Specs

| Skill | Status | What it does | When to use |
|---|---|---|---|
| **prd-development** | Installed | Structured PRD workflow with measurable success/acceptance criteria, AI eval strategy, phased rollout | Any new feature spec |
| **architecture-decision-records** | Installed | Standardized ADRs with context, decision, alternatives, stakeholders | Architectural choices: DB, transport, prompt registry, tenant isolation model |
| **brainstorming** | Installed | Creative ideation (required before creative work per Jared's protocol) | Early-stage feature exploration |

**Key patterns:** PRDs must include non-goals (MVP scope discipline). Success criteria must be measurable. ADRs capture the "why" — not just the "what." Include AI-specific fields: eval strategy, failure modes, context policy.

---

### Sprint Planning / Process / Retrospectives

| Skill | Status | What it does | When to use |
|---|---|---|---|
| **linear-automation** | Installed | Linear MCP workflow: issue creation, status management, sprint planning | All Linear operations |
| **retrospective** | Installed | Session-end memory capture, defect analysis, MEMORY.md hygiene | End of every working session |

---

## Gap Skills (Not Yet Available — Build Internally When Needed)

These are high-value skills that don't exist publicly but would encode Kinetic-specific knowledge:

| Skill | What it would do | Build when |
|---|---|---|
| **Context Budgeter** | Compute token budgets per context layer, enforce caps, output a context plan | Context window issues emerge in testing |
| **RAG Ingestion Replay** | Replay failed ingestion with deterministic retries, structured error classification | Ingestion reliability becomes a priority |
| **Tenant Isolation Audit** | Scan for tenant IDs in every query path, RLS coverage checks, cross-tenant access tests | Pre-launch security hardening |
| **Streaming Correctness Harness** | SSE disconnect/reconnect, partial token frames, ordering, backpressure simulation | Chat reliability testing |
| **Launch Readiness Gate** | Cross-cutting checklist: critical flows tested, evals passing, observability live, rollback plan | Pre-launch |
