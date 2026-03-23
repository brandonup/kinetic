# ADR-004: Conversation History Compression Thresholds

**Author:** Gilfoyle
**Date:** 2026-03-22
**Status:** Accepted
**Supersedes:** —
**Superseded by:** —

---

## Context

Long conversations will eventually exceed LLM context windows. We need a rolling summary strategy: compress old messages into a summary, retain a verbatim window of recent messages, and handle failure gracefully. KIN-277 (compression job) and KIN-276 (generation endpoint trigger) depend on these threshold values.

---

## Decisions

### 1. Compression threshold

**Trigger:** rolling summary job fires when the conversation has more than **20 user-role messages**.

- Counted after persisting the latest user message in the generation endpoint.
- Only user-role messages count toward the threshold (not assistant messages, not system messages).
- Check: `IF message_count > 20 THEN dispatch compression job`.

Rationale: 20 user turns is roughly 3,000–8,000 tokens of conversation history depending on message length. This is conservative enough to avoid hitting context limits for most models while not running the compression job on every message.

### 2. Verbatim window

**After compression:** retain the **5 most recent user/assistant message pairs** (10 messages) verbatim.

- The verbatim window is counted from the most recent message backward.
- Messages older than the verbatim window are covered by the summary.
- The summary + verbatim window is what gets injected into L (history) by ADR-003.

Rationale: 5 pairs captures the immediate conversational context that the model needs for coherence. The summary covers everything before.

### 3. Summary model

- Use the **user's BYOK default model** (`user.default_model_id`) for summary generation.
- Same model as the one used for generation (not a separate lightweight model).
- Rationale: using the same model avoids a second provider key requirement. Post-MVP we may route compression to a cheaper/faster model.

### 4. Summary prompt

```
You are summarizing a conversation to compress it for long-term context.

Preserve:
- Key facts established (names, decisions, preferences, entities mentioned)
- Open questions that have not been resolved
- Action items or commitments made
- Any context that would be necessary for the conversation to continue coherently

Do not include:
- Pleasantries and filler
- Repeated information
- Step-by-step reasoning that led to a conclusion (just the conclusion)

Respond with a concise summary in plain prose (no bullet points). Maximum 300 tokens.
```

### 5. Fallback on BYOK failure

If the summary call fails (BYOK key invalid, provider timeout, rate limit):

1. **Do not crash the generation endpoint.** The background job logs the failure and exits cleanly.
2. **Fallback behavior:** context stack assembly falls back to raw message truncation — oldest messages are excluded from history injection until the history fits within the token budget (per ADR-003 truncation priority, step 6).
3. **User notification:** when the fallback truncation path is taken, inject a synthetic system message at the top of the conversation history: `[Older messages were trimmed to fit context limits]`. This is surfaced to the user in the chat thread as a grey info bar.
4. **No retry:** the compression job does not retry automatically. It will attempt again on the next trigger (every 10th message).

### 6. `conversation_summaries` table behavior

Each successful compression inserts a new row in `conversation_summaries`:

| Field | Value |
|-------|-------|
| `conversation_id` | FK to conversation |
| `summary` | Generated summary text |
| `messages_covered_up_to` | `sequence` value of the last message included in this summary |
| `created_at` | Timestamp of summary generation |

Context assembly always uses the **most recent** `conversation_summaries` row. Old rows are retained for auditability (not deleted). Post-MVP: prune old rows on a schedule.

### 7. Re-compression

When compression fires again (another 10 messages after the last summary):

- The new summary covers messages from the previous summary's `messages_covered_up_to + 1` up to the current message minus the verbatim window.
- The new summary prompt includes the previous summary as context: "Here is a prior summary: [previous summary]. Now summarize the following additional messages, incorporating what came before."
- The new row's `messages_covered_up_to` reflects the new coverage end.

---

## Threshold values (summary)

| Parameter | Value |
|-----------|-------|
| Compression trigger | >20 user messages |
| Verbatim window | 5 user/assistant pairs (10 messages) |
| Summary max tokens | 300 tokens |
| Summary model | User BYOK default |
| Retry on failure | No (next trigger) |

---

## Consequences

- Threshold of 20 is conservative. If most conversations are short (under 20 turns), the compression infrastructure is built but rarely exercised at MVP. That's acceptable — correctness matters more than optimization.
- Using the user's default model for compression means users without a BYOK key configured will hit the fallback path. This is correct behavior: if they can't generate, they can't compress.
- 300-token summaries are intentionally short. A conversation of 20+ turns can be meaningfully summarized in 200–300 tokens. If summaries are too long, they consume the context budget they're trying to free up.
