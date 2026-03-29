# KIN-324 Code Review — R2

**Reviewer:** Gilfoyle
**Date:** 2026-03-23
**Verdict:** APPROVED

## R1 Findings Resolution

### C1 (acl-leak) — RESOLVED
Projects: `.eq("user_id", user_id)` filter on project lookup (line 259). Companies: `.eq("user_id", user_id)` when explicit `company_id` provided (line 306). Agents: visibility/owner check in Python, 404 on failure (lines 330-331). No 403 anywhere. Anti-enumeration pattern correct.

### I1 (spec-gap) — RESOLVED
Spec section 6 updated: anti-enumeration rationale documented, 403 removed from error table, `company_members` reference removed. Error table (section 8) has only 404 `entity_not_found` covering both not-found and not-authorized cases.

## R2 Audit

- **ACL test coverage:** `TestMCPEntityACL` covers all five critical permutations (project not owned, private agent not owned, public agent accessible, owner private agent accessible, company not owned). All return correct status codes.
- **Error handling:** No silent swallows. Rate limit fails open with `logger.warning` (documented, acceptable). Auth errors raise immediately.
- **Spec alignment:** Code matches spec sections 6.1-6.4 exactly.

## Result

0 Critical, 0 Important. LGTM.
