# Code Review — KIN-366: Generate Instructions from KB

**Reviewer:** Gilfoyle
**Date:** 2026-03-25
**Verdict:** CHANGES_REQUESTED
**Round:** 1

---

## Summary

Three Critical defects. The endpoint will fail at runtime on every real call. Two schema mismatches (wrong table name, non-existent column) and missing frontend tests. Changes required before approval.

---

## Critical Findings

### C1 — Schema mismatch: wrong table name for chunks
**File:** `packages/api/app/api/routes/agents.py`, line 873
**Severity:** Critical
**Category:** schema-mismatch

The endpoint queries `.table("document_chunks")`. This table does not exist. The canonical schema (db-schema-spec.md §13, migration `000_complete_schema.sql`) defines the table as `knowledge_base_chunks`. This query will fail at runtime with a Supabase 404/error on every real call. Tests pass only because the mock intercepts before the query reaches the DB.

Also compounding this: the column selected is `chunk_text` (line 874), but the actual column is named `text` (per db-schema-spec.md §13 and confirmed in migration DDL).

**Fix:**
```python
# Line 873 — change:
.table("document_chunks")
.select("chunk_text, chunk_index")
# To:
.table("knowledge_base_chunks")
.select("text, chunk_index")
```

And line 880, update the concatenation:
```python
# Change:
corpus_text = "\n\n".join(c["chunk_text"] for c in chunks if c.get("chunk_text"))
# To:
corpus_text = "\n\n".join(c["text"] for c in chunks if c.get("text"))
```

**Tests must also be updated:** `_chunk_rows()` helper in `test_generate_instructions.py` uses `chunk_text` — change to `text`. The `table_router` in all 3 test classes routes `"document_chunks"` — change to `"knowledge_base_chunks"`.

---

### C2 — Schema mismatch: `knowledge_base_id` does not exist on `agent_definitions`
**File:** `packages/api/app/api/routes/agents.py`, lines 39, 849–850
**Severity:** Critical
**Category:** schema-mismatch

The endpoint reads `agent.get("knowledge_base_id")` (line 849), which comes from `_AGENT_FIELDS` at line 39 that selects `knowledge_base_id` from `agent_definitions`. This column does not exist in `agent_definitions`. The canonical schema (db-schema-spec.md §8, migration DDL lines 196–205) defines `agent_definitions` with only: `id`, `owner_id`, `name`, `instructions`, `type`, `visibility`, `created_at`, `updated_at`. There is no `knowledge_base_id` column and no `ALTER TABLE ... ADD COLUMN` migration adding it.

The correct pattern per spec is **polymorphic ownership**: `knowledge_bases.agent_definition_id` is the FK. To find the KB for an agent, query `knowledge_bases WHERE agent_definition_id = agent_id`.

Note: this is also a pre-existing bug in `_AGENT_FIELDS` and `UpdateAgentRequest` (and the TS type `AgentDefinition.knowledge_base_id`) that predates this ticket. KIN-366 inherits and propagates it. Flagging here because KIN-366 is the first code that actually *acts* on `knowledge_base_id` from the agent row — without the fix the endpoint is broken.

