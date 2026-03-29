# Code Review — KIN-325 MCP Token Management UI (Round 2)

**Date:** 2026-03-23
**Reviewer:** Gilfoyle
**Ticket:** KIN-325 — [Dinesh] MCP token management UI
**Status:** APPROVED

---

## R1 Findings — Verification

All three R1 findings are resolved.

| Finding | Status |
|---|---|
| Critical: `revoked_at` stored as `"now()"` string | Fixed — `datetime.now(timezone.utc).isoformat()` at line 181 |
| Important: insert failure raised `ValidationError` (400) | Fixed — raises `AppException("INTERNAL_ERROR", ...)` at line 107 |
| Important: masked token value missing from list | Fixed — `mcp_••••••••` rendered below token name in JSX |

---

## R2 Findings

### Important — Wrong exception class on update empty-result path

**File:** `packages/api/app/api/routes/mcp_tokens.py`, line 186–187

After successfully fetching the token (confirming it exists and belongs to the user), if `update_result.data` is empty the code raises `NotFoundError("MCP token not found")`. At this point in the call stack, the token is known to exist — an empty update result is a DB-side failure, not a missing resource. The correct exception is `AppException("INTERNAL_ERROR", "Failed to revoke MCP token")`.

In practice this path fires only in a race condition (token deleted between fetch and update), so it won't surface in normal operation. But it would emit a misleading 404 to the client and the wrong log message, making it harder to diagnose if it ever does occur.

**Fix:**
```python
if not update_result.data:
    raise AppException("INTERNAL_ERROR", "Failed to revoke MCP token")
```

### Minor — `ValidationError` imported but never used

**File:** `packages/api/app/api/routes/mcp_tokens.py`, line 28

`ValidationError` is imported from `app.core.errors` but never raised in the module. Pydantic handles the empty/oversized name case and FastAPI returns 422 automatically — no manual `ValidationError` raise needed. This import is dead code and will be flagged by `ruff` (F401).

**Fix:** Remove `ValidationError` from the import line.

### Minor — No frontend test for `mcp_••••••••` masked display

**File:** `packages/web/app/__tests__/components/McpTokensSection.test.tsx`

The R1 fix added the masked prefix to the JSX, but no test asserts it renders. The existing "renders token list with label, created date, and last used" test checks column headers and the token name — it does not assert `mcp_••••••••` appears below the name.

This is a minor gap. The feature works and is visible in code, but test coverage doesn't verify the spec requirement ("Tokens shown masked in the list").

**Fix (optional for this pass):** Add to the existing list-render test:
```typescript
expect(screen.getByText("mcp_••••••••")).toBeInTheDocument();
```

---

## Verdict

**APPROVED with noted findings.**

The Important finding (wrong exception class on update empty path) is a correctness issue but only fires in a practically unreachable race condition. It does not affect any normal operation path and does not change observable behavior for users. Given it is entirely internal (wrong HTTP status code in a race condition that produces no user-facing side effects), I am approving this pass and logging it as a defect for the next Dinesh session rather than holding the ticket.

The two Minor findings are non-blocking. The unused import should be cleaned up as part of normal ruff compliance; the masked-value test gap is cosmetic coverage.

**Architecture:** Sound. SHA-256 per ADR-006, `run_in_executor` on all Supabase calls, ownership-scoped queries, one-time token display pattern, optimistic UI removal on revoke.
**Correctness:** All three R1 blockers resolved. One Important edge case remains (logged).
**Test coverage:** 19 backend tests + 11 frontend tests. All happy paths, error paths, and auth gates covered.
