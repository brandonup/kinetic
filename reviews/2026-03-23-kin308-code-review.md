# Code Review — KIN-308: Active Memory — token cap enforcement + entry structure

**Reviewer:** Gilfoyle
**Date:** 2026-03-23
**Verdict:** CHANGES_REQUESTED
**Files reviewed:**
- `projects/kinetic/packages/api/app/api/routes/active_memory.py`
- `projects/kinetic/packages/api/app/core/errors.py`
- `projects/kinetic/packages/api/app/main.py`
- `projects/kinetic/packages/api/tests/test_active_memory.py`

**Spec:** `docs/specs/active-memory-spec.md`
**Schema:** `docs/db-schema-spec.md` §16, §17

---

## Summary

2 Critical, 2 Important. The token cap logic, ownership verification, and general structure are correct. Two API contract violations and a test that enforces framework defaults instead of spec requirements block approval.

---

## Findings

### Critical

---

#### C1 — `review_proposals` response missing `token_usage`

**File:** `app/api/routes/active_memory.py`, line 560
**Category:** `api-contract`

**Problem:**
The spec (§4.1 `POST /api/v1/active-memory/proposals/review`) defines the response shape as:
```json
{
  "results": [...],
  "token_usage": { "current_tokens": N, "cap_tokens": N }
}
```

The implementation returns only `{"results": results}`. The comment at line 558 acknowledges this is deferred ("use first decision's scope as reference") but then simply omits the field. `token_usage` is not optional in the spec — it's in the defined response contract and is required for the UI to update the token bar after a review session.

**Fix:**
After processing all decisions, compute final token usage from the scope of the last accepted proposal (or any processed proposal's scope). Since all proposals in a review batch belong to a single scope in practice (the user is reviewing one project or agent's proposals at a time), use the first non-skipped-not-found proposal's scope. Return:
```python
return {
    "results": results,
    "token_usage": {"current_tokens": final_tokens, "cap_tokens": cap},
}
```
If no proposals were processed (empty `decisions` list), return `{"results": [], "token_usage": {"current_tokens": 0, "cap_tokens": 0}}` or omit — but the non-empty case must include it.

---

#### C2 — `ProposalDecision.action` is unconstrained — invalid action silently drops result

**File:** `app/api/routes/active_memory.py`, lines 94–97 and 509–556
**Category:** `error-swallow`

**Problem:**
`ProposalDecision.action` is typed as `str` with no validator, no `Literal` constraint. If a caller sends `action: "approve"` or `action: "ACCEPT"` or any variant, the code falls through both `if action == "reject"` and `elif action == "accept"` branches. The proposal is silently ignored — no result entry is appended for that `proposal_id`. The caller receives a `results` array missing that item with no indication of what happened.

This violates the "never silently swallow write-path failures" convention in both `CLAUDE.md` and the route module's own docstring.

**Fix:**
Add a `Literal` type constraint:
```python
from typing import Literal
class ProposalDecision(BaseModel):
    proposal_id: str
    action: Literal["accept", "reject"]
```

This converts invalid action values to a 422 at the Pydantic validation boundary before any loop iteration, which is the correct behavior. Alternatively, add an `else` branch that appends `{"proposal_id": proposal_id, "action": "invalid_action"}` — but rejecting at the boundary is cleaner.

---

### Important

---

#### I1 — `test_create_empty_content_422` asserts wrong status code

**File:** `tests/test_active_memory.py`, lines 235–239
**Category:** `spec-gap`

**Problem:**
The spec (§4.1 POST Errors) explicitly states: "400 — empty content". The test asserts `resp.status_code == 422`.

The 422 comes from FastAPI's Pydantic validation layer (`RequestValidationError`), which the existing `pydantic_validation_handler` in `errors.py` maps to 400 for `PydanticValidationError` (model-level validation). However, FastAPI handles `RequestValidationError` (request body parsing) differently from model-level `PydanticValidationError` — the body validator runs before the custom handler, and FastAPI's built-in handler returns 422.

The test is testing that FastAPI's default behavior fires, not that the spec's 400 contract is met. One of two fixes is needed:
1. **Spec-compliant fix:** Add a `RequestValidationError` handler in `add_exception_handlers` that returns 400, aligning with the spec. Update the test to assert 400.
2. **Spec amendment (requires Brandon/Jared):** Accept 422 for malformed body and update the spec. This is the pragmatic path — 422 is arguably more correct semantically for Pydantic body validation.

This needs a decision. Flagging as Important because the test is asserting behavior that happens to work today but documents the wrong contract — anyone reading the test believes the spec says 422, when it says 400.

---

#### I2 — `MemoryCapExceededError` in `update_entry` reports misleading `current_tokens`

**File:** `app/api/routes/active_memory.py`, line 362
**Category:** `api-contract`

**Problem:**
```python
raise MemoryCapExceededError(current_tokens=current_total - old_tokens, cap_tokens=cap)
```

`current_total - old_tokens` is the total *after* removing the old entry — it's the headroom before the new content. The error message renders as: `"Memory is full (X/cap tokens)"` where X is artificially low. If the scope has 990 tokens, the old entry is 25 tokens, and the new entry is 250 tokens, the error reports "Memory is full (965/1000 tokens)" — which looks like there's still 35 tokens free, making the message confusing.

The spec says this error should surface `current_tokens` and `cap_tokens` so the user knows their current usage. The correct value is `current_total` (before applying the delta).

**Fix:**
```python
raise MemoryCapExceededError(current_tokens=current_total, cap_tokens=cap)
```

---

## What's Correct

- Token counting (`ceil(len(content) / 4)`) matches spec §1.2 exactly.
- Cap constants (1000 project, 500 agent) match `db-schema-spec.md` § Configuration Parameters.
- `run_in_executor` pattern applied consistently — no sync Supabase calls in async context.
- `_resolve_scope` correctly enforces the polymorphic constraint (exactly one scope).
- Ownership verification before any data access — correct pattern.
- `DELETE` is hard-delete (not soft-delete) — matches spec §4.1.
- `PATCH` delta cap check correctly accounts for old entry tokens.
- `list_proposals` filters by `status = 'pending'` — correct.
- `admin_router` correctly bypasses user ownership check while still requiring `require_admin`.
- `main.py` router registration is clean — both `active_memory_router` and `active_memory_admin_router` registered.
- `MemoryCapExceededError` maps to HTTP 422 in the exception handler — matches spec.
- Test coverage is solid for the happy paths and boundary conditions (at-cap, one-over-cap).

---

## Required Changes Before Re-review

1. **C1:** Add `token_usage` to `review_proposals` response.
2. **C2:** Constrain `ProposalDecision.action` to `Literal["accept", "reject"]`.
3. **I1:** Align `test_create_empty_content_422` with the actual spec contract — either fix the handler to return 400 or update the test comment to document the 422 is intentional and update the spec. A decision is needed.
4. **I2:** Fix `current_tokens` argument in `update_entry` MemoryCapExceededError raise.
