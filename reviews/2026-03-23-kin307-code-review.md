# Code Review: KIN-307 — POST /api/v1/conversations/{id}/end

**Date:** 2026-03-23
**Reviewer:** Gilfoyle
**File reviewed:** `packages/api/app/api/routes/conversations.py`
**Tests reviewed:** `packages/api/tests/test_active_memory.py` — `TestConversationEndProposals`, `_make_conv_db`, constants at lines 761–821
**Spec:** `docs/specs/active-memory-spec.md` § Trigger 2
**Schema refs:** `docs/db-schema-spec.md` §2, §5, §6, §17, §19

**Verdict: Changes requested.** 2 Critical, 3 Important.

---

## Correctness

### Spec match — Trigger 2 behavior

The implementation satisfies the core Trigger 2 contract:
- 202 accepted immediately; background job dispatched non-blocking via `TaskDispatcher`
- Prompt matches spec verbatim (lines 35–42)
- `trigger_type = 'conversation_end'` set correctly
- Deduplication is case-insensitive against pending proposals for the same scope
- BYOK failure → silent skip; matches spec §Trigger 2 "BYOK failure" clause

### Agent-scoped proposals — schema gap (Critical)

The `memory_proposals` table (§17) has the same polymorphic pattern as `active_memory_entries` — either `project_id` XOR `agent_instance_id` must be set. The schema comment reads:

> `project_id` — Target scope (nullable)
> `agent_instance_id` — Target scope (nullable)

When `active_agent_id` is set on the conversation (agent-scoped conversation), the spec §Trigger 1 §Scope resolution clarifies that the entry goes to the user's `AgentInstance`, not the project. The `_generate_proposals_job` function fetches `active_agent_id` from the conversation row (line 109) but then **ignores it entirely** — all proposals are written with `project_id` regardless of agent context.

This is a correctness failure against §17 and against the scope-resolution logic described in §Trigger 1 of the spec. A project-scoped proposal will surface in the project proposal panel even when the conversation was agent-scoped. The fix requires:
1. Resolving `active_agent_id` → `agent_instance_id` for the calling user.
2. Writing `agent_instance_id` (not `project_id`) to the proposal row.

The deduplication query (step 7) has the same gap — it filters `project_id` only, so for agent-scoped conversations duplicate detection fails entirely.

**File:** `packages/api/app/api/routes/conversations.py`, lines 109–110, 244–254.

### Company-level skip — correct

Spec §Assumptions: "Company-level conversations do not have Active Memory." The `project_id` null-check (lines 124–131) implements this correctly.

### `deleted_at` filter missing on conversation fetch (Important)

The conversation lookup (line 108–115) does not filter `deleted_at IS NULL`. The schema §5 specifies conversations use soft-delete — a soft-deleted conversation should not receive new proposals. If a user deletes a conversation and ends it simultaneously (e.g., race on navigation), the background job can still insert proposals pointing to a deleted conversation's `conversation_id`. The `memory_proposals.conversation_id` FK has `ON DELETE CASCADE` (§17), so proposals would be orphaned on eventual hard-delete. Add `.is_("deleted_at", "null")` to the conversation query.

**File:** `conversations.py`, line 113.

### `key_ciphertext` / `key_nonce` storage type mismatch (Critical)

The schema (§2) specifies `key_ciphertext bytea` and `key_nonce bytea`. The implementation reads them as:

```python
ciphertext = bytes.fromhex(key_res.data["key_ciphertext"])
nonce = bytes.fromhex(key_res.data["key_nonce"])
```

`bytes.fromhex()` expects a hex string, not raw bytes. The existing encryption service writes `ciphertext` and `nonce` as raw `bytes` objects (see `encrypt_api_key` return type in `encryption.py` lines 71–88). The profile routes that originally store keys would persist `bytea` columns — the Supabase Python client returns `bytea` as `bytes`, not as a hex string. Calling `.fromhex()` on a `bytes` object raises `AttributeError: 'bytes' object has no attribute 'fromhex'`.

This is a runtime crash on the first real key decryption attempt. Every call to `_generate_proposals_job` for a user with a configured BYOK key will hit this path, log a warning, and silently skip — effectively disabling proposal generation for all users who have keys configured. The failure is silent (caught at line 186), so it will not surface in CI or basic smoke testing.

The correct pattern used elsewhere (verify against how keys are stored in `profile` routes) is:
```python
ciphertext = key_res.data["key_ciphertext"]   # already bytes from Supabase bytea
nonce = key_res.data["key_nonce"]              # already bytes
```

**File:** `conversations.py`, lines 183–184.

---

## Security

### Ownership verification — adequate for a background job

The endpoint captures `current_user.user_id` from the authenticated JWT before dispatching (line 282). The background job re-verifies ownership by filtering `conversations` on both `id` and `user_id` (lines 109–115). This is the correct pattern — the JWT user ID is captured at request time and passed into the job, so there is no TOCTOU window where a different user could hijack the job.

### User_id in job args — not a trust boundary issue

`user_id` is taken from `current_user.user_id` (the validated JWT sub claim), not from any user-supplied path parameter. No injection risk here.

### `key_nonce` uniqueness not validated

GCM nonce reuse with the same key breaks confidentiality. This is a pre-existing concern in the encryption layer — not introduced by KIN-307 — but worth noting that the `_generate_proposals_job` is the first place outside profile routes that touches raw ciphertext. No action required in this ticket; flag for encryption audit.

