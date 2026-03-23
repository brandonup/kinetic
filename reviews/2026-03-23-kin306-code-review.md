# Code Review — KIN-306: Periodic Memory Proposal Trigger

**Reviewer:** Gilfoyle
**Date:** 2026-03-23
**Ticket:** KIN-306 — Periodic background proposals on `POST /api/v1/conversations/{id}/messages`
**Verdict:** CHANGES REQUESTED — 2 Critical, 4 Important

**Files reviewed:**
- `packages/api/app/api/routes/conversations.py` — `StoreMessageRequest`, `_generate_periodic_proposals_job`, `store_message`
- `packages/api/tests/test_active_memory.py` — `_make_messages_db`, `TestPeriodicProposals`

**Spec refs:**
- `docs/specs/active-memory-spec.md` § Trigger 3
- `docs/db-schema-spec.md` §5 (conversations), §6 (messages), §17 (memory_proposals)
- `projects/kinetic/.agent-os/conventions.md`

---

## Summary

The routing structure, ownership check, sequence logic, and trigger math are correct. The debounce query fires only on multiples of 10 and correctly gates on pending proposals. However, two issues inherited from the `_generate_proposals_job` (KIN-307) have been carried forward into `_generate_periodic_proposals_job` unchanged, plus there are two additional issues specific to KIN-306. The test helper `_make_messages_db` has a structural problem that makes two of its three DB chains untestable from the message-count path, and the test class has coverage gaps on the boundary condition at count=20.

---

## Correctness

### C1 — `bytes.fromhex()` called on bytea columns that Supabase returns as `bytes` [CRITICAL]

**File:** `conversations.py`, lines 351–354

```python
ciphertext = bytes.fromhex(key_res.data["key_ciphertext"])
nonce = bytes.fromhex(key_res.data["key_nonce"])
```

`key_ciphertext` and `key_nonce` are `bytea` columns in Postgres. The Supabase Python client returns `bytea` as `bytes`, not as a hex string. Calling `bytes.fromhex()` on a `bytes` object raises `TypeError`. This exception is caught by the surrounding `try/except` and silently swallowed — every real BYOK key decryption will fail, periodic proposals will never fire for any user with a key configured, and no alarm will sound.

This is the same defect already flagged in KIN-307 for `_generate_proposals_job`. It was not corrected when the periodic variant was written.

**Fix:** Remove `bytes.fromhex()`:
```python
ciphertext = key_res.data["key_ciphertext"]  # already bytes
nonce = key_res.data["key_nonce"]             # already bytes
api_key = decrypt_api_key(ciphertext, nonce, master_key, user_id)
```

If the stored value is actually hex-encoded (check the encryption service), use `bytes.fromhex()` once and document why. The two callers must be consistent.

---

### C2 — Agent-scoped periodic proposals write `project_id` instead of `agent_instance_id` [CRITICAL]

**File:** `conversations.py`, lines 300–306 and 419–425

The job fetches `active_agent_id` from the conversation row but never uses it. When an agent is active (`active_agent_id` is set), the spec (§ Trigger 3, and §3.1) requires proposals to be scoped to `agent_instance_id`, not `project_id`. The current code always writes:

```python
row = {
    ...
    "project_id": project_id,
    "proposed_content": content,
    "trigger_type": "periodic",
}
```

For agent-scoped conversations, `project_id` will be set in the row AND `agent_instance_id` will be null. This violates the polymorphic constraint on `memory_proposals` (`chk_memory_proposals_single_parent` — same pattern as `active_memory_entries`). If the DB constraint is enforced the insert will fail; if it is not yet enforced the data is silently misrouted and the proposal will never surface on the Agent Profile page.

The dedup query (lines 400–410) is also scoped only to `project_id`, so if the agent path somehow wrote correctly, the dedup would miss all existing agent-scoped proposals.

This defect is the same as KIN-307's Critical finding for `_generate_proposals_job`. It was not corrected when the periodic variant was written.

