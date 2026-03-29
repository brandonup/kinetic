#!/bin/bash
# KIN-306 commit script — run from repo root
set -e
cd "$(dirname "$0")/../../../.."
git add \
  projects/kinetic/packages/api/app/api/routes/conversations.py \
  projects/kinetic/packages/api/tests/test_active_memory.py

git commit -m "feat: periodic active memory proposals trigger (KIN-306)

Implements POST /api/v1/conversations/{id}/messages with a 10-message
periodic proposal trigger. Every 10th message dispatches a background
job that reviews the last 10 messages with the user's BYOK LLM and
queues memory proposals for user review.

- POST /api/v1/conversations/{id}/messages → 201 (stores message)
- 10th-message trigger: dispatch _generate_periodic_proposals_job
- Debounce: skip dispatch if pending proposals already exist for conv
- _generate_periodic_proposals_job: same BYOK/silent-skip pattern as
  conversation_end job; uses last 10 messages; trigger_type='periodic'
- 4 new tests: 10th triggers, non-10th silent, debounce, no-BYOK skip
- 184 total tests passing, 6 skipped

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