### Memory proposal INSERT uses service-role client

`get_supabase()` returns the service-role client (bypasses RLS). The RLS policy on `memory_proposals` states "INSERT: system/service role only" (§17). This is intentional and correct — background jobs are supposed to use service role for writes. No issue.

---

## Error Handling

### Silent-skip policy — correct application

The spec §Trigger 2 explicitly designates this path as best-effort ("the proposal path is a best-effort enhancement, not a core write"). Silent-skip on: no conversation, no project scope, no default model, model not found, no BYOK key, decryption failure, no messages, LLM failure, empty proposals. All are logged at `info` or `warning` level. This conforms to the spec and the conventions.md distinction (read-path fail-open is acceptable).

### Write errors swallowed — Important

The per-proposal insert (lines 253):
```python
client.table("memory_proposals").insert(row).execute()
```
The return value is discarded and no exception handling wraps it. Per conventions.md: "Never `return None/[]/False` in a `try/except` on write operations — raise or log-and-raise instead." An insert failure (network blip, constraint violation, DB error) will propagate as an unhandled exception that crashes the background job mid-loop — silently, because FastAPI `BackgroundTasks` catches all exceptions at the task boundary without re-raising.

This means: if insert fails on proposal #2 of 4, proposals #3 and #4 are never inserted, and the caller has no way to know. The fix is to wrap each insert in a `try/except` with `logger.error(...)` (not silent skip — write errors should be loud, not swallowed).

**File:** `conversations.py`, line 253.

### `_parse_proposals` swallows parse failures silently — Suggestion

`_parse_proposals` catches all exceptions and returns `[]` (lines 65–78). This is acceptable for a best-effort parser, but a `logger.debug()` on parse failure would aid debugging without changing the behavior.

---

## Test Quality

### Coverage — adequate but has gaps

**Covered:**
- `test_conversation_end_endpoint_fires_proposal_job` — verifies 202, dispatcher called once, `conversation_id` in args. Solid.
- `test_conversation_end_existing_proposals_append_not_duplicate` — verifies dedup logic (new unique proposal inserted, exact duplicate skipped). Directly calls the job function with patched dependencies. Good.
- `test_no_byok_key_conversation_end_silent_skip` — verifies `call_llm` not called when no key; no rows inserted. Good.

**Gaps — Important:**

1. **No test for agent-scoped conversation** — `_make_conv_db` hardcodes `active_agent_id: None`. There is no test that exercises the path where `active_agent_id` is set. This is the exact scenario that masks the Critical correctness bug above. A test should verify that when `active_agent_id` is non-null, the inserted proposal row has `agent_instance_id` set (not `project_id`).

2. **No test for soft-deleted conversation** — no test verifies that `_generate_proposals_job` skips a soft-deleted conversation (i.e., returns without inserting when `deleted_at IS NOT NULL`). Once the `deleted_at` filter is added, a test must cover it.

3. **`_make_conv_db` dispatch test does not verify `user_id` arg** — `test_conversation_end_endpoint_fires_proposal_job` checks `call_args[1] == CONVERSATION_ID` (the `conversation_id` arg) but does not assert `call_args[2]` (the `user_id`). If the endpoint accidentally passes a hardcoded value or wrong field, this would not catch it. Minor but worth adding.

4. **No test for `bytes.fromhex()` path** — there is no test that exercises the actual decryption path with a real ciphertext/nonce. `_make_conv_db` provides `_VALID_KEY_DATA = {"key_ciphertext": "deadbeef", "key_nonce": "cafebabe"}` (hex strings), and the test patches `decrypt_api_key` entirely so the bug is invisible in tests. Once the production code is fixed, a test that passes raw bytes (as Supabase would return) and does NOT patch `decrypt_api_key` (or minimally patches `derive_user_key`) would catch this regression.

5. **LLM failure silent-skip not tested** — there is no test verifying that if `call_llm` raises, the job exits cleanly with no proposals inserted.

---

## Issues Summary

| Severity | Location | Description |
|---|---|---|
| C | `conversations.py:109–110, 244–254` | Agent-scoped conversations write `project_id` to proposal instead of `agent_instance_id`; `active_agent_id` fetched but never acted on |
| C | `conversations.py:183–184` | `bytes.fromhex()` called on `bytea` columns that Supabase returns as `bytes` — crashes all real BYOK key decryption attempts silently |
| I | `conversations.py:113` | Conversation query missing `deleted_at IS NULL` filter — soft-deleted conversations can receive proposals |
| I | `conversations.py:253` | Per-proposal `insert().execute()` not wrapped — DB write failures crash the loop silently; partial insert with no visibility |
| I | `tests/test_active_memory.py:824–892` | No test for agent-scoped conversation path, soft-deleted conversation skip, LLM failure silent-skip, or real bytes decryption path |
| S | `conversations.py:65–78` | `_parse_proposals` exception path has no log statement — add `logger.debug()` to aid parse failure debugging |

---

## Disposition

**Changes requested.** Both Criticals must be fixed before merge:

- C1 (agent scope) requires a non-trivial logic addition: resolve `active_agent_id` → `agent_instance_id` for the calling user, then branch the proposal row construction and dedup query.
- C2 (bytea) is a one-line fix but has caused all real decryption to silently fail — every user with a configured BYOK key gets no proposals generated. This must be verified against how the profile routes actually write the key fields.
