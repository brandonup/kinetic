# Code Review: KIN-321 — MCP Context Endpoint (R3)

**Date:** 2026-03-24
**Reviewer:** Gilfoyle
**Round:** 3 (R2 was 2026-03-24, R1 was 2026-03-23)
**Verdict:** APPROVED
**Findings:** 0 Critical, 0 Important

---

## R2 Findings — Status

| Finding | R2 Verdict | R3 Status |
|---|---|---|
| C1 — Rate limit increment is not atomic (check-then-act race) | Critical | **Resolved.** `_check_rate_limit` calls `mcp_check_and_increment_rate_limit` RPC. Migration performs `INSERT ... ON CONFLICT DO UPDATE SET request_count = mcp_rate_limits.request_count + 1` in a single CTE — fully atomic, matches ADR-006 §3. |
| I1 — UPSERT error silently swallowed | Important | **Resolved.** try/except wraps RPC call. `except RateLimitError: raise` preserves the 429 path. Generic `except Exception` logs warning with `exc_info=True` and continues (fail-open). Docstring cites conventions.md rationale. |
| I2 — `mcp_tokens` name/label schema gap | Informational | **Still tracked.** KIN-325 implementation files exist; resolution will land there. Not blocking KIN-321. |

---

## Files Reviewed

- `packages/api/app/api/routes/mcp.py` (lines 139–177: `_check_rate_limit`)
- `packages/api/tests/test_mcp.py` (`_make_db_mock` RPC mock, `TestMCPRateLimit`)
- `packages/api/supabase/migrations/20260324000000_mcp_rate_limit_rpc.sql` (new)

---

## Migration Review

`mcp_check_and_increment_rate_limit` RPC:
- `SECURITY DEFINER` with `SET search_path = public` — correct for service-role invocation.
- CTE performs atomic upsert: `INSERT ... ON CONFLICT DO UPDATE SET request_count = mcp_rate_limits.request_count + 1 RETURNING request_count, daily_cap`.
- Boundary check: `allowed = (request_count <= daily_cap)` — user gets exactly `daily_cap` requests; request `daily_cap + 1` returns `allowed = false`. Correct.
- Default `daily_cap = 1000` in INSERT VALUES matches spec default. Acceptable for MVP (no admin-configurable cap mechanism exists yet).

---

## Notes (non-blocking)

- **No test for RPC failure path.** The `except Exception` branch (fail-open + log warning) has no dedicated test. Risk is low — three lines, fail-open behavior. Consider adding in a future test pass.

---

## Summary

All R2 findings resolved. Atomic rate limit via RPC eliminates the check-then-act race. Fail-open error handling with logging follows conventions. No new issues introduced. LGTM.