**Fix — replace the KB lookup (steps 2-3 in the endpoint):**
```python
# Step 2: Find KB for this agent via knowledge_bases table
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

The rest of the endpoint (steps 3-onwards) uses `kb_id` correctly — no further changes needed there.

Also update `_AGENT_FIELDS` to remove `knowledge_base_id`:
```python
_AGENT_FIELDS = (
    "id, owner_id, name, instructions, type, visibility, mcp_enabled, created_at, updated_at"
)
```

And remove from `UpdateAgentRequest` (the agent can't store a KB reference directly — the KB stores the agent reference). The agent profile page frontend already has this wrong via `knowledge_base_id` on `AgentDefinition` — that's a separate cleanup ticket, but the backend must not compound it.

---

### C3 — Frontend tests missing entirely
**File:** `packages/web/app/__tests__/agents/[id]/page.test.tsx`
**Severity:** Critical
**Category:** test-missing

The implementation plan (Task 4) specifies 4 frontend test cases. The file does not exist. Zero frontend test coverage for:
1. Regenerate button visible for `thought_leader` + owner
2. Regenerate button hidden for `custom` agent
3. Regenerate button hidden for non-owner
4. Click → API called → textarea populated (not saved)

The existing `app/__tests__/agents/page.test.tsx` covers the agents *list* page (KIN-365), not this page. These are required — the plan explicitly marks them as part of the done-when checklist.

**Fix:** Create `packages/web/app/__tests__/agents/[id]/page.test.tsx` with the 4 cases from the implementation plan, following the mock pattern in the existing page tests.

---

## Important Findings

### I1 — `bytes.fromhex()` on bytea columns matches existing codebase pattern (accepted risk)
**File:** `packages/api/app/api/routes/agents.py`, lines 903–904
**Severity:** Important / Informational

The endpoint uses `bytes.fromhex(key_row["key_ciphertext"])` directly, without the `_to_bytes()` helper that `conversations.py` uses. `conversations.py` correctly handles both raw bytes and hex-prefixed strings (`\x...`). `linked_upload.py` uses the same raw `bytes.fromhex()` pattern as this endpoint.

Since `profile.py` stores keys as `.hex()` strings (line 208), and `linked_upload.py` uses the same raw pattern and is working in production, this is acceptable. The risk is that if Supabase ever returns the `\x`-prefixed bytea format, this will fail with a `ValueError`. This is existing technical debt shared with `linked_upload.py` — not introduced here. Not blocking this ticket but note it for the BYOK audit (KIN-333).

### I2 — Model hardcoded to `gpt-4o-mini` — should use user's default model
**File:** `packages/api/app/api/routes/agents.py`, line 912
**Severity:** Important
**Category:** spec-gap

The endpoint hardcodes `model="gpt-4o-mini"`. The spec (§7, Step 3) states: "sends KB contents + a generation prompt to the user's default LLM (BYOK)." The user's default model is stored in `users.default_model_id` → `llm_models.model_id`. The implementation ignores this entirely.

The existing `linked_upload.py` has the same hardcoded `gpt-4o-mini` pattern (it was flagged in KIN-340 but apparently not fixed). Since both are inconsistent with spec, this is a shared gap. Not blocking — but it means the spec claim ("user's default LLM") is not met. Dinesh should either fix to use the user's default model or update the spec to acknowledge the hardcoded model.

---

## Schema Cross-Reference Summary

| Table/Column Referenced | In Schema? | Notes |
|---|---|---|
| `agent_definitions` | Yes (§8) | |
| `agent_definitions.knowledge_base_id` | **No** | Does not exist. C2. |
| `knowledge_base_documents` | Yes (§12) | |
| `knowledge_base_documents.status` | Yes | |
| `knowledge_base_documents.deleted_at` | Yes | |
| `document_chunks` | **No** | Table is `knowledge_base_chunks`. C1. |
| `document_chunks.chunk_text` | **No** | Column is `text`. C1. |
| `document_chunks.chunk_index` | Exists as `chunk_index` on correct table | |
| `user_api_keys` | Yes (§2) | |
| `user_api_keys.key_ciphertext` | Yes (bytea) | |
| `user_api_keys.key_nonce` | Yes (bytea) | |

---

## Async/Supabase Pattern Audit

All 4 Supabase queries use `await loop.run_in_executor(None, lambda: ...)`. Compliant.

---

## Security Audit

- Owner-only check on line 845-846: correct. Agent is fetched first, then `owner_id` compared to `current_user.user_id`. 403 on mismatch.
- BYOK key decryption in-memory only — key not logged or returned.
- `master_key` from `load_master_key()` — not returned in response.
- Generated `instructions` returned as-is — no credential leak risk in this path.
- Corpus text (`corpus_text`) truncated at 12,000 chars — DoS mitigation is present.

---

## Error Handling Audit

- Non-owner: raises `AuthorizationError` (403). Correct.
- No KB: raises `ValidationError` (400). Correct.
- No docs: raises `ValidationError` (400). Correct.
- Empty corpus text: raises `ValidationError` (400). Correct.
- No API key: raises `ValidationError` (400). Correct.
- LLM failure: caught in `try/except`, logged with `logger.error`, raises `HTTPException(500)`. Correct — not silently swallowed.

---

## Frontend Review

### Correct
- `handleRegenerateInstructions` calls `POST` endpoint correctly.
- On success: populates `editedInstructions` state only — does NOT auto-save. Spec §7 Step 3 compliance.
- Button disabled while `generating = true`. Loading state shown.
- Button conditionally rendered: `agent.type === "thought_leader" && isOwner`. Correct.
- Save button correctly disabled when `!isDirty`. Prevents spurious saves.
- Error handling: `res.json().catch(() => null)` + toast on failure. No silent swallow.
- snake_case/camelCase: response body `{ instructions: string }` — both sides use `instructions` (no mapping needed for this field).

### Missing
- Frontend tests (C3 above).

---

## Done-When Checklist Status

| Item | Status |
|---|---|
| Endpoint returns generated instructions | Broken (C1, C2) |
| Owner-only (403) | Correct |
| KB required (400) | Broken (C2 — wrong lookup) |
| Docs required (400) | Broken (C1 — wrong table) |
| BYOK required (400) | Correct |
| Regenerate button visible thought_leader + owner | Correct |
| Generated text populates textarea, no auto-save | Correct |
| Save button persists via PATCH | Correct |
| Backend tests: 6 cases | Present but mocking wrong table names |
| Frontend tests: 4 cases | Missing (C3) |
| Full suites green | Not verifiable without fixes |
| TypeScript clean | Not checked — no new TS types added |

---

## Defect Log Entries

| Date | Ticket | Reviewer | Category | Severity | Description |
|---|---|---|---|---|---|
| 2026-03-25 | KIN-366 | Gilfoyle | schema-mismatch | Critical | Chunks queried from non-existent table `document_chunks`; correct table is `knowledge_base_chunks`; column `chunk_text` does not exist, correct column is `text` |
| 2026-03-25 | KIN-366 | Gilfoyle | schema-mismatch | Critical | `knowledge_base_id` selected from `agent_definitions` — column does not exist in schema; KB must be found via `knowledge_bases.agent_definition_id` FK |
| 2026-03-25 | KIN-366 | Gilfoyle | test-missing | Critical | Frontend tests for agent profile page (4 cases per plan) not implemented |
| 2026-03-25 | KIN-366 | Gilfoyle | spec-gap | Important | Model hardcoded to `gpt-4o-mini`; spec §7 requires user's default model |
