# Code Review: KIN-326 — Admin RAG Debug Tab
**Date:** 2026-03-23
**Reviewer:** Gilfoyle
**Verdict:** CHANGES_REQUESTED — 2 Critical, 4 Important
**Round:** 1

---

## Summary

Implementation is structurally correct: the async write pattern, join-at-read for chunk enrichment, run_in_executor usage in the routes, cursor pagination logic, and frontend architecture all follow the arch review checklist. The migration schema matches db-schema-spec.md §20 on column names, types, and index. Test coverage is broad.

Two Critical items block approval: (1) the RLS SELECT policy uses the wrong JWT path and will silently deny all users including admins in any non-service-role context, and (2) neither API route wraps its Supabase calls in try/except — unhandled DB exceptions surface as raw 500s with no error shape.

---

## Critical Findings

### C1 — Migration: RLS SELECT policy uses wrong JWT claim path
**File:** `packages/api/migrations/20260323000003_create_retrieval_debug_logs.sql` line 35
**Severity:** Critical
**Category:** rls-bypass

**Problem:**
```sql
USING (auth.jwt() ->> 'role' = 'admin');
```
`role` is stored in `public.users.role` (a DB column, type `user_role`), not in the Supabase JWT payload as a top-level claim. `auth.jwt() ->> 'role'` returns NULL for all users — the standard Supabase JWT contains `sub`, `email`, `aud`, `app_metadata`, `user_metadata`, not a `role` field at the top level. This policy silently evaluates to `false` for every authenticated user, including admins.

The established RLS pattern in this codebase (see `001_create_users.sql` lines 83–91) uses a subquery against `public.users`:
```sql
EXISTS (
  SELECT 1 FROM public.users u
  WHERE u.id = auth.uid() AND u.role = 'admin'
)
```

**Current impact:** The API routes use the service-role Supabase client (`get_supabase()`), which bypasses RLS entirely. So the broken policy is dormant in production — reads work. But: (a) RLS is security infrastructure and should be correct regardless of who's reading; (b) any future test, script, or Supabase Studio query using an authed user-role client will silently return zero rows; (c) if the client is ever changed to anon-key for a read path, the policy becomes an active data-access failure.

**Fix:**
```sql
CREATE POLICY "admin_select_retrieval_debug_logs"
    ON retrieval_debug_logs
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.users u
            WHERE u.id = auth.uid() AND u.role = 'admin'
        )
    );
```

---

### C2 — Routes: No error handling on Supabase calls
**Files:** `packages/api/app/api/routes/admin_rag_debug.py` lines 71–74, 136–144, 156–163
**Severity:** Critical
**Category:** error-swallow

**Problem:** Neither `list_rag_debug_traces` nor `get_rag_debug_trace` wraps its `run_in_executor` calls in try/except. A Supabase timeout, connection failure, or unexpected client exception propagates as an unhandled exception. FastAPI will catch it and return a 500, but with no consistent error shape. This violates conventions.md § Error Handling ("Every API endpoint needs explicit error handling with meaningful status codes and messages") and the project's standard error response format `{ error: { code, message, details? } }`.

The existing error infrastructure (`app.core.errors`) already provides the right shapes — this is a missing try/except, not a missing framework.

**Fix (both routes — same pattern):**
```python
try:
    result = await loop.run_in_executor(
        None,
        lambda: _list_traces_sync(client, limit, cursor, scope),
    )
except Exception as exc:
    logger.error("list_rag_debug_traces: DB query failed: %s", exc)
    raise  # re-raise to let the exception handler return a 500 with proper shape
```

Note: re-raising is correct here (read-path failure is a real error, not a fail-open situation). The exception handlers in `add_exception_handlers` will format it correctly. The point is that a bare `logger.error` call must precede any unhandled propagation — right now there is no logging at all.

---

## Important Findings

### I1 — Tests: `WRITER_PATCH` constant is dead code / wrong patch target
**File:** `packages/api/tests/test_admin_rag_debug.py` line 25
**Severity:** Important
**Category:** test-missing

**Problem:**
```python
WRITER_PATCH = "app.services.rag.trace_writer.get_supabase"
```
`trace_writer.py` does not import `get_supabase`. The supabase client is injected as a parameter (`supabase` arg) — the module has zero internal imports of `get_supabase`. This patch target does not exist and would silently no-op if used. It is never referenced in any test (no `with patch(WRITER_PATCH, ...)` call in the file). Dead constant, but it signals the test was written with a wrong mental model of the module interface. Remove the constant. If a future test needs to exercise the full dispatch chain, it should patch at the `TaskDispatcher.dispatch` level, not at an imaginary import.

---

### I2 — Frontend: Fragment key missing on trace rows map
**File:** `packages/web/app/admin/rag-debug/page.tsx` lines 446–483
**Severity:** Important
**Category:** other

