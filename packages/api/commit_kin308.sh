#!/bin/bash
# KIN-308 commit script — run from repo root
set -e
cd "$(dirname "$0")/../../../.."
git add \
  projects/kinetic/packages/api/app/core/errors.py \
  projects/kinetic/packages/api/app/api/routes/active_memory.py \
  projects/kinetic/packages/api/app/main.py \
  projects/kinetic/packages/api/tests/test_active_memory.py \
  projects/kinetic/docs/plans/2026-03-23-active-memory-crud.md

git commit -m "feat: active memory CRUD + token cap enforcement (KIN-308)

Implements active_memory_entries CRUD and memory_proposals review
endpoints with hard token-cap enforcement (project=1000t, agent=500t).

- GET/POST/PATCH/DELETE /api/v1/active-memory (entries)
- GET /api/v1/active-memory/proposals (list pending)
- POST /api/v1/active-memory/proposals/review (bulk accept/reject)
- GET /api/v1/admin/active-memory (admin read-any-user)
- MemoryCapExceededError (422) added to errors.py
- Token count: ceil(len(content)/4), no tiktoken dependency
- 155 tests passing (24 new), 6 skipped

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
