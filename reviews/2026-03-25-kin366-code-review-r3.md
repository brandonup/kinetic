# Code Review — KIN-366: Generate Instructions from KB (Round 3)

**Reviewer:** Gilfoyle
**Date:** 2026-03-25
**Verdict:** APPROVED
**Round:** 3

---

## Summary

C2 is fixed. All three Critical items from R1 are now resolved. No new issues introduced. Approved.

---

## Fix Verification

### C1 — FIXED (confirmed from R2)

Table name `knowledge_base_chunks`, column `text`, corpus join `c["text"]`. Correct.

### C2 — FIXED

**File:** `packages/api/app/api/routes/agents.py`, lines 848–860

The endpoint now queries `knowledge_bases WHERE agent_definition_id = agent_id` (Option A from R2) instead of reading a non-existent `knowledge_base_id` column from `agent_definitions`. The implementation:

```python
kb_result = await loop.run_in_executor(
    None,
    lambda: client
        .table("knowledge_bases")
        .select("id")
        .eq("agent_definition_id", agent_id)
        .execute(),
)
kb_rows = kb_result.data or []
if not kb_rows:
    raise ValidationError("Agent has no knowledge base. Upload documents first.")
kb_id = kb_rows[0]["id"]
```

This correctly uses the polymorphic FK per `db-schema-spec.md` §10. The endpoint no longer reads `agent["knowledge_base_id"]` anywhere.

**Backend tests** (`test_generate_instructions.py`): `_kb_chain()` mocks `knowledge_bases` with the correct chain `select().eq().execute()`. `_full_chains()` includes `"knowledge_bases": _kb_chain()`. The `test_no_kb_returns_400` test correctly passes `rows=[]` to `_kb_chain` to trigger the empty-KB error path. Chain structure matches production code.

### C3 — FIXED (confirmed from R2)

All 4 frontend tests passing. No change in R3.

---

## Remaining Known Item (not blocking)

### I1 — model hardcoded to `gpt-4o-mini`

Unchanged from R1/R2. Accepted as known gap matching linked upload pattern. Non-blocking.

---

## Notes

`_AGENT_FIELDS` (line 39) still includes `knowledge_base_id`. This field is not used by the `generate_instructions` endpoint — the KB is now discovered via the `knowledge_bases` table. The field remains for `get_agent`, `list_agents`, and `update_agent`, which is a pre-existing product spec conflict (noted in R2 as a Jared/Brandon call). This is out of scope for KIN-366 and does not affect correctness of the generate-instructions flow.

---

## Done-When Checklist

| Item | Status |
|---|---|
| C1 fixed — correct table/column names | Done |
| C2 fixed — KB lookup via `knowledge_bases.agent_definition_id` | Done |
| C3 fixed — frontend tests (4 cases) | Done |
| Backend tests updated and green | Done |
| TypeScript clean | Unchanged |
