# ADR-001: Infrastructure Choices

**Status:** Proposed
**Author:** Gilfoyle
**Date:** 2026-03-22
**Project:** Kinetic

---

## Context

Kinetic is a context-rich AI workspace SaaS for knowledge workers. The MVP targets ≤50 users with ~2M words of KB content. The codebase ports proven components from FounderPanel (`~/Projects/founder_panel`), which runs on the same backend stack (FastAPI + Supabase) and a similar frontend stack.

Forces at play:
- **Speed:** AI agent team (Dinesh, Big Head) implements — porting from FounderPanel is faster than greenfield.
- **Scale:** MVP is small (~50 users, ~20K chunks). Architecture must not over-engineer for millions when we need to ship for dozens.
- **Cost:** BYOK model means no LLM infrastructure costs. Platform-owned embedding key is the only operational cost. Hosting should be minimal.
- **Complexity budget:** Every added service is a service the AI agents must understand, configure, and debug. Fewer moving parts = fewer failure modes.
- **Vector search:** pgvector for KB chunks (~20K vectors at 3072 dimensions) and framework trigger embeddings (~750 vectors). Both are well within pgvector HNSW limits.

---

## Decision

We will use the following stack for Kinetic MVP:

| Layer | Choice |
|---|---|
| Database | Supabase (PostgreSQL 15 + pgvector + Auth + Storage) |
| Vector storage | pgvector (HNSW indexes) |
| Backend | FastAPI (Python 3.11+) |
| Frontend | Next.js 14 (App Router) + TypeScript |
| Component library | Radix UI + shadcn/ui + Tailwind CSS |
| LLM abstraction | LiteLLM |
| Background jobs | FastAPI BackgroundTasks + TaskDispatcher abstraction |
| Text extraction | `unstructured` (Python) |
| Auth | Supabase Auth (Google OAuth) |
| File storage | Supabase Storage |

---

## Alternatives Considered

### Database + Vector Storage

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **Supabase (PostgreSQL + pgvector)** — chosen | Single service for DB, auth, storage, vectors. FounderPanel precedent. Managed hosting. RLS built-in. | pgvector slower than dedicated vector DBs at scale (>1M vectors). HNSW index rebuild on schema changes. | N/A — this is the decision |
| PostgreSQL + Qdrant | Dedicated vector DB optimized for ANN search. Better at high scale. | Two services to operate. FounderPanel used Qdrant but it added operational overhead. Kinetic's scale (~20K chunks) doesn't justify it. | Operational complexity for MVP scale. Qdrant is the migration option if pgvector becomes a bottleneck. |
| PlanetScale (MySQL) + Pinecone | Serverless scaling on both. | Two vendors, two billing surfaces. No PostgreSQL (losing RLS, pgvector, Supabase ecosystem). MySQL doesn't support the array types and JSONB we rely on. | Wrong ecosystem. Would require rewriting all FounderPanel ports. |

### Backend Framework

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **FastAPI (Python 3.11+)** — chosen | FounderPanel port. Async-native. Pydantic validation. BackgroundTasks built-in. Python is the standard for GenAI (LiteLLM, unstructured, embedding libraries). | GIL limits CPU-bound concurrency (not an issue — our workload is I/O-bound). | N/A |
| Django | Mature ORM, admin panel. | Heavier. No async-first design. FounderPanel isn't Django — port cost is high. | No FounderPanel reuse. Async is a retrofit, not native. |
| Express.js (Node) | Same language as frontend. | Python GenAI ecosystem is stronger. Would need to rewrite all backend ports. LiteLLM is Python-only. | Wrong language for GenAI workload. |

### Frontend Framework

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **Next.js 14 (App Router)** — chosen | FounderPanel port. Server components. API routes for SSE proxy. TypeScript. Vercel deployment option. | App Router is newer — some ecosystem libraries lag. | N/A |
| Remix | Good data loading patterns. | No FounderPanel reuse. Smaller ecosystem than Next.js. | Port cost. |
| SvelteKit | Lighter runtime. | No FounderPanel reuse. Svelte ecosystem is smaller. Team (AI agents) has no Svelte training data. | Port cost + ecosystem risk. |

### LLM Client Abstraction

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **LiteLLM** — chosen | Single interface for Anthropic, OpenAI, Google, Groq. Streaming support. FounderPanel uses it. Actively maintained. | Dependency on a third-party abstraction layer. | N/A |
| Direct provider SDKs | No abstraction dependency. Full control. | 4 separate integration paths. Per-query model switching becomes 4 code paths instead of 1. BYOK key routing is 4x the logic. | Unacceptable complexity for BYOK + multi-provider. |
| Vercel AI SDK | Good streaming primitives. | TypeScript-only (backend is Python). Doesn't support Groq natively. | Wrong language. |

