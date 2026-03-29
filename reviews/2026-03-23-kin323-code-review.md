# KIN-323 Code Review — MCP Rate Limiting (R1)

**Reviewer:** Gilfoyle
**Date:** 2026-03-23
**Verdict:** APPROVED
**Findings:** 0 Critical, 1 Important, 1 Informational

---

## Summary

Rate limit headers added to 429 responses. UTC midnight computation is correct. Per-user cap flows through `mcp_rate_limits.daily_cap` (no schema change needed). 6 previously-skipped tests now pass. Clean implementation.

---

## Findings

### I1 — Spec says X-RateLimit-* headers on ALL responses, not just 429

**File:** `app/core/errors.py` lines 162-169, `app/api/routes/mcp.py`
**Severity:** Important
**Category:** spec-gap

Spec §7 says:

> **Response headers (on all MCP responses):**
> X-RateLimit-Limit: 1000
> X-RateLimit-Remaining: 742
> X-RateLimit-Reset: 1711324800

The implementation only adds these headers on 429 (inside the `RateLimitError` handler in `errors.py`). Success responses (200) do not include `X-RateLimit-Remaining` or the other rate limit headers. Clients that want to proactively back off before hitting the wall have no signal.

**Assessment:** This is a spec requirement that KIN-323 did not fully implement, but the 429-path headers (the primary deliverable) are correct. I'm not blocking on this because: (a) the 429 path is the critical path and it works, (b) adding headers to 200 responses requires the RPC to return `request_count` and `daily_cap` on the success path too, which is a different code path (route-level middleware or response hook, not error handler). This should be a follow-up ticket, not a rework of KIN-323.

**Action:** Create a follow-up ticket for rate limit headers on 200 responses.

---

### I2 — 429 response body shape differs from spec

**File:** `app/core/errors.py` (inherits `AppException` shape)
**Severity:** Informational
**Category:** spec-gap

Spec §7 shows 429 body as `{"error": "rate_limit_exceeded", "limit": 1000, "reset_at": "..."}`. Implementation returns `{"error": {"code": "RATE_LIMIT_EXCEEDED", "message": "...", "details": {...}}}` — the standard `AppException` shape from `conventions.md`.

**Assessment:** The implementation is correct per project conventions (all errors use `{ error: { code, message, details? } }`). The spec's 429 body example is inconsistent with the project error shape. Not an implementation bug — the spec should be updated to reflect the standard error shape. No action needed on Big Head's code.

---

## Architecture

- UTC midnight computation (`datetime.now(timezone.utc)` + `replace` + `timedelta`) is correct and avoids timezone pitfalls.
- Header injection in the centralized error handler (`errors.py`) is the right place — keeps the route clean.
- `RateLimitError.details` as the transport mechanism for header values is pragmatic and avoids a new abstraction.
- Fail-open on RPC error (line 187-191 in `mcp.py`) is correctly preserved from KIN-321.

## Tests

- 4 new header tests (`TestMCPRateLimitHeaders`) cover `Retry-After`, `X-RateLimit-Remaining`, `X-RateLimit-Limit`, `X-RateLimit-Reset`.
- 2 new advanced tests (`TestMCPRateLimitAdvanced`) cover per-user cap override and midnight reset.
- All 6 previously-skipped tests now pass. 51 total passed, 5 remaining skips are KIN-322 (RAG).
- No test coverage gaps for the 429 path.
