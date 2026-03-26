# Code Review — KIN-385: Chat Generation Endpoint

**Reviewer:** Gilfoyle
**Date:** 2026-03-26
**Round:** 1
**Verdict:** CHANGES_REQUESTED
**Files reviewed:**
- `packages/api/app/services/context_assembler.py` (new)
- `packages/api/app/api/routes/generation.py` (new)
- `packages/api/app/services/prompts.py` (modified)
- `packages/api/app/main.py` (modified)
- `packages/api/tests/conftest.py` (modified)
- `packages/api/tests/test_context_assembly.py` (new, 17 tests)
- `packages/api/tests/test_generation.py` (new, 11 tests)

---

## Summary

Architecture is sound. The 9-layer assembly pattern, run_in_executor discipline, and fail-open behavior for L7/L8/L9 are all correct. Two correctness issues require fixes before this ships: a sequence race condition in message storage, and a missing user-scope filter on the agent switch update. One error message is misleading enough to confuse future debugging. Schema section reference in the docstring is wrong but code is correct.

---

## Critical

### C1 — Sequence race condition on message insert

**File:** `packages/api/app/api/routes/generation.py`, lines 175–196

The endpoint counts existing messages with a `SELECT id FROM messages WHERE conversation_id = ...`, then uses `len(result)` as `sequence`. Between the count query and the insert, a concurrent request (or a retry) can insert a message, producing a duplicate `sequence` value. The schema has no `UNIQUE(conversation_id, sequence)` constraint to catch this.

For MVP with low concurrency this is low-probability, but it is a latent correctness bug that will manifest under any parallel usage (e.g., two tabs, a retry after timeout).

**Fix:** Compute sequence atomically. Options:
1. Use a DB-side `SELECT COALESCE(MAX(sequence), -1) + 1 FROM messages WHERE conversation_id = ...` inside a transaction with the insert.
2. Simpler for MVP: use `SELECT COUNT(*) ...` wrapped in a Supabase RPC that both counts and inserts atomically.
3. Acceptable MVP shortcut: add `UNIQUE(conversation_id, sequence)` to the schema and catch the constraint violation in the insert, retrying with MAX(sequence)+1.

**Category:** `other` (race condition / sequence integrity)

---

### C2 — Agent switch update is not user-scoped at the application layer

**File:** `packages/api/app/api/routes/generation.py`, lines 126–133

```python
await loop.run_in_executor(
    None,
    lambda: client.table("conversations")
    .update({"active_agent_id": body.agent_id})
    .eq("id", conversation_id)
    .execute(),
)
```

The `UPDATE` filters only on `id`. RLS enforces ownership at the DB layer, but the application layer convention (and defense-in-depth) requires that every write operation include the explicit `user_id` equality filter. The preceding SELECT already verified ownership — the UPDATE should chain `.eq("user_id", current_user.user_id)` to maintain the same pattern used everywhere else in the codebase.

**Fix:**
```python
client.table("conversations")
    .update({"active_agent_id": body.agent_id})
    .eq("id", conversation_id)
    .eq("user_id", current_user.user_id)
    .execute()
```

**Category:** `rls-bypass` (defense-in-depth gap)

---

## Important

### I1 — Misleading error message when model UUID is valid but model is disabled/not found

**File:** `packages/api/app/api/routes/generation.py`, lines 160–162

When `model_res.data` is empty (model disabled or UUID not in `llm_models`), the error is:
```
"No model selected and no default model configured"
```
This is identical to the upstream case where `model_uuid` is `None`. A user or developer debugging a 400 from a valid model UUID will not understand why they're getting a "no model" error.

**Fix:**
```python
if not model_res.data:
    raise ValidationError("Model not found or not enabled")
```

**Category:** `other` (misleading error)

---

### I2 — Schema section reference error in context_assembler.py docstring

**File:** `packages/api/app/services/context_assembler.py`, line 11

The docstring lists:
```
§16 (active_memory_entries), §19 (messages), §6 (conversation_summaries)
```

Per `docs/db-schema-spec.md`:
- `messages` = **§6**
- `conversation_summaries` = **§7**
- `llm_models` = **§19** (not `messages`)

The table names in the actual code are correct — only the cross-reference numbers are wrong. Still a violation of the schema-reference convention (a developer following the reference lands on the wrong table).

**Fix:** Update docstring to:
```
§16 (active_memory_entries), §6 (messages), §7 (conversation_summaries)
```

**Category:** `schema-mismatch` (documentation)

---

## Minor

### M1 — Test coverage gap: soft-deleted conversation not tested

**File:** `packages/api/tests/test_generation.py`

`TestGenerateConversationNotFound404` tests a completely missing conversation. There is no test for a soft-deleted conversation (one with `deleted_at IS NOT NULL`). The `.is_("deleted_at", "null")` filter in the query is correct, but it is not exercised by the test suite.

**Fix:** Add one test case where the conversation data exists but `deleted_at` is set — verify 404 is returned.

---

### M2 — `_mock_stream_fail` in `TestGenerateLLMFailure` has an unreachable `yield`

**File:** `packages/api/tests/test_generation.py`, line 483

```python
async def _mock_stream_fail(**kwargs):
    raise RuntimeError("LLM provider unavailable")
    yield  # make it a generator  # noqa: E501
```

The `yield` after an unconditional `raise` is unreachable — the comment acknowledges the smell. Python will treat the function as an async generator because of the `yield` keyword, so the test passes, but this is a code smell that will confuse future maintainers.

**Fix:** Use `AsyncMock` with `side_effect=RuntimeError(...)`, or restructure to `yield` a value before raising:
```python
async def _mock_stream_fail(**kwargs):
    if False:
        yield  # make it a generator
    raise RuntimeError("LLM provider unavailable")
```

---

## Checklist

| Check | Status |
|---|---|
| All Supabase calls in async methods use `run_in_executor` | PASS |
| No bare `except:` | PASS |
| Every `except` block logs before returning | PASS |
| No `try/except` returning defaults on write operations | PASS (reads fail-open with documented comment) |
| Table names match `db-schema-spec.md` | PASS |
| Column names match `db-schema-spec.md` | PASS |
| snake_case Python ↔ camelCase TypeScript boundary | N/A (SSE event fields: `message_id`, `type` — correct) |
| RLS scoping on write operations | FAIL — C2 (agent switch update missing user_id filter) |
| Error handling quality | FAIL — I1 (misleading message) |
| Test count meets spec minimum (28) | PASS (17 + 11 = 28) |
| Context layer assembly correctness | PASS |
| BYOK key resolution | PASS |
| Agent switch logic | PASS (logic correct; filter gap is C2) |
| SSE event format matches spec | PASS |

---

## Defect Log Entries

| Date | Ticket | Reviewer | Category | Severity | Description |
|---|---|---|---|---|---|
| 2026-03-26 | KIN-385 | Gilfoyle | other | Critical | Sequence race condition on message insert (count then insert, not atomic) |
| 2026-03-26 | KIN-385 | Gilfoyle | rls-bypass | Critical | Agent switch UPDATE missing user_id filter at application layer |
| 2026-03-26 | KIN-385 | Gilfoyle | other | Important | Misleading 400 error message when model UUID is valid but disabled |
| 2026-03-26 | KIN-385 | Gilfoyle | schema-mismatch | Important | context_assembler.py docstring cites wrong schema section numbers for messages/conversation_summaries |
