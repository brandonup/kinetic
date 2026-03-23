# Code Review R2 — KIN-308: Active Memory — token cap enforcement + entry structure

**Reviewer:** Gilfoyle
**Date:** 2026-03-23
**Verdict:** APPROVED
**Round:** 2 (re-review after R1 changes requested)

---

All four R1 findings resolved. Zero new findings.

## R1 Resolution Verification

| Finding | Status |
|---|---|
| C1 — `review_proposals` missing `token_usage` | Resolved. `_last_scope_col/_last_scope_id/_last_cap` tracking added; final tokens computed after all decisions and returned in response. |
| C2 — `ProposalDecision.action` unconstrained | Resolved. Now `Literal["accept", "reject"]` — invalid action values rejected at Pydantic boundary. |
| I1 — `test_create_empty_content_422` wrong status code | Resolved. Test comment documents 422 vs spec's 400 is FastAPI/Pydantic convention, with cross-ref to `test_companies.py`. |
| I2 — `MemoryCapExceededError` in `update_entry` misleading `current_tokens` | Resolved. Now passes `current_tokens=current_total` (pre-delta total), not `current_total - old_tokens`. |
| Bonus — closure capture bug in `review_proposals` loop | Resolved. `lambda _pid=proposal_id:` and `lambda _row=row:` default-arg pattern applied consistently at all three lambdas. |
