# KIN-319 Code Review

**Reviewer:** Gilfoyle
**Date:** 2026-03-23
**Files reviewed:**
- `packages/api/app/api/routes/agents.py`
- `packages/api/tests/test_agents.py`
- `packages/web/lib/types/models.ts`
- `packages/web/app/(app)/agents/[id]/page.tsx`
- `packages/web/components/FrameworkLibraryTab.tsx`

---

## Strengths

- Race-safe SELECT→INSERT(CONFLICT DO NOTHING)→re-SELECT pattern is correctly implemented for instance creation.
- Route ordering: `/{agent_id}/instance` and `/{agent_id}/frameworks` registered before `/{agent_id}` catch-all — FastAPI routing is correct.
- Optimistic row removal with ref-based rollback is a good pattern.
- `get_supabase_client()` helper makes routes patchable in tests.
- All Supabase calls correctly use `run_in_executor`.
- Pre-review fix of `target.framework_id` → `target.id` in DELETE path caught before review.

---

## Issues Found

### Critical

**C1. `PATCH /{agent_id}/instance` — broken instance lookup** (`agents.py`)

`.eq("id", agent_id)` queries `agent_instances.id` with the agent definition UUID. These are different columns on different rows — the endpoint returned 404 for every real call. The test didn't catch it because mocked `.eq()` chains ignore argument values.

**Fix applied:** Changed to `.eq("agent_definition_id", agent_id).eq("user_id", current_user.user_id)`. Removed now-redundant ownership check (user_id filter IS the ownership check).

---

### Important

**I1. `framework_overrides` accepted as bare `dict`** (`agents.py`)

`UpdateAgentInstanceRequest.framework_overrides: dict` accepted `{"pinned": "string", "excluded": 99}`. No validation.

**Fix applied:** New `FrameworkOverrides(BaseModel)` with `pinned: list[str]`, `excluded: list[str]`. `UpdateAgentInstanceRequest` now uses it. `model_dump()` called on serialization to DB.

**I2. `list_frameworks` returned 403 for private non-owner agents** (`agents.py`)

`get_agent` returns 404 to hide private agent existence; `list_frameworks` raised 403, leaking existence. Inconsistent and a minor information disclosure.

**Fix applied:** Changed `AuthorizationError` → `NotFoundError("Agent not found")`. Test updated to assert 404.

**I3. `get_or_create_instance` had no access check** (`agents.py`)

Any authenticated user could create an `agent_instances` row for any `agent_id`, including nonexistent IDs and private agents from other users. Creates orphaned rows.

**Fix applied:** Added Step 0 — fetch agent, verify exists and is accessible (owner or public); raise 404 otherwise.

**I4. `AgentProfilePage` swallowed all fetch errors as "Agent not found"** (`page.tsx`)

Network failures, 500s, and auth expiry all resulted in `agent = null` showing "Agent not found." to users with valid agents.

**Fix applied:** Added `loadError` state. Non-404 failures set `loadError = true` → "Something went wrong. Please try again." message.

---

### Minor

**M1.** `test_patch_instance_overrides` mock used `.single()` on wrong chain — test passed because mock returns data regardless of call chain. Updated to match new `.eq().eq().single()` chain. Added `test_patch_instance_404_not_found` to cover the previously-undetected Critical #1.

**M2.** Optimistic rollback in `FrameworkLibraryTab` appends removed row to end rather than restoring original position. Benign for current usage but misleading on error. Deferred to KIN-320 when sorting is introduced.

**M3.** `AgentDefinition.instructions` typed as non-nullable `string` in `models.ts`. If the DB column is nullable (possible for drafts), this will cause a runtime type mismatch. Acceptable for now given current schema, but worth noting.

---

## Assessment

All Critical and Important issues fixed before merge. **APPROVED.**
