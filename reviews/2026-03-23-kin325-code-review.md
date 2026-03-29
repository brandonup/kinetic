# Code Review: KIN-325 — MCP Token Management UI

**Date:** 2026-03-23
**Reviewer:** Gilfoyle
**Ticket:** KIN-325 — [Dinesh] MCP token management UI
**Verdict:** CHANGES_REQUESTED

---

## Summary

1 Critical, 2 Important, 1 Minor. The critical issue is a timestamp bug that stores the literal string `"now()"` in `revoked_at` instead of a real timestamp. Tests don't catch it because Supabase calls are mocked. The two Important issues are a wrong exception type on create failure and a spec deviation on the masked token display. All three need fixing before merge.

---

## Findings

### [CRITICAL] `"now()"` stored as a literal string, not a timestamp

**File:** `packages/api/app/api/routes/mcp_tokens.py`, line 180

**Problem:** The revoke endpoint does:
```python
.update({"revoked_at": "now()"})
```
The Supabase Python client does **not** evaluate `"now()"` as a SQL function. It inserts the literal string `"now()"` into the `revoked_at` column. Every other timestamp write in this codebase uses `datetime.now(timezone.utc).isoformat()` — see `admin_users.py:139`, `active_memory.py:524`, `active_memory.py:563`. This is a codebase-established pattern that `mcp_tokens.py` breaks.

**Impact:**
- The `revoked_at` column stores `"now()"` (a string), not a real timestamptz.
- The API returns `"now()"` to the client as the revocation timestamp — an invalid ISO timestamp that will break any consumer that parses it.
- `revoked_at IS NULL` filters work accidentally correctly (a non-null string satisfies the IS NOT NULL check), so access control is not broken. But the API contract is.
- The test mocks the Supabase response directly, so it never exercises the actual value written to the DB.

**Fix:**
```python
from datetime import datetime, timezone
# ...
.update({"revoked_at": datetime.now(timezone.utc).isoformat()})
```

**Category:** `other` (timestamp serialization)

---

### [IMPORTANT] Wrong exception type on insert failure in `create_token`

**File:** `packages/api/app/api/routes/mcp_tokens.py`, line 106

**Problem:**
```python
if not result.data:
    raise ValidationError("Failed to create MCP token")
```
`ValidationError` maps to HTTP 400 and signals a client input error. An insert failure (no data returned from Supabase) is an infrastructure/server-side failure — it means the DB rejected the write or an unexpected state occurred. The correct exception is a generic `AppException` with code `"INTERNAL_ERROR"` and status 500.

A 400 on an internal server failure is misleading to the client and confusing for debugging.

**Fix:**
```python
from app.core.errors import AppException
# ...
if not result.data:
    raise AppException("INTERNAL_ERROR", "Failed to create MCP token")
```
This maps to the generic 500 handler in `add_exception_handlers`.

**Category:** `api-contract`

---

### [IMPORTANT] Spec deviation: token list does not show masked token value

**File:** `packages/web/app/(app)/profile/page.tsx`, MCP Tokens section (lines 683–707)

**Problem:** The ticket description specifies: *"After modal dismissal: token appears in the list as `mcp_••••••••`."* and *"Tokens shown masked (`mcp_••••••••`) — value never shown again after generation modal."*

The implementation shows only the token label/name in the list. There is no column or field displaying the masked value `mcp_••••••••`. The backend `GET /api/v1/mcp/tokens` response does not include any hint or masked prefix — the `McpToken` type has no such field.

The Done When criteria says "Token never shown in list after modal dismissal" — that is satisfied. But "shown as `mcp_••••••••`" (masked, not absent) is a distinct UX from "not shown at all."

This is a spec ambiguity that needs a decision before approving. Possible resolutions:
1. Add a `token_prefix` field to the `GET` response (first N chars of the raw token stored at create time) and display it masked — matches the spec literally.
2. Keep the current design (name only, no masked value) and update the ticket AC to reflect the actual behavior.

**Why this is a block:** Per review policy, spec ambiguities touching implemented behavior are a block, not a note.

**Category:** `spec-gap`

---

### [MINOR] `tokenCopied` state not cleared when a new token modal opens after rapid second generate

**File:** `packages/web/app/(app)/profile/page.tsx`, lines 91 and 286–292

**Problem:** `tokenCopied` is only reset in the `onOpenChange` handler when the modal closes (line 725). If a user generates a token, copies it (`tokenCopied = true`), dismisses the modal, then generates another token immediately, the new modal opens showing "Copied!" on the copy button.

**Fix:** Add `setTokenCopied(false)` inside `generateToken()` before `setNewToken(data)`.

**Category:** `other`

---

## What's Working Well

- SHA-256 hashing via `_hash_token` is correct and consistent with ADR-006 §1.
- `get_supabase_client()` module-level helper is the right pattern for test patching.
- All three Supabase calls in async routes use `run_in_executor`. No direct sync calls in async context.
- Ownership scoping: both the fetch and update in `revoke_token` filter by `user_id`. The fetch-then-update pattern correctly handles the already-revoked case before the write.
- `ConflictError` addition to `errors.py` is clean — added to both the class hierarchy and the status code dispatch in `add_exception_handlers`.
- `dialog.tsx` is a standard shadcn/Radix Dialog wrapper. No issues.
- Frontend types in `models.ts` are correctly minimal — `McpToken` excludes `token_hash` and the raw `token` field.
- Backend test coverage is solid: 19 tests covering create, list, revoke, auth, uniqueness, hash correctness.
- Frontend test suite covers all major flows including revoke dialog, modal, copy, and empty state.
- The one-time token modal UX is correct: raw token stored in `newToken` state, cleared on modal dismiss.
