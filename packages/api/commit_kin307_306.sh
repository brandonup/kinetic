#!/bin/bash
# KIN-307 + KIN-306 commit script — run from repo root
set -e
cd "$(dirname "$0")/../../../.."
git add \
  projects/kinetic/packages/api/app/api/routes/conversations.py \
  projects/kinetic/packages/api/app/main.py \
  projects/kinetic/packages/api/tests/test_active_memory.py

git commit -m "feat: active memory proposal triggers — conversation-end + periodic (KIN-307, KIN-306)

Implements two background proposal triggers that review conversations
with the user's BYOK LLM and queue proposals into memory_proposals.

KIN-307 — Conversation-end trigger:
- POST /api/v1/conversations/{id}/end → 202 (dispatches bg job)
- _generate_proposals_job: full conversation review, trigger_type='conversation_end'

KIN-306 — Periodic 10-message trigger:
- POST /api/v1/conversations/{id}/messages → 201 (stores message)
- Every 10th message dispatches _generate_periodic_proposals_job
- Debounce: skip dispatch if pending proposals already exist for conv
- _generate_periodic_proposals_job: last 10 messages, trigger_type='periodic'

Both jobs share:
- BYOK pattern: default_model_id → llm_models → user_api_keys → decrypt → call_llm
- _to_bytes(): handles Supabase bytea columns (bytes, \\x-prefixed hex, plain hex)
- _resolve_scope(): agent_instance > project > company-level skip
- Agent-scoped conversations write agent_instance_id (not project_id) to proposals
- deleted_at IS NULL filter on all conversation fetches (including store_message endpoint)
- Per-proposal insert wrapped in try/except logger.error() — write failures are loud
- Silent-skip policy: no BYOK, no model, LLM failure → return without error

Tests — 11 new tests (187 total passing, 6 skipped):
- Endpoint dispatch, append-not-duplicate, no-BYOK skip, agent-scope (KIN-307)
- 10th trigger, 20th trigger, non-10th silent, debounce, no-BYOK skip, agent-scope (KIN-306)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
