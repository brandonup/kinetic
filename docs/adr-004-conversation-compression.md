# ADR-004: Conversation History Compression + `updated_at` Trigger

**Status:** Accepted — Sprint 3
**Author:** Gilfoyle
**Issue:** KIN-270
**Implements:** Sprint 3 (compression background job). `updated_at` trigger included in initial DB migration.

---

## 1. Problem

Long conversations accumulate messages that eventually exceed the token budget allocated to conversation history in the context stack. Without compression, the assembler is forced to silently truncate old messages, losing potentially important context. A rolling summary strategy preserves the semantic content of older messages while keeping token usage bounded.

Additionally, the `conversations.updated_at` field must stay current to power conversation sorting in the UI (most-recently-active first). The mechanism for bumping this field must be decided before implementation.

---

## 2. Context Window Budget Calculation

This calculation justifies the compression threshold. We use a **16,384-token model** as the binding worst case (the smallest context window a user might configure via BYOK).

| Budget item | Token estimate |
|-------------|---------------|
| L1 — platform defaults | 500 |
| L2 — user preferences | 300 |
| L3 — scope instructions (generous) | 2,000 |
| L4 — active memory (stub in Sprint 3) | 0 |
| L8 — RAG floor | 2,048 |
| Response buffer | 2,048 |
| Current user message | 500 |
| **Total non-history overhead** | **7,396** |
| **Available for conversation history** | **16,384 − 7,396 = 8,988 tokens** |

At a conservative average of **300 tokens per message exchange** (user + assistant pair):

```
8,988 / 300 ≈ 29 message pairs = 58 individual messages
```

The 20-message threshold (10 pairs) is well within this budget for 16k models. **Compression is not about fitting the history into the budget on a 16k model — it is about predictability.** As conversations grow past 20 messages, token usage variance increases sharply depending on message length. Compressing at 20 ensures the history block never grows unboundedly regardless of message length or model choice.

For models smaller than 16k (e.g. 8k), the assembler's token budget enforcement in `token_budget.py` truncates history before injection regardless of compression state. The compression job improves quality; the budget enforcer is the hard safety net.

**Locked values:**

| Parameter | Value |
|-----------|-------|
| Compression trigger threshold | 20 total messages |
| Verbatim window | Last 10 messages |
| Messages compressed per run | All messages older than the verbatim window |

---

## 3. Rolling Summary — Compression Job

### 3.1 Trigger

The compression check is enqueued as a `BackgroundTask` at the end of every successful generation cycle, after the assistant message is persisted (step 9 in ADR-003 §9).

```python
background_tasks.add_task(maybe_compress_conversation, conversation_id, user_id)
```

`maybe_compress_conversation` is idempotent. It first checks:

```sql
SELECT COUNT(*) FROM messages WHERE conversation_id = ? AND role IN ('user', 'assistant')
```

If count ≤ 20: return immediately (no-op). If count > 20: proceed with compression.

### 3.2 Background job pattern

**Decision: FastAPI `BackgroundTasks` via `TaskDispatcher` abstraction (not direct).**

The generation endpoint adds the task to `BackgroundTasks` after the SSE stream closes. The `TaskDispatcher` abstraction (established in Sprint 1) wraps `BackgroundTasks.add_task` so that post-MVP migration to Celery/RQ requires only the dispatcher implementation to change — call sites are unaffected.

Compression is an acceptable fit for in-process `BackgroundTasks` because:
- It runs after the response is complete (no latency impact on the user).
- It is idempotent — if the process restarts mid-compression, the next message will re-trigger it.
- Failure is recoverable — the fallback (truncation) handles the missing summary gracefully.
- Summary generation typically completes in 2–5 seconds for a 20-message history — well within process lifetime.

### 3.3 Summary generation

**Model:** User's default BYOK model (same model used for conversation generation).

Rationale: the summary is part of the user's conversation context. Using the user's own BYOK key:
1. Keeps costs consistent with the user's model choice and budget.
2. Avoids platform key cost exposure for a per-user background job.
3. Ensures the same model that generates responses also summarises — stylistically consistent.

Platform embedding key is **not** used here (it is reserved for RAG embeddings only).

**Prompt template:**

```
You are summarising a conversation to preserve context while reducing length.

Produce a concise summary of the following conversation history. The summary must:
- Capture all decisions made, facts established, and open questions raised.
- Be written in the third person (e.g. "The user asked...", "The assistant explained...").
- Not exceed 400 words.
- Not include meta-commentary about the summarisation process.

Conversation:
{formatted_message_history}

Summary:
```

