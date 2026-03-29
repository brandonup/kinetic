# Code Review: KIN-321 — MCP Context Endpoint (R2)

**Date:** 2026-03-24
**Reviewer:** Gilfoyle
**Round:** 2 (R1 was 2026-03-23)
**Verdict:** CHANGES_REQUESTED
**Findings:** 1 Critical, 2 Important

---

## R1 Findings — Status

| Finding | R1 Verdict | R2 Status |
|---|---|---|
| C1 — ACL bypass (no ownership checks on project/company/agent) | Critical | **Resolved.** Projects filter `.eq("user_id", user_id)`. Companies enforce `user_id` when explicit. Agent visibility/owner check in place. |
| C2 — Rate limiting absent | Critical | **Partially resolved — new defect introduced (see C1 below).** Rate limiting is implemented, but the increment logic is not atomic. |
| I1 — project+company_id: unnecessary company fetch | Important | **Resolved.** Company is fetched in both paths now, but L2 is correct for the `company_id + project_id` scope (spec §4.2 includes L2 for that combo). |

---

## Files Reviewed

- `packages/api/app/api/routes/mcp.py` (updated)
- `packages/api/tests/test_mcp.py` (updated, now 44+ tests)

---

## Critical Findings

### C1 — Rate limit increment is not atomic (check-then-act race condition)

**File:** `packages/api/app/api/routes/mcp.py`, lines 148–178

**Problem:** `_check_rate_limit` reads `request_count` from the DB (line 148–155), computes `new_count = row["request_count"] + 1` in Python (line 166), then upserts that computed value (lines 170–178). This is a check-then-act pattern, not an atomic increment.

ADR-006 §3 and spec §7 both explicitly prescribe the atomic SQL pattern:
```sql
DO UPDATE SET request_count = mcp_rate_limits.request_count + 1
```

The current upsert is:
```python
{"user_id": user_id, "date": today, "request_count": new_count}
```

This replaces the DB value with a Python-computed value. Under two concurrent requests when `request_count = 999`: both read 999, both compute 1000, both pass the cap check (999 < 1000), and both upsert 1000. The counter ends at 1000 instead of 1001, and both requests succeed when only one should. At MVP scale this is rarely triggered, but the ADR specified atomicity for correctness, and the implementation diverges from spec.

**Fix required:** Use a Supabase RPC call (or raw SQL via PostgREST) to perform the atomic check-and-increment in a single round-trip. Pattern:

```sql
-- A Postgres function `mcp_rate_limit_check_and_increment(p_user_id uuid, p_date date)`
-- returns: 'ok' | 'exceeded'
-- Performs the UPSERT and returns exceeded if request_count >= daily_cap after increment
```

Alternatively, accept eventual consistency with a comment acknowledging the race and document the known limitation. The simpler fix is to run the ADR's prescribed atomic UPSERT first (increment always), then check whether the resulting count exceeded the cap after the fact. This is slightly permissive (allows one extra request at the boundary) but far better than the current non-atomic read-compute-write.

---

## Important Findings

### I1 — `_check_rate_limit` write (UPSERT) error is silently swallowed

**File:** `packages/api/app/api/routes/mcp.py`, lines 170–178

**Problem:** The UPSERT block (lines 170–178) has no error handling. If the Supabase UPSERT fails (connection error, constraint violation), the exception propagates uncaught up to the FastAPI exception handler as an unhandled 500. This is acceptable behavior, but there is no log statement before the failure propagates. Per conventions: "Every `except` block must contain a log statement before any `return` or `pass`." More critically, if the UPSERT raises an exception *after* the cap check passed, the request is blocked with a 500 when the user should have gotten a 200. The rate counter is left unincremented, and the failed request counted against nothing.

**Fix:** Wrap the UPSERT in a try/except, log the error, and continue (read-path writes should fail-open with a logged warning — the rate limit write failing should not block context assembly). Convention cite: "Read-path fail-open (return `[]` on a failed search) is acceptable when documented with a comment."

---

### I2 — `mcp_tokens` schema: `name` column vs. spec §9 `label` field — schema gap flagged in KIN-321 tests, not tracked in schema spec

**File:** `packages/api/tests/test_mcp.py` (test constants); `docs/db-schema-spec.md` §18

**Problem:** `db-schema-spec.md` §18 defines the column as `name` (`"User label, e.g., 'Claude Desktop'"`). Spec §9.1 response shape uses `label` as the field name. ADR-006 notes that `db-schema-spec.md` §18 has a pending correction (bcrypt → SHA-256) but does not flag the `name`/`label` inconsistency. KIN-321 scope is auth/context, not token management, so this does not affect mcp.py. However, KIN-325 (token management UI) will hit this directly. The column name `name` vs. response field `label` mismatch must be resolved before KIN-325 implements the token list endpoint.

**Fix:** Update `db-schema-spec.md` §18 to rename `name` → `label` (or clarify in spec §9 that `label` maps to `name`). Must happen before KIN-325 starts. Not blocking KIN-321 — documenting here for tracking.

---

## Areas That Pass (R2)

**Token auth (unchanged):** SHA-256 hashing, `mcp_` prefix stripping, revocation check, `last_used_at` fire-and-forget — all correct.

**Async correctness (unchanged):** All Supabase calls use `run_in_executor` with `get_running_loop()`. Fully compliant.

**ACL checks (R1 C1 fixed):** Project ownership via `user_id` filter. Company ownership via `user_id` filter when explicit. Agent visibility check (public = any auth'd user; private = owner only; returns 404 to avoid existence confirmation). Cross-scope validation (project company_id must match body company_id) correct.

**Scope routing (unchanged):** `resolve_layers` correctly implements all 7 spec §4.2 combinations. L4 absent. L6 absent. Pure function.

**Context assembly (unchanged):** L1 (user name + bio), L2 (company), L3 (project instructions), L5 (agent instructions) assembled correctly. L7/L8/L9 stubs for KIN-322.

**Response shape (unchanged):** `context`, `metadata.layers_assembled`, `metadata.token_count_estimate`, `metadata.matched_framework_id`, `metadata.sources` all present. Matches spec §5.

**Test coverage:** 44 tests including auth (5), validation (8), scope routing (8), context assembly (13), rate limit (2 active + 4 skipped for KIN-322/KIN-323), ACL (5). Skipped tests correctly flagged with KIN ticket references. Coverage is solid for implemented scope.

---

## Summary

R1 Critical items resolved. One new Critical introduced: the rate limit increment is non-atomic — it diverges from the spec's explicit `DO UPDATE SET request_count = mcp_rate_limits.request_count + 1` requirement. One Important: UPSERT failure should fail-open with logging. Fix C1; I1 is straightforward. I2 is a schema doc gap to fix before KIN-325.
