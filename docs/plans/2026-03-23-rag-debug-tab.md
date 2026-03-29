# Admin RAG Debug Tab — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Admin RAG Debug tab — backend trace storage + paginated read endpoints + frontend trace inspector.

**Architecture:** Sync `write_retrieval_trace()` background function writes to `retrieval_debug_logs`; two admin-only read endpoints serve the table; frontend replaces the stub page. No chat route exists yet — trace writer is built standalone for integration when generation is implemented.

**Tech Stack:** FastAPI, Supabase Python client (sync + run_in_executor), pytest, Next.js 14, shadcn/ui, Tailwind

**Spec:** `docs/specs/rag-debug-tab-spec.md` (Approved)
**Architecture review:** `reviews/2026-03-23-kin332-arch-review.md`
**Schema:** `docs/db-schema-spec.md §20` (`retrieval_debug_logs`)

---

## Task 1: DB Migration

**Files:**
- Create: `packages/api/migrations/20260323000003_create_retrieval_debug_logs.sql`

**Steps:**

1. Write migration per schema spec §20. Required columns: `id`, `message_id` (FK → messages ON DELETE CASCADE), `scope` (retrieval_scope enum), `query_text`, `query_variants`, `vector_candidates` (jsonb), `mmr_selections` (jsonb), `rerank_scores` (jsonb), `gating_decision` (text NOT NULL), `injected_chunks` (jsonb), `error_message` (text), `created_at`. No `updated_at` — append-only.

2. Add index: `CREATE INDEX idx_retrieval_debug_logs_created_at ON retrieval_debug_logs (created_at DESC);`

3. Add RLS policies:
   - SELECT: admin role only (`auth.jwt() ->> 'role' = 'admin'`)
   - INSERT: service role only (no user-facing RLS for inserts)

4. Verify all column names/types match `db-schema-spec.md §20` exactly before saving.

5. Commit: `feat: add retrieval_debug_logs migration`

---

## Task 2: Trace Writer Service

**Files:**
- Create: `packages/api/app/services/rag/trace_writer.py`
- Test: `packages/api/tests/test_admin_rag_debug.py` (partial — trace writer unit tests)

**Steps:**

1. Write `test_write_retrieval_trace_success` — mock supabase, assert `table("retrieval_debug_logs").insert(row).execute()` called with correct fields. Run → FAIL.

2. Implement `write_retrieval_trace(message_id, scope, query_text, vector_candidates, mmr_selections, injected_chunks, gating_decision, supabase, *, error_message=None)` — sync function (designed for `BackgroundTasks.add_task`). Wraps in `try/except Exception` with `logger.error(...)`. Never re-raises.

3. Write `test_write_retrieval_trace_db_failure_is_silent` — mock supabase insert to raise, assert no exception propagates.

4. Write `test_write_retrieval_trace_error_case` — pass `gating_decision="error"` + `error_message="..."`, assert both land in the insert row.

5. Run all three tests → PASS.

6. Commit: `feat: add retrieval trace writer service`

---

## Task 3: Admin RAG Debug List Endpoint

**Files:**
- Create: `packages/api/app/api/routes/admin_rag_debug.py`
- Test: `packages/api/tests/test_admin_rag_debug.py` (extend)

**Steps:**

1. Write `TestRagDebugList`:
   - `test_list_returns_traces` — admin_client, mock supabase, assert 200 + `{"traces": [...], "next_cursor": null}`
   - `test_list_scope_filter` — pass `scope=project_kb`, assert filter applied in query
   - `test_list_cursor_pagination` — pass `cursor=<uuid>`, assert `lt` filter on `created_at` applied
   - `test_list_non_admin_returns_403` — client (non-admin), assert 403

2. Implement `GET /api/v1/admin/rag-debug` in `admin_rag_debug.py`:
   - `require_admin` dependency
   - Query params: `limit: int = Query(50, ge=1, le=200)`, `cursor: Optional[str] = None`, `scope: Optional[str] = None`
   - Select summary fields: `id, message_id, scope, query_text, gating_decision, created_at` + compute `injected_chunk_count` and `vector_candidate_count` from JSONB length
   - Order `created_at DESC`. Apply `lt` filter on `created_at` when cursor present.
   - Return `{"traces": [...], "next_cursor": traces[limit-1]["id"] if len(traces) == limit else None}`
   - All Supabase calls wrapped in `run_in_executor`.

3. Run `TestRagDebugList` → PASS.

4. Commit: `feat: admin RAG debug list endpoint`

---

## Task 4: Admin RAG Debug Detail Endpoint

**Files:**
- Modify: `packages/api/app/api/routes/admin_rag_debug.py`
- Test: `packages/api/tests/test_admin_rag_debug.py` (extend)

**Steps:**

