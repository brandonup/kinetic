# Architecture Review: KIN-332 — Admin RAG Debug Tab
# Spec: `docs/specs/rag-debug-tab-spec.md`

**Date:** 2026-03-23
**Reviewer:** Gilfoyle
**Verdict:** APPROVED with schema corrections
**Findings:** 2 schema gaps (corrected below), 1 implementation note, 1 open-question resolution

---

## 1. Async Write Ordering — CONFIRMED

**Decision:** Write the trace via `TaskDispatcher` in the route handler body, not inside the SSE generator.

FastAPI `BackgroundTasks` execute **after the full response is sent** — for SSE, this means after the stream closes. The spec says "concurrently" which is slightly imprecise; the trace is written sequentially after the stream ends, not literally in parallel. This is correct behavior: it doesn't delay SSE delivery and doesn't block the user.

**Implementation note for Dinesh:** Register the task before returning the `StreamingResponse`, not inside the `async def generate()` iterator:

```python
# CORRECT: register in route handler body
@router.post("/chat")
async def chat(request: ChatRequest, background_tasks: BackgroundTasks, ...):
    # ... run retrieval pipeline, assemble context ...
    background_tasks.add_task(write_retrieval_trace, trace_data, client)
    return StreamingResponse(generate(context, ...), media_type="text/event-stream")

# WRONG: registering inside the generator means the task only fires after the
# generator is exhausted (same net timing), but it's also awkward and non-obvious.
async def generate(context, ...):
    background_tasks.add_task(...)  # don't do this
    for chunk in stream:
        yield chunk
```

**Why it matters:** If trace registration is inside the generator, the background task is added to the task queue during streaming rather than at request ingress. Same net result in this case, but the correct pattern is route handler registration — consistent with how the existing `TaskDispatcher` abstraction is used elsewhere.

**Failure isolation:** Per spec §5: if trace write fails, log server-side and continue. Never fail a user query over a trace write failure. Dinesh must wrap the write function in a try/except and log-only on failure.

---

## 2. Index on `retrieval_debug_logs(created_at DESC)` — SCHEMA GAP

**Finding:** The `GET /api/v1/admin/rag-debug` list endpoint paginates by `created_at DESC`. The schema in `db-schema-spec.md §20` has no index on `created_at`.

**Fix required:** Add to `db-schema-spec.md §20`:

```
- `idx_retrieval_debug_logs_created_at` on `(created_at DESC)`
```

Without this, the list query does a full table scan sorted by timestamp. At MVP volume this is tolerable, but the index is trivially cheap to add and should be there from day one. **I am updating the schema spec directly.**

---

## 3. `error_message` Column — SCHEMA GAP

**Finding:** Spec §6 edge cases define: "Query embedding fails → log with `gating_decision: 'error'`, `error_message: '<error detail>'`". There is no `error_message` column in `retrieval_debug_logs` in `db-schema-spec.md §20`.

**Assessment:**
- `gating_decision: "error"` is valid — the column is `text NOT NULL`, not a closed enum. "error" as a value is fine.
- `error_message` has no home. Options:
  - **Option A:** Add `error_message text NULL` column — clean, queryable, explicit.
  - **Option B:** Shove error details into an existing jsonb column (e.g., `injected_chunks` with `[]` + a top-level "error" key). Messy, non-standard.

**Decision:** Option A. Add `error_message text NULL` to `retrieval_debug_logs`. Admin tools that need to display error context have a clean field to query. **I am updating the schema spec directly.**

---

## 4. Detail Panel Join Path — PERFORMANT

The join chain: `retrieval_debug_logs.id → messages(id) → conversations(id) → projects(id) + users(id)`

All joins are on primary keys (indexed). No additional indexes needed for the detail endpoint. This is a single-row lookup — an admin clicking into a trace detail triggers one 4-table join, all on PKs. Acceptable.

For the injected chunks join at read time (see §5 below), the lookup is `knowledge_base_chunks.id IN (array of chunk IDs from jsonb)`. PK lookup, performant.

---

## 5. Open Question 1: Join vs. Denormalize for Chunk Display — OPTION B CONFIRMED

**Decision: Option B — join at read time.** Keep `injected_chunks` as `[{chunk_id, score, text_preview}]`. When the detail endpoint serves a trace, join `knowledge_base_chunks` and `knowledge_base_documents` via the extracted `chunk_id` values to get `document_title` and `section_path`.

**Rationale:**
- Admin reads are infrequent and single-row — a small join cost is irrelevant.
- `injected_chunks` denormalization bloat is permanent and accumulates over 30 days of traces. Not worth it for an admin diagnostic tool.
- No schema change needed.

**Implementation note for Dinesh (detail endpoint):**

```python
# After fetching the trace row, extract chunk IDs from injected_chunks JSONB,
# then join to get document metadata
chunk_ids = [c["chunk_id"] for c in trace["injected_chunks"] or []]
if chunk_ids:
    chunk_meta = await loop.run_in_executor(
        None,
        lambda: client
            .table("knowledge_base_chunks")
            .select("id, section_path, document_id, knowledge_base_documents(title)")
            .in_("id", chunk_ids)
            .execute(),
    )
    # merge into injected_chunks before returning
```

---

## Schema Corrections Applied

Both gaps resolved by direct edits to `docs/db-schema-spec.md §20`:

1. Added `error_message text NULL` column with note "Populated on embedding failure; null for successful retrievals."
2. Added `idx_retrieval_debug_logs_created_at` on `(created_at DESC)` to the Indexes section.

---

## Implementation Checklist for Dinesh (KIN-326)

1. **Backend:** `GET /api/v1/admin/rag-debug` — paginated list, cursor by `created_at DESC`. Requires `require_admin` dependency. Returns summary fields only (see spec §2).
2. **Backend:** `GET /api/v1/admin/rag-debug/{trace_id}` — full trace detail. Join `knowledge_base_chunks → knowledge_base_documents` for injected chunk display (Option B).
3. **Background write:** Register `TaskDispatcher.dispatch(write_trace_fn, ...)` in the chat route handler body **before** returning `StreamingResponse`. Wrap write in try/except; log-and-continue on failure — never fail the user query.
4. **Schema fields:** Use `error_message` column (now in schema) for embedding failure details. Set `gating_decision = "error"` on failure.
5. **Index:** `idx_retrieval_debug_logs_created_at` must be in the migration.
6. **Frontend:** Admin panel → RAG Debug tab. Scope dropdown filter. Expandable row detail with collapsible pipeline stage sections (Vector Search → MMR → Threshold Gate → Injected Chunks).
7. **Access control:** Two-layer (frontend route guard + API `require_admin` middleware). See spec §4.
8. **No `updated_at`:** `retrieval_debug_logs` is append-only per schema conventions.

**Spec reference:** `docs/specs/rag-debug-tab-spec.md`
**Schema reference:** `docs/db-schema-spec.md §20` (updated by this review)
