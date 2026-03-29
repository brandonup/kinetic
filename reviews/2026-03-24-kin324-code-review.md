# Code Review: KIN-324 — MCP Access Control (R1)

**Reviewer:** Gilfoyle
**Date:** 2026-03-24
**Ticket:** KIN-324
**Author:** Big Head
**Files:** `packages/api/app/api/routes/mcp.py`, `packages/api/tests/test_mcp.py`
**Spec:** `docs/specs/mcp-spec.md` §6
**ADR:** `docs/adr-006-mcp-server.md`

---

## Verdict: Changes Requested

**1 Critical, 1 Important, 1 Note.**

---

## Findings

### C1 — [Critical] [acl-leak] 403 for unauthorized entities enables entity enumeration

**File:** `packages/api/app/api/routes/mcp.py` lines 263-266, 303, 326-329
**Spec ref:** mcp-spec.md §6.1, §6.2, §6.3; ADR-006 §4

**Problem:** The implementation returns 403 for entities the user does not own, and 404 for entities that do not exist. This split allows any holder of a valid MCP token to enumerate entity UUIDs: probe a UUID, get 404 = doesn't exist, get 403 = exists but forbidden. This leaks which project, agent, and company UUIDs are valid.

Jian's pre-implementation comment on KIN-324 flagged this exact conflict. The spec §6 says 403. ADR-006 §4 says "Reject 403 if unauthorized, 404 if not found." But the security rationale in ADR-006 — "rate limit before scope prevents entity enumeration at scale" — only mitigates volume, not the information leak per request. Rate limiting slows enumeration; it does not prevent it.

The standard pattern for preventing entity enumeration: return 404 for both "not found" and "not authorized." The caller cannot distinguish between a nonexistent entity and one they lack access to.

**Fix:** Replace all three `AuthorizationError` raises (project line 264, company line 303, agent line 327) with `NotFoundError`. Use the same message for both missing and unauthorized: `"Project not found"`, `"Company not found"`, `"Agent not found"`. Update tests to expect 404 for not-owned entities. **This requires a spec update** — mcp-spec.md §6 must change 403 to 404 for ownership failures, or a `[Decision]` ticket for Brandon if the 403 behavior is intentional.

**Severity:** Critical — security information leak. Blocks approval.

---

### I1 — [Important] [spec-gap] Spec §6.3 references `company_members` table that does not exist in schema

**File:** `docs/specs/mcp-spec.md` §6.3
**Schema ref:** `docs/db-schema-spec.md` §3

**Problem:** Spec §6.3 says: "Verify user is a member of the company (row in `company_members` or `companies.user_id = authenticated_user_id`)." There is no `company_members` table in `db-schema-spec.md`. The implementation correctly checks `companies.user_id` only, which is the sole ownership column available.

The implementation is correct given the current schema. But the spec references a nonexistent table, which will confuse future implementers (e.g., when `shared` visibility ships and multi-user company access becomes real).

**Fix:** Update mcp-spec.md §6.3 to remove the `company_members` reference. Replace with: "Verify `companies.user_id = authenticated_user_id`." Add a comment: "Multi-user company membership (company_members table) deferred to post-MVP shared visibility."

**Severity:** Important — spec-implementation mismatch. Does not block the current code (implementation is correct), but the spec must be cleaned up before this ticket closes.

---

### N1 — [Note] Test coverage is solid for the happy and unhappy ACL paths

New tests cover: project 403, company 403, private agent 403, public agent 200, owner private agent 200. Combined with existing 404 tests for missing entities, all §6 branches are exercised. Mock builder correctly updated to single `.eq()` chain (fetch by id only, ownership in Python). 47 pass, 9 skipped (all skipped tests are for KIN-322/KIN-323 scope). Good work.

---

## Summary

The ACL logic is structurally correct — ownership checks are clean, entity fetch is separated from authorization, and cross-scope validation works. The blocking issue is the 403 vs 404 decision: returning 403 leaks entity existence. This is a security concern, not a code quality issue. The spec says 403, but the security-first choice is 404. Brandon or Jared needs to resolve the spec conflict before this merges.