**Problem:**
```tsx
{traces.map((trace) => (
  <>
    <tr key={trace.id} ...>
    {expandedId === trace.id && (
      <tr key={`${trace.id}-detail`} ...>
    )}
  </>
))}
```
The outer `<>` fragment has no `key`. React requires the key on the outermost element returned by a `.map()` — not on the children inside it. React will emit a "Each child in a list should have a unique key" warning in development. The key on the inner `<tr>` is irrelevant to the fragment's identity.

**Fix:**
```tsx
{traces.map((trace) => (
  <React.Fragment key={trace.id}>
    <tr className={...} onClick={() => toggleExpand(trace.id)}>
      ...
    </tr>
    {expandedId === trace.id && (
      <tr className="border-b border-border bg-muted/10">
        ...
      </tr>
    )}
  </React.Fragment>
))}
```
Remove the redundant `key` props from the inner `<tr>` elements after this change.

---

### I3 — API: `scope` query param accepts arbitrary strings without validation
**File:** `packages/api/app/api/routes/admin_rag_debug.py` lines 51–52, 110–112
**Severity:** Important
**Category:** api-contract

**Problem:** The `scope` param is typed as `Optional[str]` with no constraint. Invalid values (e.g., `scope=FOO`) are passed directly to `.eq("scope", scope)`. The `retrieval_scope` enum in Postgres will return zero rows rather than an error — caller gets a misleading empty result instead of a 400. Conventions require input validation at the API boundary.

**Fix:** Add a `Literal` annotation or explicit validation:
```python
from typing import Literal, Optional
scope: Optional[Literal["project_kb", "agent_kb"]] = Query(None, ...)
```
FastAPI will return a 422 with a clear validation error for any value outside the enum.

---

### I4 — Spec doc gap: `next_cursor` type annotated as "uuid" but implementation emits ISO timestamp
**File:** `docs/specs/rag-debug-tab-spec.md` line 75
**Severity:** Important
**Category:** spec-gap

**Problem:** The spec response schema shows `"next_cursor": "uuid | null"`. The implementation (consistent with the arch review's cursor-by-`created_at` decision) returns an ISO-8601 timestamp string, not a UUID. The test `test_list_next_cursor_set_when_full_page_returned` asserts `"2026-03-23T10:00:00+00:00"` — also a timestamp. The spec type annotation is wrong and will mislead anyone integrating against this endpoint.

**Fix:** Update spec §2 response schema:
```json
"next_cursor": "ISO-8601 timestamp | null"
```
No code change needed. Spec update only.

---

## What Is Correct

- `trace_writer.py`: sync function design is right. `try/except` on the `insert().execute()` call is correctly scoped. Log-and-continue on failure matches spec §5. Client injection via parameter (not internal import) is the correct testable pattern.
- `run_in_executor` usage: both routes use `asyncio.get_running_loop()` (not deprecated `get_event_loop()`). Sync Supabase calls are correctly offloaded.
- Migration schema: all columns, types, and constraints match `db-schema-spec.md §20` exactly (`error_message`, `idx_retrieval_debug_logs_created_at`, `ON DELETE CASCADE` on `message_id`). Append-only convention honored (no `updated_at`). Deny-insert policy for user role is correct.
- Router wiring: `admin_rag_debug_router` registered in `main.py`. Correct.
- `require_admin` dependency: applied to both endpoints. Correct.
- Join-at-read (Option B): implementation matches arch review §5 exactly. `isinstance(doc, list)` guard for Supabase embedded-select response shape is correct and defensive.
- Cursor pagination: `next_cursor` set iff `len(traces) == limit`. Edge-free logic.
- Frontend scope filter: re-fetches from page 0 on filter change (via `fetchTraces()` in `useEffect([fetchTraces])`). Cursor reset on filter change (`setLoaded(false)`, `setExpandedId(null)`) is correct.
- Frontend `TraceDetailPanel`: `mounted` guard prevents state updates after unmount. Correct.
- Test coverage: 13 tests, all meaningful scenarios covered. Admin-only enforcement tested for both endpoints. Scope filter, cursor, pagination, 404, enrichment, empty-chunk skip all have dedicated tests.

---

## Required Changes

| # | File | Change |
|---|---|---|
| C1 | `migrations/20260323000003_create_retrieval_debug_logs.sql` | Replace `auth.jwt() ->> 'role' = 'admin'` with `EXISTS (SELECT 1 FROM public.users u WHERE u.id = auth.uid() AND u.role = 'admin')` |
| C2 | `app/api/routes/admin_rag_debug.py` | Add try/except + logger.error around both run_in_executor blocks in both route handlers |
| I1 | `tests/test_admin_rag_debug.py` | Remove dead `WRITER_PATCH` constant |
| I2 | `app/admin/rag-debug/page.tsx` | Replace `<>` with `<React.Fragment key={trace.id}>` in traces.map() |
| I3 | `app/api/routes/admin_rag_debug.py` | Add `Literal["project_kb", "agent_kb"]` type constraint to `scope` Query param |
| I4 | `docs/specs/rag-debug-tab-spec.md` | Fix `next_cursor` type annotation from "uuid" to "ISO-8601 timestamp" |