**Fix:** Resolve the `AgentInstance` for the conversation's `active_agent_id` + `user_id` to get `agent_instance_id`, then conditionally set `project_id` XOR `agent_instance_id` on the row. The dedup query must use the same scope field.

---

### I1 — Message count query is not an aggregate — it fetches all message IDs [IMPORTANT]

**File:** `conversations.py`, lines 490–497

```python
count_res = await loop.run_in_executor(
    None,
    lambda: client.table("messages")
    .select("id")
    .eq("conversation_id", conversation_id)
    .execute(),
)
current_count = len(count_res.data or [])
```

This fetches every message ID in the conversation to get a count. For long conversations (100+ messages) this transfers unnecessary data. Supabase supports `count` queries:

```python
.select("id", count="exact")
```

Not a correctness bug — count will be accurate. Flagging as Important because it will degrade as conversations grow. Conversations can be long-lived; this path is hot (every message store triggers it).

**Fix:** Use `select("id", count="exact")` and read `count_res.count` instead of `len(count_res.data)`.

---

### I2 — Soft-deleted conversation can receive periodic proposals [IMPORTANT]

**File:** `conversations.py`, lines 477–485

The ownership check does not filter `deleted_at IS NULL`:

```python
client.table("conversations")
.select("id, project_id")
.eq("id", conversation_id)
.eq("user_id", current_user.user_id)
.single()
.execute()
```

A soft-deleted conversation that still has its JWT-bearing user making requests (e.g., a race condition between deletion and a pending request) could receive new messages and trigger proposal generation against a deleted entity.

**Fix:** Add `.is_("deleted_at", "null")` to the ownership check filter. Same fix applies to `_generate_periodic_proposals_job`'s conversation fetch at line 285.

---

## Security

### Security posture: satisfactory for this ticket

Ownership is verified before any DB mutation. The conversation query enforces `user_id = current_user.user_id`, so cross-user access is blocked. The background job re-verifies ownership independently (lines 285–306). BYOK keys are decryption-only — the plaintext key is not logged or returned. The periodic proposal insert uses service role (background task), consistent with the `memory_proposals` RLS policy (`INSERT: system/service role only`).

The only security concern is the soft-delete gap (I2) — a deleted conversation should not generate new proposals.

---

## Error Handling

### I3 — Per-proposal insert not wrapped; loop crash on DB failure is silent [IMPORTANT]

**File:** `conversations.py`, lines 413–425

```python
for content in proposals:
    if content.lower() in existing_content:
        continue
    row = { ... }
    client.table("memory_proposals").insert(row).execute()
    existing_content.add(content.lower())
```

If `insert().execute()` raises (transient Supabase error, constraint violation, network timeout), the exception propagates out of the loop and out of `_generate_periodic_proposals_job`. Since background tasks in FastAPI do not surface exceptions to the caller, this fails silently with no log entry and a partial insert. Per conventions: never swallow write errors — raise or log-and-raise.

**Fix:**
```python
try:
    client.table("memory_proposals").insert(row).execute()
except Exception as exc:
    logger.warning(
        "_generate_periodic_proposals_job: insert failed for conversation %s: %s",
        conversation_id, exc,
    )
    # Continue inserting remaining proposals rather than aborting the batch
```

The same unwrapped insert pattern appears in `_generate_proposals_job` (KIN-307 finding — already flagged there).

---

## Test Quality

### I4 — `_make_messages_db` message-count mock chain is not reached by `store_message` [IMPORTANT]

**File:** `tests/test_active_memory.py`, lines 738–741

```python
# Count query: select("id").eq(...)
m.select.return_value.eq.return_value.execute.return_value = MagicMock(
    data=[{"id": str(uuid4())} for _ in range(existing_message_count)]
)
```

The actual `store_message` endpoint queries messages with two `.eq()` calls:
```python
client.table("messages")
.select("id")
.eq("conversation_id", conversation_id)
.execute()
```

Wait — that is only one `.eq()`. So the mock chain `.select().eq().execute()` matches. However, the conversation ownership check also calls `.select().eq().eq().single().execute()`. The mock for `"conversations"` binds that chain to the conversation chain. The messages mock binds `.select().eq().execute()` — which works for the count query.

