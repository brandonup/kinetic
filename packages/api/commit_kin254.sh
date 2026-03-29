#!/bin/bash
set -e
cd /Users/brandonupchuch/son_of_anton
git add \
  projects/kinetic/packages/api/app/__init__.py \
  projects/kinetic/packages/api/app/core/__init__.py \
  projects/kinetic/packages/api/app/core/config.py \
  projects/kinetic/packages/api/app/services/__init__.py \
  projects/kinetic/packages/api/app/services/llm_client.py \
  projects/kinetic/packages/api/tests/test_llm_client.py \
  projects/kinetic/packages/api/tests/conftest.py \
  projects/kinetic/docs/plans/2026-03-22-kin254-llm-client.md \
  projects/kinetic/reviews/2026-03-22-kin254-code-review.md
MSG="feat: port LiteLLM client abstraction for Kinetic (KIN-254)

Adds BYOK api_key routing to all call surfaces (call_llm, call_llm_with_response,
stream_llm). Platform-owned keys in config (PLATFORM_OPENAI_KEY / PLATFORM_ANTHROPIC_KEY).
Strips FounderPanel-specific fields; no get_model_for_use_case (per-query user selection).
18 tests passing.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git commit -m "$MSG"
echo "Commit complete."