### Background Jobs

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **FastAPI BackgroundTasks + TaskDispatcher** — chosen | Zero infrastructure. In-process. FounderPanel precedent. TaskDispatcher abstraction makes migration a one-file change. | No retry, no dead-letter queue, no monitoring dashboard. Tasks lost if process crashes. | N/A — sufficient for MVP. |
| Celery + Redis | Battle-tested. Retry, monitoring, scheduling. | Requires Redis broker. Two more services to operate. Over-engineered for MVP volume (~50 users). | Premature. TaskDispatcher abstraction means we can migrate when needed. |
| Temporal | Durable workflows. | Heavy operational overhead. Enterprise-grade for enterprise-scale problems. | Way too heavy for MVP. |

### Text Extraction

| Option | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| **`unstructured`** — chosen | Single library covers all 12 PRD formats (PDF, DOCX, PPTX, XLSX, CSV, TXT, MD, RTF, JSONL). Standard for RAG document ETL. Active maintenance. | Heavier dependency (~200MB with all extras). Extraction quality varies by format. | N/A |
| Per-format libraries (pdfplumber + python-docx + python-pptx + openpyxl + csv) | Fine-grained control per format. Lighter individual dependencies. | 4–5 libraries to install, wrap, and maintain. Each has different APIs. Error handling multiplied per format. FounderPanel used this approach and it was painful. | 4x integration surface for diminishing returns. |

---

## Consequences

**Positive:**
- FounderPanel port path cuts Sprint 1 implementation time significantly — auth, LLM client, ingestion, frontend scaffold are adapt-and-go, not build-from-scratch.
- Single Supabase project covers DB, auth, storage, and vectors. One bill, one dashboard, one connection string.
- Python backend + LiteLLM means the GenAI ecosystem is native — no language boundary for embedding, extraction, or LLM calls.
- TaskDispatcher abstraction future-proofs background jobs without adding infrastructure now.

**Negative:**
- pgvector HNSW index performance degrades past ~1M vectors. At current scale (~20K), this is not a concern. Qdrant migration path exists.
- FastAPI BackgroundTasks has no retry, monitoring, or dead-letter queue. Ingestion failures rely on application-level retry (3x with backoff, per PRD). A process crash loses in-flight tasks.
- `unstructured` is a heavy dependency. Extraction quality for edge-case formats (scanned PDFs, complex XLSX) may require per-format fallbacks later.
- Supabase vendor lock-in on Auth + Storage. Auth is portable (standard JWT); Storage would require S3 migration.

**Neutral:**
- Next.js App Router is the current standard but still maturing. Server Components patterns may shift. This is industry-wide, not Kinetic-specific.
- LiteLLM abstracts provider differences but may lag on new provider features. Acceptable tradeoff for unified interface.

---

## Risks

- **pgvector scale ceiling:** If KB content exceeds ~500K chunks (25x current estimate), retrieval latency will degrade. **Mitigation:** Monitor retrieval latency via `retrieval_debug_logs`. Migration to Qdrant is a known path — schema is designed with scope columns that map directly to Qdrant collection namespaces.

- **BackgroundTasks reliability:** Process crash = lost in-flight ingestion and memory proposals. **Mitigation:** Document status tracking (`pending → extracting → ...`) enables restart from the failed stage. TaskDispatcher abstraction enables Celery migration as a one-file change when reliability requirements increase.

- **`unstructured` extraction quality:** Complex documents (multi-column PDFs, password-protected files, scanned images) may extract poorly. **Mitigation:** Document processing status + retry UI. Users can re-upload or use simpler formats. Per-format fallback libraries can be added behind the extraction interface without changing the pipeline.

- **Supabase outage:** Single point of failure for DB + auth + storage. **Mitigation:** Supabase provides automatic backups. For MVP scale, this risk is acceptable. Multi-region or self-hosted PostgreSQL is the escape hatch.

---

## Review Trigger

Revisit this ADR when:
- KB content exceeds 500K chunks across all users (pgvector scale)
- Background task failures exceed 5% of ingestion attempts (reliability)
- User count exceeds 500 (general scale pressure)
- Supabase pricing becomes a meaningful cost driver
- A new LLM provider is needed that LiteLLM doesn't support
