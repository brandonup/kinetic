# Code Review — KIN-366: Generate Instructions from KB (Round 2)

**Reviewer:** Gilfoyle
**Date:** 2026-03-25
**Verdict:** CHANGES_REQUESTED
**Round:** 2

---

## Summary

C1 and C3 are fully resolved. C2 is not. The `knowledge_base_id` column still does not exist in the canonical schema (`db-schema-spec.md` §8) or the migration DDL (`000_complete_schema.sql` lines 196–205). The R2 "fix" added a comment pointing to `agents.md §2`, but `agents.md §2` is not the canonical schema document — `db-schema-spec.md` is, and it explicitly states it wins on conflict (§ Purpose). The endpoint will fail at runtime on every call because it selects a column that Supabase will not return.

---

## Fix Verification

### C1 — FIXED

Table name corrected to `knowledge_base_chunks`, column corrected to `text`, corpus join updated to `c["text"]`. Backend tests route to `"knowledge_base_chunks"` and `_chunk_rows()` uses `"text"`. Correct.

### C2 — NOT FIXED

**File:** `packages/api/app/api/routes/agents.py`, lines 39, 848–851
**Severity:** Critical (persists from R1)
**Category:** schema-mismatch

The endpoint still reads `agent.get("knowledge_base_id")` from a Supabase query that selects `_AGENT_FIELDS`, which includes `knowledge_base_id`. The migration DDL (`000_complete_schema.sql` lines 196–205) creates `agent_definitions` with columns: `id`, `owner_id`, `name`, `instructions`, `type`, `visibility`, `created_at`, `updated_at` — no `knowledge_base_id`. The canonical schema spec (`db-schema-spec.md` §8) lists the same eight columns. The claim that "the column exists in production" is unverified and contradicted by the migration file.

The R2 fix — adding a comment pointing to `agents.md §2` — is not a fix. `agents.md §2` is a product spec, not the canonical schema document. `db-schema-spec.md` explicitly states: "Single source of truth — no other document defines DDL. All implementation code must reference this spec for table names, column names, types, and constraints. Inline DDL in other specs is advisory only; this document wins on conflict." The column is not in `db-schema-spec.md` §8. Therefore it is not a valid column reference.

**Required resolution (choose one):**

Option A — Fix the endpoint lookup (no schema change required):
```python
# Step 2: Find KB for this agent via knowledge_bases table (polymorphic FK — see db-schema-spec.md §10)
kb_result = await loop.run_in_executor(
    None,
    lambda: client
        .table("knowledge_bases")
        .select("id")
        .eq("agent_definition_id", agent_id)
        .single()
        .execute(),
)
kb = kb_result.data
if not kb:
    raise ValidationError("Agent has no knowledge base. Upload documents first.")
kb_id = kb["id"]
```
Also remove `knowledge_base_id` from `_AGENT_FIELDS` for this endpoint (or leave it and just don't use it — but removing avoids misleading future readers).

Option B — Add the column to the schema (migration + spec update required):
- Add `knowledge_base_id uuid REFERENCES public.knowledge_bases(id) ON DELETE SET NULL` to `000_complete_schema.sql` `agent_definitions` table.
- Add `knowledge_base_id` to `db-schema-spec.md` §8 with correct type, constraint, and notes.
- Update `agents.md §2` to confirm.
This is more invasive. Option A is the lower-risk fix — it uses the existing polymorphic FK that `knowledge_bases.agent_definition_id` already provides.

**Note on agents.md §2:** The spec field table in `agents.md §2` lists `knowledge_base_id` on `agent_definitions`. This is a spec-schema conflict that predates this ticket. If Option A is chosen, `agents.md §2` should be updated to remove the field or note that the KB is discovered via `knowledge_bases.agent_definition_id`. This is a product call for Jared.

### C3 — FIXED

All 4 frontend tests present in `packages/web/app/__tests__/agents/[id]/page.test.tsx`:
- Regenerate button visible: thought_leader + owner ✓
- Regenerate button hidden: custom agent ✓
- Regenerate button hidden: non-owner ✓
- Click → API called → textarea populated (not saved) ✓

Test mocking pattern is correct: `apiFetch` mocked at module level, table routing via `mockImplementation` with URL matching. Toast mocked. Sibling tabs stubbed to prevent their own API calls from interfering.

---

## Remaining Issues

### I1 — model hardcoded to `gpt-4o-mini`

Same as R1. Accepted as known gap matching linked upload pattern (KIN-340). Not blocking.

---

## Async/Supabase Pattern

No change from R1. All calls use `run_in_executor`. Compliant.

---

## Error Handling

No change from R1. All paths raise or log-and-raise. No silent swallows.

---

## Done-When Checklist

| Item | Status |
|---|---|
| C1 fixed — correct table/column names | Done |
| C2 fixed — KB lookup via correct pattern | **Not done** |
| C3 fixed — frontend tests (4 cases) | Done |
| Backend tests updated and green | Done (given C1 fix) |
| TypeScript clean | Unchanged — no new TS types added |