**Token target for summary:** 500 tokens maximum. The assembler uses `ceil(len(summary) / 4)` to estimate. If the model returns a longer summary, truncate at sentence boundary.

### 3.4 What gets compressed

All messages **except** the 10 most recent (by `created_at`) are included in the compression input. After a successful summary is saved, the older messages are **not deleted** — they remain in the `messages` table for audit/history purposes. The assembler uses the summary + verbatim window, not the raw older messages.

### 3.5 Subsequent compression runs

Each run compresses the entire pre-verbatim-window history into a single new summary row. The new summary incorporates the previous summary (if any) plus any messages that have since moved outside the verbatim window. Only the most recent summary row is used at assembly time.

Append-only: summary rows are never updated or deleted. `ORDER BY created_at DESC LIMIT 1` always retrieves the latest.

---

## 4. `conversation_summaries` Table

```sql
CREATE TABLE conversation_summaries (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id       UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  summary               TEXT NOT NULL,
  message_count_at_creation INT NOT NULL,  -- total messages when this summary was made
  last_message_id       UUID NOT NULL REFERENCES messages(id),  -- boundary: verbatim window starts after this message
  model_used            TEXT NOT NULL,     -- LiteLLM model string (e.g. "gpt-4o")
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_conversation_summaries_conversation_id
  ON conversation_summaries(conversation_id, created_at DESC);
```

**Append-only.** Rows are never updated. The most recent row per conversation is the active summary.

RLS: users may only SELECT summaries where `conversation_id` belongs to a conversation they own. INSERT is service-role only (background job runs under service role).

---

## 5. Fallback: BYOK Key Failure

If the BYOK LLM call for summary generation fails (key missing, provider error, rate limit):

1. Log the failure with `conversation_id` and error code.
2. Do **not** create a summary row.
3. The assembler falls back to raw truncation (oldest messages dropped until budget fits).
4. On the **next** user message in this conversation, the assembler detects no summary exists and conversation is still over threshold → re-enqueues the compression job. This creates a natural retry on the next interaction.
5. **User notification:** When the assembler falls back to truncation AND the conversation is over threshold AND no valid summary exists, append an inline system message to the context:

```
[System: Older conversation history has been trimmed to fit the context window.
Your conversation is available in full in the conversation history panel.]
```

This appears as a non-persisted context injection, not a saved `messages` row.

---

## 6. `conversations.updated_at` Trigger Decision

**Decision: Option A — DB trigger.** (Confirmed here; first stated in ADR-003 §10.)

Rationale and trigger definition are in ADR-003 §10. Reproduced here for completeness:

A `BEFORE INSERT` trigger on `messages` bumps `conversations.updated_at = NOW()` on the parent row. This is automatic, consistent, and path-independent.

**Tradeoffs:**

| | Option A (trigger) | Option B (explicit update) |
|---|---|---|
| Consistency | ✅ Automatic for all insert paths | ⚠️ Only if application remembers to call it |
| Visibility | ⚠️ "Magic" — not in application code | ✅ Visible in endpoint logic |
| Testability | Requires DB integration test | Unit-testable with mocks |
| Maintenance | One trigger definition | Update every code path that writes messages |

Option A is chosen. The trigger is documented here and in the schema spec. Integration tests in KIN-278/KIN-292 will exercise it.

---

## 7. Implementation Notes for Big Head + Dinesh

### Big Head (KIN-277 — compression job)

- Implement `maybe_compress_conversation(conversation_id, user_id)` in `app/services/compression.py`.
- Register as a `BackgroundTask` in the generation endpoint router (after stream close, step 9 in ADR-003).
- The function must be idempotent. Check message count first; return early if ≤ 20.
- Fetch messages excluding the 10 most recent. If a prior summary exists, include it in the compression prompt as a prelude.
- On BYOK failure: log, return without raising. Do not retry inline.
- Write a `conversation_summaries` row on success.

### Dinesh (KIN-272 — conversation CRUD)

- The `updated_at` trigger is applied via a DB migration. Dinesh does not need to write an explicit `UPDATE` in any code path.
- Confirm the migration is applied before Sprint 3 testing begins.
- The `conversations` list endpoint must order by `updated_at DESC` to reflect the most-recently-active conversation at the top.

---

## Done when

- [x] `docs/adr-004-conversation-compression.md` written
- [x] Threshold values confirmed (20 total / 10 verbatim window)
- [x] `updated_at` approach chosen (DB trigger — Option A)
- [ ] Big Head and Dinesh confirm before implementation starts