But the `messages.insert` mock:
```python
m.insert.return_value.execute.return_value = MagicMock(data=[stored_message])
```

This is correct. The insert chain is `client.table("messages").insert(row).execute()`.

**Revised finding:** The chains are structurally sound for the happy path. The actual gap is narrower: the debounce check at lines 523–530 queries:
```python
client.table("memory_proposals")
.select("id")
.eq("conversation_id", conversation_id)
.eq("status", "pending")
.execute()
```

That is two `.eq()` calls. The mock at line 747–749 wires:
```python
m.select.return_value.eq.return_value.eq.return_value.execute.return_value = ...
```

This matches two `.eq()` calls — correct.

On closer examination the mock wiring is structurally valid for the paths being tested. The actual test gap is coverage, not mock incorrectness.

### I4 (revised) — `test_non_tenth_message_does_not_trigger` missing count=19 → 20 boundary case [IMPORTANT]

**File:** `tests/test_active_memory.py`, line 788

```python
for existing_count in (0, 4, 8, 10):  # new_count = 1, 5, 9, 11
```

The test checks that non-tenth counts don't fire, but it does not include `existing_count=19` (new_count=20), which is the second trigger boundary. The spec says "every 10th message (message_count % 10 == 0)" — count=20 should trigger. The test only verifies count=10 fires. The count=20 case is not tested at all (neither trigger nor non-trigger direction).

Add `existing_count=19` to `test_tenth_message_triggers_proposal_job` (confirm it fires), and verify `existing_count=20` (new_count=21) to `test_non_tenth_message_does_not_trigger`.

### Additional coverage gaps

1. **`test_no_byok_key_periodic_silent_skip` asserts `inserted is not None`** (line 844) — `_make_conv_db` always returns a list, so this assertion never fails. It provides no signal. Remove it or replace with `assert inserted == []`.

2. **No test for `StoreMessageRequest` validation** — empty content, system role, missing role field. The validator at line 440 (`content_not_empty`) is untested.

3. **No test for conversation not found (404 path)** — `store_message` raises `NotFoundError` when the ownership check fails. No test exercises this path.

4. **No test for `_generate_periodic_proposals_job` with agent-scoped conversation** — given C2 above, this is a critical gap. The agent path is entirely untested, so the bug has zero coverage.

5. **No test verifying `trigger_type = "periodic"`** on inserted proposal rows — the test asserts dispatch is called but never verifies the job inserts rows with the correct `trigger_type`.

---

## Issues Summary

| # | Severity | Category | Description |
|---|---|---|---|
| C1 | Critical | `async-supabase` | `bytes.fromhex()` on bytea columns — crashes every real BYOK key decrypt |
| C2 | Critical | `schema-mismatch` | Agent-scoped conversations write `project_id` instead of `agent_instance_id` to proposals |
| I1 | Important | `other` | Count query fetches all message IDs instead of using `count="exact"` — degrades at scale |
| I2 | Important | `spec-gap` | Soft-deleted conversation not filtered in ownership check — can receive proposals |
| I3 | Important | `error-swallow` | Per-proposal `insert().execute()` unwrapped — silent partial insert on DB failure |
| I4 | Important | `test-missing` | Missing count=20 boundary test; no agent-scoped job test; no trigger_type assertion |

---

## Required Before Approval

1. Fix C1 — remove `bytes.fromhex()` from `_generate_periodic_proposals_job` (same fix needed in `_generate_proposals_job` per KIN-307).
2. Fix C2 — resolve `agent_instance_id` when `active_agent_id` is set; write `project_id` XOR `agent_instance_id`.
3. Fix I3 — wrap per-proposal insert in try/except with a warning log.
4. Fix I2 — add `deleted_at IS NULL` filter to the `store_message` conversation ownership check and to the job's conversation fetch.
5. Fix I4 — add count=20 trigger test, agent-scoped job test, `trigger_type` assertion.