1. Write `TestRagDebugDetail`:
   - `test_detail_returns_full_trace` — assert all JSONB fields present + `injected_chunks` enriched with `document_title` and `section_path`
   - `test_detail_not_found_returns_404` — mock returns no data
   - `test_detail_non_admin_returns_403`
   - `test_detail_no_chunks_skips_join` — `injected_chunks: []`, assert no chunk lookup performed

2. Implement `GET /api/v1/admin/rag-debug/{trace_id}`:
   - Fetch full row from `retrieval_debug_logs` by `id` — 404 if not found
   - Join-at-read for injected chunks (Gilfoyle Option B): extract `chunk_id` values from `injected_chunks` JSONB, query `knowledge_base_chunks.select("id, section_path, document_id, knowledge_base_documents(title)").in_("id", chunk_ids)`, merge `document_title`/`section_path` back into `injected_chunks` list before returning
   - Skip join when `injected_chunks` is null or empty
   - All Supabase calls in `run_in_executor`

3. Run `TestRagDebugDetail` → PASS.

4. Commit: `feat: admin RAG debug detail endpoint`

---

## Task 5: Wire Router

**Files:**
- Modify: `packages/api/app/main.py`

**Steps:**

1. Import `router as admin_rag_debug_router` from `app.api.routes.admin_rag_debug`.

2. Add `app.include_router(admin_rag_debug_router)` after `admin_users_router` include.

3. Run full test suite: `pytest packages/api/tests/ -v`. Verify all tests pass (including new ones).

4. Commit: `chore: register admin_rag_debug router`

---

## Task 6: Frontend — RAG Debug Page

**Files:**
- Modify: `packages/web/app/admin/rag-debug/page.tsx`

**Steps:**

1. Replace stub with real implementation. Follow patterns from `app/admin/models/page.tsx` (client component, `apiFetch`, `useToast`).

2. State: `traces`, `loaded`, `nextCursor`, `scopeFilter` (`"all" | "project_kb" | "agent_kb"`), `expandedId`.

3. On mount + scope change: `GET /api/v1/admin/rag-debug?scope=<filter>&limit=50`.

4. Render:
   - Scope dropdown: "All" / "Project KB" / "Agent KB"
   - Table with columns: Timestamp, Query (truncated 80 chars), Scope badge, Outcome badge (`injected`=green, `below_threshold`=amber, `error`=red), Chunks injected, Candidates
   - Click row → expand inline panel, fetch `GET /api/v1/admin/rag-debug/{id}` for full trace
   - Detail panel sections (collapsible): **Query** (full text, scope, timestamp) | **Vector Search** (table: chunk ID truncated, doc title, score) | **MMR Selection** (selected chunks highlighted, dropped dimmed) | **Threshold Gate** (threshold value, pass/fail per chunk) | **Injected Chunks** (text_preview, doc title, score)
   - Error state: show error badge + message instead of pipeline sections

5. Load more: if `nextCursor`, show "Load more" button, append to list.

6. TypeScript: define `RagTraceSummary` and `RagTraceDetail` interfaces in the component file.

7. Run: `./node_modules/.bin/tsc --noEmit` from `packages/web/`. Fix any TypeScript errors.

8. Commit: `feat: admin RAG debug page — trace table + detail inspector`

---

## Done When

- [ ] Migration file created with correct schema (cross-checked vs `db-schema-spec.md §20`)
- [ ] `write_retrieval_trace()` handles failure silently, never raises
- [ ] `GET /api/v1/admin/rag-debug` returns 200 for admin, 403 for non-admin; scope + cursor filtering work
- [ ] `GET /api/v1/admin/rag-debug/{trace_id}` returns full trace + enriched chunk metadata; 404 on missing
- [ ] All tests pass (run `pytest packages/api/tests/ -v`)
- [ ] TypeScript clean (`tsc --noEmit`)
- [ ] Frontend renders trace list + expandable detail panel

## Test Strategy

All backend tests mock Supabase. Use `admin_client` fixture (from conftest.py) for admin endpoints. Use `client` fixture for 403 tests. `PATCH_TARGET = "app.api.routes.admin_rag_debug.get_supabase_client"` pattern. No integration tests needed.

## Notes

- `injected_chunk_count` / `vector_candidate_count` are computed at read time from JSONB array length — not stored columns. Use Python `len(row.get("injected_chunks") or [])` after fetching.
- `cursor` is a `created_at` UUID cursor, not a page number. The list query filters `created_at < cursor_created_at` — you'll need to store the `created_at` of the last item, not its `id`, for the next page query. Simplest approach: pass `created_at` of last item as the cursor value (ISO string), filter with `.lt("created_at", cursor)`.
- Trace write integration into the generation endpoint is out of scope for this ticket — `write_retrieval_trace` is available for that endpoint to call via `TaskDispatcher.dispatch(write_retrieval_trace, ...)` when implemented.
