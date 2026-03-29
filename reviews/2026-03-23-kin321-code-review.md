# Code Review: KIN-321 — MCP Context Endpoint

**Date:** 2026-03-23
**Reviewer:** Gilfoyle
**Verdict:** CHANGES_REQUESTED
**Findings:** 2 Critical, 1 Important

---

## Files Reviewed

- `packages/api/app/api/routes/mcp.py` (new)
- `packages/api/app/main.py` (mcp_router registration)
- `packages/api/tests/test_mcp.py` (32 tests)

**Reference:** ADR-006 §4, `docs/db-schema-spec.md` §8/§18/§21

---

## Critical Findings

### C1 — Missing ownership/visibility check on project, company, and agent

**File:** `packages/api/app/api/routes/mcp.py`, lines 197–239

**Problem:** After fetching project, company, and agent rows, the endpoint does not verify that the authenticated user is allowed to access them. For projects and companies, the code fetches by `id` only — no filter on `user_id`. For agents, it fetches `owner_id` and `visibility` but never asserts `visibility = 'public' OR owner_id = user_id`. The ADR-006 §4 Step 3 explicitly states: "Verify user owns/can access each requested entity. Reject 403 if unauthorized."

**Consequence:** Any authenticated MCP token holder can read any project, company, or private agent in the database by guessing (or knowing) the UUID. This is an ACL leak.

**Fix required:**
- Projects: add `.eq("user_id", user_id)` (projects belong to a user per schema §4). If `r.data` is null after the ownership filter, raise `NotFoundError` (do not 403 — don't reveal existence).
- Companies: add `.eq("user_id", user_id)` (companies §3 have `user_id`). Same null → NotFoundError pattern.
- Agents: after fetching, assert `agent_row["owner_id"] == user_id or agent_row["visibility"] == "public"`. If neither, raise `NotFoundError` (same reasoning — don't confirm existence to an unauthorized caller).

Note: returning 404 on unauthorized access is the correct pattern here (prevents entity enumeration). The ADR says 403, but per ADR-006 §4 rationale ("prevents an attacker from probing entity existence"), 404 is more consistent.

---

### C2 — Rate limiting is fully absent

**File:** `packages/api/app/api/routes/mcp.py`

**Problem:** ADR-006 §3 and §4 define a per-user daily rate limit enforced via the `mcp_rate_limits` table (db-schema-spec §21). The implementation contains no rate limit check, no UPSERT increment, and no HTTP 429 path. The ADR validation order is: Auth → Rate limit → Scope → Assemble. The current implementation goes directly from Auth to Scope.

**Consequence:** Per-user daily cap (1,000 req/day, HTTP 429 on exceed) from MEMORY.md decision 2026-03-21 is not enforced. Any token holder can hammer the endpoint without bound.

**Fix required:** Add a `_check_and_increment_rate_limit(user_id, client, loop)` async helper between `_authenticate` and scope validation. Pattern per ADR-006 §3:
1. Query `mcp_rate_limits` for `(user_id, CURRENT_DATE)`.
2. If `request_count >= daily_cap`, raise `RateLimitError` (already defined in `app/core/errors.py` → HTTP 429).
3. UPSERT to increment count.

All Supabase calls must use `run_in_executor` per conventions.

Tests needed: one test for 429 when count >= cap, one test that a first-request user succeeds (no rate limit row yet).

---

## Important Findings

### I1 — `project_id + company_id` scope: company row is fetched but never used in context assembly

**File:** `packages/api/app/api/routes/mcp.py`, lines 210–224, 258–268

**Problem:** When both `project_id` and `company_id` are provided, the code fetches the company row from the DB (line 213) even though the L3 assembly block at line 259 uses `project_row` (project wins) and the company row is never injected into the context. This is a wasted DB query on every request with both params set.

**Consequence:** Minor — it's not a correctness bug (the right data is assembled), but it is unnecessary I/O and the company `NotFoundError` check on line 221 would 404 on a non-existent company even when project takes precedence. A caller could get a 404 for a company_id they provided as optional context, which is confusing.

**Fix:** Only fetch the company row if `body.company_id` is provided AND `body.project_id` is NOT provided. Move the company fetch inside `if body.company_id and not body.project_id`.

---

## Areas That Pass

**Token auth:** SHA-256 hashing (`_hash_token`) matches ADR-006 §1. `mcp_` prefix stripping is correct. Revocation check (`.is_("revoked_at", "null")`) is correct. No plaintext token exposure anywhere. `last_used_at` stamped via background task — correct pattern (non-blocking).

**Async correctness:** Every Supabase call uses `run_in_executor` with `get_running_loop()`. Fully compliant with conventions.

**Error shapes:** All raises use `app/core/errors.py` typed exceptions that map to correct HTTP codes (401 → `AuthenticationError`, 400 → `ValidationError`, 404 → `NotFoundError`).

**Layer routing (`resolve_layers`):** Logic matches the ADR-006 §4 scoping table for all 7 combinations. L4 is correctly absent. The function is pure and unit-testable.

**Context assembly:** L1 static text, L2 user (name + bio), L3 (project wins over company), L5 (agent instructions). Project-wins-for-L3 behavior is correct per the scoping table. `token_count_estimate` formula (`len // 4`) is a reasonable approximation.

**`main.py`:** `mcp_router` registered correctly. No ordering issue relative to other routers.

**Test coverage (32 tests):** Auth tests (5), request validation (8), scope routing (8), context assembly (11). Coverage is solid for what's implemented. Two tests are missing for the rate limit (C2). No test for the ACL bypass (C1) — add tests that a user cannot access another user's private data.

---

## Summary

Two blocking issues. Rate limiting is an unimplemented ADR requirement, not a future nice-to-have — it's in the locked decisions table. The ownership check is a security hole that lets any valid MCP token read any entity. Both must be fixed before this can ship.
