# Admin RAG Debug Tab Spec

**Owner:** Jared
**Sprint:** 5 (spec); 6 (implementation by Dinesh)
**Status:** Approved
**Tickets:** KIN-315

---

## 1. Overview

The Admin RAG Debug tab is a read-only diagnostic tool inside the Kinetic admin panel. It surfaces per-query retrieval traces so admins can answer "why did the AI say that?" — inspecting which chunks were retrieved, what similarity scores they carried, how MMR filtered them, and whether the gating threshold was passed.

It is admin-only. Users never see it.

---

## 2. Data Model

The `retrieval_debug_logs` table is the source of truth. This spec does not add columns — it describes how the existing schema is exposed via API and UI.

### 2.1 Schema reference (`docs/db-schema-spec.md` §20)

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `message_id` | uuid FK → messages | The assistant message that triggered retrieval |
| `scope` | `retrieval_scope` enum | `project_kb` or `agent_kb` |
| `query_text` | text | User's original query text |
| `query_variants` | text[] | V1 only — null in MVP |
| `vector_candidates` | jsonb | Pre-MMR candidates: `[{ "chunk_id": "...", "score": 0.87 }]` |
| `mmr_selections` | jsonb | Post-MMR selections: same shape as vector_candidates |
| `rerank_scores` | jsonb | V1 only — null in MVP |
| `gating_decision` | text | `injected` or `below_threshold` (MVP) |
| `injected_chunks` | jsonb | Final injected chunks: `[{ "chunk_id": "...", "score": 0.87, "text_preview": "..." }]` |
| `created_at` | timestamptz | Write time |

### 2.2 Joins needed for display

The list view joins outward from `retrieval_debug_logs`:

```
retrieval_debug_logs
  → messages (message_id)
    → conversations (conversation_id)
      → projects (project_id)
      → users (user_id)
```

This is resolved at query time — not denormalized into the log table.

### 2.3 Retention

Rows older than 30 days are deleted by a scheduled background job. No manual deletion UI in MVP. Retention is fixed — not admin-configurable in MVP.

### 2.4 Write path

The backend writes one `retrieval_debug_logs` row per scope per assistant message. A single message in a project-level conversation with an agent active produces up to two rows: one for `project_kb` (L8) and one for `agent_kb` (L9). Each scope runs independently and logs independently.

**Async write:** the log insert fires after the retrieval result has been assembled, as a background task (via `TaskDispatcher`). It does not block the generation response. If the background insert fails, the error is logged to the application logger — no retry, no impact on the query response.

---

## 3. API

All endpoints are admin-only. Auth: standard JWT auth. Role check: `user.role = 'admin'` — 403 if not.

### 3.1 List traces

```
GET /api/v1/admin/rag-debug
```

Returns recent retrieval traces across all users, newest first. Joined with message and conversation metadata.

**Query parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `page` | int | 1 | Page number (1-indexed) |
| `page_size` | int | 50 | Max 100 |
| `scope` | string | — | Filter: `project_kb` or `agent_kb` |
| `gating_decision` | string | — | Filter: `injected` or `below_threshold` |
| `user_id` | uuid | — | Filter by user |
| `project_id` | uuid | — | Filter by project |
| `query` | string | — | Substring search on `query_text` (case-insensitive) |
| `since` | ISO 8601 | — | Filter: created_at ≥ this timestamp |
| `until` | ISO 8601 | — | Filter: created_at ≤ this timestamp |

**Response 200:**

```json
{
  "traces": [
    {
      "id": "uuid",
      "message_id": "uuid",
      "created_at": "ISO 8601",
      "scope": "project_kb",
      "query_text": "What was the outcome of the Q3 review?",
      "gating_decision": "injected",
      "vector_candidate_count": 20,
      "mmr_selection_count": 6,
      "injected_chunk_count": 4,
      "user": {
        "id": "uuid",
        "name": "Jane Smith",
        "email": "jane@example.com"
      },
      "project": {
        "id": "uuid",
        "name": "Q3 Review"
      },
      "conversation_id": "uuid"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 50,
    "total": 312
  }
}
```

`vector_candidate_count`, `mmr_selection_count`, `injected_chunk_count` are derived from the jsonb array lengths. They are computed at query time — not stored as separate columns.

### 3.2 Get trace detail

```
GET /api/v1/admin/rag-debug/{id}
```

Returns the full trace for a single `retrieval_debug_logs` row, including all jsonb payload.

**Response 200:**

```json
{
  "id": "uuid",
  "message_id": "uuid",
  "created_at": "ISO 8601",
  "scope": "project_kb",
  "query_text": "What was the outcome of the Q3 review?",
  "query_variants": null,
  "vector_candidates": [
    { "chunk_id": "uuid", "score": 0.91 },
    { "chunk_id": "uuid", "score": 0.87 }
  ],
  "mmr_selections": [
    { "chunk_id": "uuid", "score": 0.91 },
    { "chunk_id": "uuid", "score": 0.74 }
  ],
  "rerank_scores": null,
  "gating_decision": "injected",
  "injected_chunks": [
    {
      "chunk_id": "uuid",
      "score": 0.91,
      "text_preview": "The Q3 revenue came in at $2.1M, exceeding the target..."
    }
  ],
  "user": {
    "id": "uuid",
    "name": "Jane Smith",
    "email": "jane@example.com"
  },
  "project": {
    "id": "uuid",
    "name": "Q3 Review"
  },
  "conversation_id": "uuid"
}
```

**Error responses:**

| Status | Code | Condition |
|---|---|---|
| 403 | `forbidden` | Caller is not admin |
| 404 | `not_found` | Trace ID does not exist |

