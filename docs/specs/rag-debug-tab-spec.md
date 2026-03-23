# Admin RAG Debug Tab — Implementation Spec

**Status:** In Review
**Author:** Jared
**Date:** 2026-03-23
**Linear:** KIN-315
**Sprint:** 6 (Dinesh implementation)
**PRD ref:** `docs/prd.md` §1 Admin section
**Schema ref:** `docs/db-schema-spec.md` §20 (`retrieval_debug_logs`)
**RAG ref:** `docs/rag-architecture.md` § Debug Tracing

---

## Overview

The Admin RAG Debug tab is a read-only diagnostic tool for admins. It surfaces per-query retrieval traces — which chunks were retrieved, their similarity scores, MMR selection decisions, threshold gating outcomes, and the final injected chunks. Purpose: answer "why did the AI say that?" without digging into logs.

Not user-facing. Admin panel only.

---

## 1. Data Model

The `retrieval_debug_logs` table is already defined in `db-schema-spec.md §20`. Do not redefine it here. Summary of relevant fields:

| Field | What it contains |
|---|---|
| `message_id` | FK to the conversation message that triggered retrieval |
| `scope` | `project_kb` or `agent_kb` |
| `query_text` | Original user query |
| `query_variants` | Rewritten variants (null in MVP — single query path) |
| `vector_candidates` | Pre-MMR candidates: `[{chunk_id, score}]` |
| `mmr_selections` | Post-MMR selections: `[{chunk_id, score}]` |
| `rerank_scores` | Per-chunk reranker scores (null in MVP) |
| `gating_decision` | `injected` or `below_threshold` (MVP); `high`, `limited`, or `none` (V1 with reranking) |
| `injected_chunks` | Final chunks that entered the prompt: `[{chunk_id, score, text_preview}]` — schema stores chunk_id + preview only. See Open Questions for display strategy. |
| `created_at` | Query timestamp |

**Retention:** Rows auto-purge after 30 days. No manual deletion needed. Max trace count: no hard cap in MVP — purge-by-age is the only bound.

---

## 2. API Endpoints

All endpoints require admin auth (HTTP 403 if non-admin). No BYOK key used — read-only DB queries.

### `GET /api/v1/admin/rag-debug`

Returns a paginated list of recent retrieval traces.

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int | 50 | Rows per page |
| `cursor` | uuid | — | Pagination cursor (`created_at` desc) |
| `scope` | string | — | Filter by `project_kb` or `agent_kb` |

**Response:**
```json
{
  "traces": [
    {
      "id": "uuid",
      "message_id": "uuid",
      "scope": "project_kb",
      "query_text": "...",
      "gating_decision": "injected",
      "injected_chunk_count": 4,
      "vector_candidate_count": 20,
      "created_at": "ISO-8601"
    }
  ],
  "next_cursor": "uuid | null"
}
```

Note: List response returns summary fields only. Full trace (candidates, MMR, chunks) comes from the detail endpoint.

### `GET /api/v1/admin/rag-debug/{trace_id}`

Returns full trace detail for a single query.

**Response:** Full `retrieval_debug_logs` row — all fields including `vector_candidates`, `mmr_selections`, `injected_chunks`, `rerank_scores`.

---

## 3. UI Layout

Located at: Admin panel → RAG Debug tab.

### Trace List (table view)

| Column | Source |
|---|---|
| Timestamp | `created_at` |
| Query | `query_text` (truncated to 80 chars) |
| Scope | `scope` badge (`project_kb` / `agent_kb`) |
| Outcome | `gating_decision` badge — `injected` (green), `below_threshold` (amber), error (red) |
| Chunks injected | `injected_chunk_count` |
| Candidates | `vector_candidate_count` |

Default sort: newest first. No user-facing sort controls in MVP.

Filter: scope dropdown (`All` / `Project KB` / `Agent KB`). No date range filter in MVP.

### Trace Detail (expandable row / drawer)

Clicking a row expands an inline panel (or opens a side drawer). Sections:

**Query**
- Full query text
- Scope + timestamp

**Retrieval Steps** (collapsible sections per pipeline stage)

1. **Vector Search** — table of pre-MMR candidates: chunk ID (truncated), document title, similarity score. Sorted by score desc.
2. **MMR Selection** — highlight which candidates survived MMR. Show dropped candidates dimmed.
3. **Threshold Gate** — show `SIMILARITY_THRESHOLD` value in effect and which chunks cleared it. If no chunks cleared: show "Below threshold — nothing injected."
4. **Injected Chunks** — final chunks in prompt: `text_preview` (from JSONB) + score. `document_title` and `section_path` displayed if enriched at write time (see Open Questions §1) or omitted if join-at-read pattern is used.

