# Code Review: KIN-254 — Port LLM Client Abstraction (LiteLLM)

**Date:** 2026-03-22
**Reviewer:** Gilfoyle
**Verdict:** APPROVED
**Round:** 1

---

## Summary

Clean port. The Kinetic-specific changes (BYOK `api_key` routing, `PLATFORM_OPENAI_KEY`/`PLATFORM_ANTHROPIC_KEY` config, removal of `get_model_for_use_case`) are correctly implemented. Test coverage is solid for this module's scope. No Critical or Important findings.

---

## Files Reviewed

- `packages/api/app/services/llm_client.py`
- `packages/api/app/core/config.py`
- `packages/api/tests/test_llm_client.py`
- `packages/api/tests/conftest.py`

---

## Findings

### Critical (0)

None.

### Important (0)

None.

### Minor (3)

**M1 — `llm_client.py` line 18: unused `import os`**
`os` is imported but never used in `llm_client.py`. The FounderPanel source used it for `os.environ["GEMINI_API_KEY"]`; that was removed in this port but the import wasn't cleaned up. Remove it.

**M2 — `test_llm_client.py` line 16–17: unused imports `sys`, `call`, `pytest_asyncio`**
`sys`, `call` (from `unittest.mock`), and `pytest_asyncio` are imported but not referenced in any test. Clean up.

**M3 — `config.py` `is_reasoning_model` placement**
`is_reasoning_model` is a utility function for the LLM layer, not a config concern. It lives here because FounderPanel put it in config, but in Kinetic it would be cleaner in `llm_client.py` where it's consumed. Acceptable for now given it's a direct port — refactor when the chat service is implemented and consumption patterns are clear. No action required this ticket.

---

## Architecture Assessment

**BYOK design is correct.** `api_key` param on all three call surfaces (`call_llm`, `call_llm_with_response`, `stream_llm`). Conditional injection (`if api_key: completion_params["api_key"] = api_key`) correctly falls through to platform env keys when omitted. The null-or-empty string check (`if api_key:`) is the right behavior — an explicitly empty string is treated the same as None.

**Config separation is correct.** `PLATFORM_OPENAI_KEY`/`PLATFORM_ANTHROPIC_KEY` are clearly distinguished from BYOK keys. The docstring at module level makes the boundary explicit. Required-field validation in `validate_settings()` covers the right set.

**Error propagation is correct.** All three call surfaces re-raise on failure with no silent swallowing. The retry loop in `call_llm` correctly raises on non-length failures. `stream_llm` correctly classifies mid-stream failures as non-retryable.

**Test coverage is appropriate for this module.** 18 tests covering: provider routing (6), rate-limit classification (4), sync completion happy path + BYOK + platform-key + failure + retry (5), async streaming happy path + BYOK (2), import guard (1). The one gap (no test for `call_llm_with_response` BYOK pass-through) is Minor — the function is a thin wrapper with identical routing logic to `call_llm`.

---

## Checklist Confirmation

- No DB calls in this module — Supabase conventions N/A
- No tables referenced — schema cross-reference N/A
- Error handling: raises on failure, no silent swallow on any code path
- `get_model_for_use_case` correctly absent
- `is_reasoning_model` present (needed by future chat service)
- 18/18 tests passing (verified by Big Head before review)
