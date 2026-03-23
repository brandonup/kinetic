# KIN-311 Code Review — Linked Upload Agent Profile
**Reviewer:** Gilfoyle
**Date:** 2026-03-23
**Status:** Approved with Minor Issues

---

## Strengths

- **Clean surface-specific dispatch** (`linked_upload.py:124–130`). The `if prompt_id == ...` chain in `extract()` is readable and adding a fourth surface later requires only adding one branch. No magic, no over-engineering.
- **Correct text limit for agents** (`linked_upload.py:216`). `_extract_agent` uses `_TEXT_LIMIT_AGENT = 12_000` rather than the shared `_TEXT_LIMIT_SHORT = 8_000`, reflecting that a corpus document requires broader context to produce a useful persona prompt. This is a deliberate, correct divergence.
- **Instructions prompt is well-structured** (`linked_upload.py:240–255`). The five-axis decomposition (thinking style, communication patterns, core principles, expertise, distinctive perspective) + the "begin with 'You are [name]...'" constraint gives the LLM enough scaffold to produce a usable system prompt rather than a summary. The `max_tokens=800` ceiling is appropriately higher than the other surfaces.
- **No instructions length cap applied post-LLM** (`linked_upload.py:256`). Unlike `_extract_profile` and `_extract_company` which hard-cap at 1000 characters, agent instructions are returned as-is (if non-empty). This is correct: the instructions field has no character constraint in the spec, and truncating mid-prompt would produce a broken system prompt.
- **`PATCH_EXTRACT_TEXT` applied uniformly across all four agent tests** (`test_linked_upload.py:334,364,399,415,435`). Every test that calls the endpoint patches text extraction, which eliminates the real PDF parser from unit tests. Consistent and correct.
- **`test_agent_extraction_uses_different_prompt_than_profile`** (`test_linked_upload.py:384–428`). Verifying prompt ID divergence structurally is a better test than "trust the implementation." The double-context manager pattern is verbose but unambiguous.
- **Route docstring is accurate** (`linked_upload.py:447–454`). Accepted formats, size limit, and no-storage guarantee all match the implementation. No misleading comments.

---

## Issues

### Critical

None.

### Important

**1. `test_agent_extraction_uses_different_prompt_than_profile` has a conditional assertion that can silently pass without testing anything**
- File: `test_linked_upload.py:425–428`
- Issue: The final assertion `if user_prompt_id is not None and agent_prompt_id is not None: assert ...` means if either prompt ID capture fails (e.g. the mock's `call_args` returns `None` because `side_effect` consumed it differently), the test body is skipped entirely and the test reports green. The `_capture_extract` closure is wired to the `side_effect` but it doesn't write to `user_prompt_id` — that variable stays `None` unless `call_args[1].get("prompt_id")` succeeds. In practice the test works right now, but the conditional guard means a regression could go undetected.
- Fix: Assert both IDs are not None before comparing them, or restructure to use `assert_called_once_with` / `call_args` outside the conditional. At minimum: `assert user_prompt_id is not None, "Profile prompt_id was not captured"` and `assert agent_prompt_id is not None, "Agent prompt_id was not captured"` before the inequality check.

**2. `agent_id` path parameter is accepted but never validated or used**
- File: `linked_upload.py:436–494`
- Issue: The route accepts `agent_id: str` but never touches it — no ownership check, no existence check, no logging. For the profile and company surfaces this is consistent (profile has no path param; company has the same gap), but the agent route is the most sensitive because the corpus document could be large and the extraction is expensive. A user could POST to any `agent_id` UUID, including agents they don't own, and extraction proceeds. Currently this only leaks compute, not data (the route returns extracted fields, not agent data). However, when the Agent Profile page wires up the save call in Sprint 4, a missing ownership check on the upload surface sets a bad precedent — the frontend will assume the backend validated ownership before returning draft data.
- Fix: Either add a Supabase lookup to confirm `agent_id` belongs to `current_user.user_id` and return 404 if not, or document explicitly (in code comment and MEMORY.md) that ownership is enforced at the PATCH endpoint only, not here. The decision should be intentional, not accidental.

### Minor

**1. Module docstring still says "KIN-314" at the top of the test file**
- File: `test_linked_upload.py:2`
- Issue: The module header reads `Tests for Linked Upload extraction endpoints — KIN-314`. KIN-314 doesn't exist in this context. Given the implementation tickets are KIN-310 and KIN-311, this is probably a stale placeholder from a previous scaffolding pass.
- Fix: Update to `KIN-310 / KIN-311`.

**2. Stub status comment in test file header is outdated**
- File: `test_linked_upload.py:14`
- Issue: Line 14 reads `Stub status: skipped — awaiting KIN-310 + KIN-311 implementation.` Both tickets are now implemented and the skips have been removed. This comment is actively misleading — a future reader will wonder which tests are skipped.
- Fix: Remove the line or replace with `All stubs active as of KIN-311.`

**3. `_make_extraction_result` helper defaults to `bio` key, not usable for agent tests**
- File: `test_linked_upload.py:63–64`
- Issue: The helper returns `{"name": name, "bio": bio}`. The agent tests that need `{"name": ..., "instructions": ...}` construct their return value inline (e.g. `test_linked_upload.py:339–341`). This is fine, but it means the helper is only useful for profile tests. No risk, but it's a readability wart — a new contributor writing agent tests might reach for `_make_extraction_result` and get the wrong dict shape silently (since the mock accepts whatever the test puts in `.return_value`).
- Fix: Either add an `instructions` variant helper, or rename `_make_extraction_result` to `_make_profile_result` to signal its scope.

**4. Token range check uses a loose lower bound**
- File: `test_linked_upload.py:380–382`
- Issue: `assert 100 <= token_estimate <= 1000` accepts as few as 400 characters (100 * 4). The spec says 300–500 tokens for the instructions field. The test range is so wide (100–1000) that it would pass even if the LLM returned a single sentence. The test comment correctly notes it's a "rough check," but at 100 token lower bound it's effectively not checking the lower bound at all — the mock value `instructions = "You are Nate Jones. " + ("You reason from first principles. " * 40)` happens to produce ~330 chars / ~82 token-estimate, which actually fails the 100-token lower bound. This means the test is passing because the mock was set to a specific length, not because the bound is meaningful.
- Fix: Tighten the bounds to `50 <= token_estimate <= 700` (realistic given the mocked value), or acknowledge this is a prompt contract test and remove the assertion in favor of a comment that the real eval lives in `evals/`.

---

## Assessment

The KIN-311 implementation is correct and production-safe for the Sprint 4 frontend integration. The `_extract_agent` method produces a well-structured instructions prompt with appropriate token budget, the file type set and size limit match the spec, the BYOK gate is enforced server-side, and the in-memory constraint holds. The four agent test cases cover the right scenarios.

The one issue worth resolving before Sprint 4 frontend work begins is the `agent_id` ownership gap (Important #2): if the decision is "validate at PATCH only," that needs to be written down before the save endpoint is built, not discovered during that review.

The conditional assertion in `test_agent_extraction_uses_different_prompt_than_profile` (Important #1) should be hardened — it's currently testing the right thing but structured so it could silently stop testing it. The minor issues are cleanup items with no runtime impact.

**Ready to merge: Yes, with Important #2 documented**

The code is shippable. Important #1 and the minors can be addressed in the current branch or as a follow-up KIN ticket. Important #2 requires either a one-line fix or an explicit decision captured in MEMORY.md before Sprint 4 wires up the save endpoint.