**Error state** (if retrieval failed):
- Show error type + message in place of pipeline steps.

---

## 4. Access Control

**Enforcement — two layers:**

1. **Route guard (frontend):** Admin panel is only rendered for users with `role = admin`. Non-admin users cannot navigate to admin routes. The RAG Debug tab is never rendered for non-admin users.

2. **API middleware (backend):** Every `GET /api/v1/admin/*` route requires `role = admin` in the JWT. Return HTTP 403 with `{ error: { code: "ADMIN_REQUIRED", message: "Admin access required." } }` for non-admin users.

Both layers are required. Frontend-only guard is insufficient — API must enforce independently.

**RLS:** `retrieval_debug_logs` has admin-bypass RLS (see `db-schema-spec.md §20`). Non-admin Supabase calls cannot read the table regardless of API enforcement.

---

## 5. Performance — Async Write

Trace writes must not add latency to the user query path.

**Write pattern:** After the retrieval pipeline completes and the context is assembled, the trace is written via a background task (FastAPI `BackgroundTasks` using the `TaskDispatcher` abstraction from ADR-001). The SSE stream begins immediately — trace writing happens concurrently.

**Write failure:** If the trace write fails (DB error, timeout), log the error server-side and continue. Never fail a user query because the debug log couldn't be written. Silent failure on trace write is acceptable.

**No read impact:** The list and detail endpoints are admin-only, infrequent reads. No caching needed in MVP.

---

## 6. Edge Cases

| Scenario | Expected behavior |
|---|---|
| RAG returns 0 chunks (all below threshold) | Log with `gating_decision: "below_threshold"`, `injected_chunks: []`. UI shows "Below threshold" badge. No error state. |
| Query embedding fails (OpenAI API error) | Log with `gating_decision: "error"`, `error_message: "<error detail>"`. Retrieval pipeline returns 0 chunks and continues. UI shows error badge in trace list. |
| KB is empty (no documents uploaded) | Vector search returns 0 candidates. Log normally. `vector_candidates: []`, `gating_decision: "below_threshold"`. |
| BYOK key error mid-query | Not relevant to this feature — retrieval uses platform-owned embedding key. No BYOK dependency. |
| Trace write fails (DB unavailable) | Log error server-side. Query continues normally. Trace is lost — acceptable in MVP. |
| Message is deleted | `message_id` FK becomes a dangling reference. Traces are append-only — retain as-is. Queries against deleted messages still show in the debug list (the message text is captured in `query_text` at write time). |

---

## 7. Handoff Checklist (Jared → Gilfoyle → Dinesh)

**Before Approved:** Run cross-reference check against `db-schema-spec.md §20` — verify all field names and types match. Confirm `TaskDispatcher` abstraction is the correct pattern for async write (see ADR-001).

**When Approved:**
1. Create `[Gilfoyle] Architecture review: RAG Debug tab spec` — labels: `architecture`, `Feature`. Link: `blocks: KIN-315`.
2. Move Gilfoyle issue to `Todo`.
3. Comment on Gilfoyle issue: "Spec at `docs/specs/rag-debug-tab-spec.md`. Review async write pattern and confirm API endpoint contract matches `retrieval_debug_logs` schema. Ready to start. — Jared"

---

## Open Questions

**1. Injected chunk display — join vs. denormalize?**

`db-schema-spec.md §20` defines `injected_chunks` as `[{chunk_id, score, text_preview}]`. The UI trace detail wants to show `document_title` and `section_path` per chunk. Two options:

- **Option A (denormalize at write time):** Expand `injected_chunks` JSONB to `[{chunk_id, score, text_preview, document_title, section_path}]`. Requires a schema update. Pro: no read-time join. Con: small schema change.
- **Option B (join at read time):** Keep schema as-is. Detail endpoint joins `knowledge_base_chunks` → `knowledge_base_documents` via `chunk_id` when serving trace detail. Pro: no schema change. Con: extra query at read time (admin-only, acceptable).

**Recommendation:** Option B — admin reads are infrequent and the join is trivial. No schema change needed.
**Needs Gilfoyle's call** — confirm Option B is acceptable before Approved.