---

## 4. UI

Location: **Admin panel → RAG Debug tab** (third tab after Users and LLM Models).

### 4.1 Toolbar

- **Search input:** substring search on query text. Client sends `?query=` param on each keystroke (debounced 300ms).
- **Scope filter:** dropdown — All / Project KB / Agent KB.
- **Gating filter:** dropdown — All / Injected / Below threshold.
- **Date range:** two date pickers (since / until). Optional — clears to show all.
- **User filter:** dropdown of all users (fetched from `/api/v1/admin/users`). Optional.

Filters compose — all active filters apply simultaneously.

### 4.2 Trace list table

Columns: **Query**, **Scope**, **Decision**, **Candidates → MMR → Injected**, **User**, **Project**, **Timestamp**

| Column | Description |
|---|---|
| Query | First 80 characters of `query_text`. Full text in tooltip on hover. |
| Scope | Badge: `Project KB` (blue) or `Agent KB` (purple). |
| Decision | Badge: `injected` (green) or `below threshold` (amber). |
| Candidates → MMR → Injected | Three numbers in a compact funnel display: e.g. `20 → 6 → 4`. |
| User | User display name + email. |
| Project | Project name. Clicking navigates to the project (opens in new tab). |
| Timestamp | Relative time (e.g. "3 hours ago"). Full ISO timestamp in tooltip. |

Clicking a row opens the **trace detail panel** (see §4.3). No page navigation — panel slides in from the right.

Pagination: 50 rows per page. Next/previous page controls below the table.

**Empty state:** "No retrieval traces found. Traces appear after users receive AI responses grounded in KB content." (Shown when no data exists or filters return zero results.)

### 4.3 Trace detail panel

Slides in from the right when a table row is clicked. Closes with ESC or an X button.

**Header:** Query text (full, not truncated). Below: Scope badge, Decision badge, timestamp, user + project name.

**Sections:**

#### Vector Search Results
Collapsible. Shows `vector_candidates` as a ranked list:
- Rank, chunk ID (truncated to 8 chars), similarity score (4 decimal places), a visual score bar (width = score × 100%).
- If `gating_decision = 'below_threshold'`, all candidates are shown with an amber banner: "All candidates fell below the similarity threshold (0.3). Nothing was injected."

#### MMR Selections
Collapsible. Shows `mmr_selections` — same format as above, but only the post-MMR subset. Indicates how many candidates were pruned: "6 of 20 selected by MMR."

#### Injected Chunks
Always expanded. Shows `injected_chunks` with chunk ID, score, and the `text_preview` string displayed as a blockquote. If `injected_chunks` is empty (gating failed or embedding error), shows: "No chunks were injected."

#### V1 Fields
If `query_variants` or `rerank_scores` are non-null (V1 only), show them in collapsible sections. In MVP these are always null — sections are hidden entirely (not shown as empty).

### 4.4 No edit actions

The RAG Debug tab is fully read-only. No create, update, or delete controls.

---

## 5. Access Control

| Layer | Enforcement |
|---|---|
| Route guard (frontend) | Admin sidebar tab not rendered for non-admin users. Direct URL access redirects to home. |
| API middleware | Every `/api/v1/admin/rag-debug` request checks `user.role = 'admin'`. Returns 403 if not. |
| RLS | `retrieval_debug_logs` SELECT restricted to admin role in Supabase RLS. Service role handles all INSERTs. |

Three independent layers enforce admin-only access. A non-admin user cannot reach the data through any path.

---

## 6. Performance

The write path (inserting trace rows) must not add latency to the query response:

- Insert fires as a `TaskDispatcher` background task after retrieval result is assembled — before generation starts, but not in the critical path.
- If the insert fails: error is logged (structured JSON to application logger), not raised. The generation continues unaffected. No retry in MVP.
- The read path (GET endpoints) runs against `retrieval_debug_logs` which is admin-only. No caching needed — admin usage is infrequent.

**Index:** `retrieval_debug_logs` needs an index on `created_at DESC` for list pagination. This is not in the current schema spec — Gilfoyle should add it in the implementation ADR or migration.

---

## 7. Edge Cases

| Case | Behavior |
|---|---|
| RAG returns 0 chunks (all below threshold) | `gating_decision = 'below_threshold'`. `vector_candidates` shows what was retrieved and scored. `mmr_selections` and `injected_chunks` are empty arrays. UI shows the amber "below threshold" state with candidates still visible for diagnosis. |
| Vector search returns 0 candidates (empty KB or embedding too dissimilar) | `vector_candidates = []`, `mmr_selections = []`, `injected_chunks = []`, `gating_decision = 'below_threshold'`. Logged as normal — trace row is written. |
| Query embedding fails | Retrieval cannot run. Log entry is still written with `query_text` populated, `vector_candidates = []`, `gating_decision = 'below_threshold'`, and an `error` field added to the jsonb payload: `{ "error": "embedding_failed", "message": "..." }`. UI: if `error` key is present in any jsonb payload, show a red banner in the detail panel: "Retrieval failed — see error details." |
| Agent not active (no L9) | Only one log row is written (for L8 / `project_kb`). No `agent_kb` row. Normal — not an error. |
| Project-level conversation without project KB | Retrieval runs but finds no chunks. Same as empty KB case above. |
| Trace older than 30 days | Automatically deleted by scheduled purge. Not surfaced in UI (404 if navigated to directly). |
| No traces exist | Empty state shown (see §4.2). |

---

## 8. Open Questions

None. Spec is complete for Gilfoyle pre-implementation review.
