#!/bin/bash
# KIN-307 commit script — run from repo root
set -e
cd "$(dirname "$0")/../../../.."
git add \
  projects/kinetic/packages/api/app/api/routes/conversations.py \
  projects/kinetic/packages/api/app/main.py \
  projects/kinetic/packages/api/tests/test_active_memory.py

git commit -m "feat: conversation-end active memory proposals trigger (KIN-307)

Implements POST /api/v1/conversations/{id}/end — fires a non-blocking
background job that reviews the full conversation with the user's BYOK
LLM and inserts AI-proposed memory entries into memory_proposals.

- POST /api/v1/conversations/{id}/end → 202 (dispatches bg job)
- _generate_proposals_job: fetch conv scope → BYOK key lookup → call_llm
  → parse JSON array → content-level dedup → insert memory_proposals rows
- trigger_type='conversation_end', silent-skip policy: no BYOK, no model,
  LLM failure all return silently (no error surfaced to caller)
- Appends to existing pending proposals (never blocks on prior batch)
- 3 new tests passing: endpoint dispatch, append-not-duplicate, no-BYOK-skip
- 176 total tests passing, 14 skipped

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
