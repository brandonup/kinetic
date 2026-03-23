# KIN-254: LLM Client Abstraction (LiteLLM) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Port and adapt FounderPanel's LiteLLM client into Kinetic's backend package, adding BYOK key routing and stripping FounderPanel-specific concerns.

**Architecture:** Single module at `packages/api/app/services/llm_client.py` mirrors the FounderPanel source but adds an `api_key` param to all call surfaces so BYOK user keys can be passed through to LiteLLM. Platform-owned keys (embedding, reranker) remain in `Settings`. Config (`packages/api/app/core/config.py`) is Kinetic-specific — no FounderPanel model use-cases, no Qdrant, no Debate/Transcript fields.

**Tech Stack:** Python 3.11+, LiteLLM, pydantic-settings, pytest + pytest-asyncio

**Source to port from:** `/Users/brandonupchuch/Projects/founder_panel/backend/app/services/llm_client.py` and `/Users/brandonupchuch/Projects/founder_panel/backend/app/core/config.py`

**Output location:** `/Users/brandonupchuch/son_of_anton/projects/kinetic/packages/api/` (Dinesh copies this into the kinetic3 repo when bootstrapping)

---

## Task 1: Create package skeleton

**Files:**
- Create: `packages/api/app/__init__.py`
- Create: `packages/api/app/core/__init__.py`
- Create: `packages/api/app/services/__init__.py`

**Step 1:** Create the three empty `__init__.py` files. The `Write` tool creates parent dirs automatically — no mkdir needed (bighead-memory lesson).

**Step 2:** Verify directory structure with `ls packages/api/app/`.

---

## Task 2: Write `config.py` with Kinetic settings

**Files:**
- Create: `packages/api/app/core/config.py`
- Test: `packages/api/tests/test_llm_client.py` (env injection in conftest)

**Kinetic settings (not in FounderPanel):**
- `API_KEY_ENCRYPTION_KEY: str` — AES-256-GCM key for user API key encryption. Required.
- `PLATFORM_OPENAI_KEY: str` — Platform-owned key for embedding + pipeline LLM calls. Required.
- `PLATFORM_ANTHROPIC_KEY: str = ""` — Platform key for Haiku reranker calls.
- `FRAMEWORK_RERANKER_MODEL: str = "claude-haiku-3-5"` — Haiku for framework selection reranker.
- `EMBEDDING_MODEL: str = "text-embedding-3-large"` — Platform-owned embedding model.
- `CONVERSATION_COMPRESSION_MODEL: str = "claude-haiku-3-5"` — For rolling summary compression.

**Drop from FounderPanel:** Qdrant, Debate, Transcript, Enrichment, MMR, Rerank, SimpleRAG, Cohere, all per-use-case model fields (Kinetic uses per-query user selection, not admin-configured use-case models).

**Keep from FounderPanel:** Supabase fields, CORS, APP_NAME (→ "Kinetic"), DEBUG, ENVIRONMENT, CORS_ORIGINS validator, `validate_settings()` pattern, `is_reasoning_model()`.

**Step 1:** Write `config.py`. Required fields that must be provided: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`, `API_KEY_ENCRYPTION_KEY`, `PLATFORM_OPENAI_KEY`. All LLM provider user keys default to `""` (they come from BYOK, not platform env).

**Step 2:** Add env injection to `packages/api/tests/conftest.py` at module level (before any imports) — pydantic-settings lesson: use `os.environ.setdefault(...)` for required fields in conftest.

---

## Task 3: Write failing tests for `llm_client.py`

**Files:**
- Create: `packages/api/tests/test_llm_client.py`
- Read: `packages/api/tests/conftest.py` before editing (bighead-memory lesson)

**Behaviors to test:**

| Test | Behavior |
|---|---|
| `test_get_provider_model_openai` | `"gpt-4o"` → `"gpt-4o"` (no prefix) |
| `test_get_provider_model_claude` | `"claude-haiku-3-5"` → `"anthropic/claude-haiku-3-5"` |
| `test_get_provider_model_gemini` | `"gemini-2.5-flash"` → `"gemini/gemini-2.5-flash"` |
| `test_get_provider_model_groq` | `"llama-3.3-70b-instruct"` → `"groq/llama-3.3-70b-instruct"` |
| `test_get_provider_model_empty` | `""` → `"gpt-4o-mini"` (default fallback) |
| `test_call_llm_success` | Mocked `litellm.completion` returns content; `call_llm` returns string |
| `test_call_llm_passes_api_key` | When `api_key` provided, it appears in `litellm.completion` call kwargs |
| `test_call_llm_platform_key_used_when_no_byok` | When no `api_key`, `api_key` kwarg is absent from litellm call (LiteLLM uses env) |
| `test_call_llm_raises_on_failure` | LiteLLM raises → `call_llm` re-raises (no silent swallow) |
| `test_call_llm_retries_on_empty_with_length_finish` | Empty content + `finish_reason="length"` → retry with 4x tokens |
| `test_stream_llm_yields_text` | `stream_llm` yields text deltas from async mock stream |
| `test_stream_llm_passes_api_key` | `api_key` param flows through to `litellm.acompletion` |
| `test_is_rate_limit_error_true` | Exception with "rate limit" in message → `True` |
| `test_is_rate_limit_error_false` | Generic exception → `False` |
| `test_require_litellm_raises_when_none` | With litellm patched to None, `_require_litellm()` raises `ModuleNotFoundError` |

**Step 1:** Write `test_llm_client.py` with all tests marked `@pytest.mark.skip` — tests are scaffolded but not yet passing (TDD: write failing tests first).

**Step 2:** Remove the skip markers from the non-async `get_provider_model` and `is_rate_limit_error` tests only (these are pure functions, can pass immediately).

**Step 3:** Run `pytest packages/api/tests/test_llm_client.py -v` from the son_of_anton project root (or the right working dir). Expect failures on the async/litellm tests, passes on the pure-function tests.

**Step 4:** Remove skip from remaining tests.

**Step 5:** Run again — all should fail with ImportError or AttributeError (llm_client not yet implemented).

---

## Task 4: Implement `llm_client.py`

**Files:**
- Create: `packages/api/app/services/llm_client.py`

**Delta from FounderPanel source** (all other logic is a direct port):

1. **Add `api_key: Optional[str] = None`** to `call_llm`, `call_llm_with_response`, and `stream_llm` signatures.
2. **Pass `api_key` to LiteLLM** only when not None/empty:
   ```python
   if api_key:
       completion_params["api_key"] = api_key
   ```
3. **Module-level LiteLLM init** uses `settings.PLATFORM_OPENAI_KEY` and `settings.PLATFORM_ANTHROPIC_KEY` (not OPENAI_API_KEY / ANTHROPIC_API_KEY from FounderPanel).
4. **Remove `get_model_for_use_case`** — Kinetic doesn't use DB-backed use-case model config. Per-query model comes from the user's UI choice.
5. **Keep `is_reasoning_model`** — needed for the chat service to know when to use `max_completion_tokens`.
6. **Import guard pattern** — keep the `litellm_import_error` / `_require_litellm()` guard exactly as in FounderPanel.

**Step 1:** Write `llm_client.py` following the FounderPanel source with the deltas above.

**Step 2:** Run the full test suite: `pytest packages/api/tests/test_llm_client.py -v`.

**Step 3:** Fix any failures. Watch for: mock `assert_called_once_with` — use `unittest.mock.ANY` for args that are opaque strings (bighead-memory lesson).

**Step 4:** Run full suite again — all 15 tests must pass.

---

## Task 5: Verification and commit

**Step 1:** Run the complete test file with count: `pytest packages/api/tests/test_llm_client.py -v --tb=short`. Record count (must be ≥15, 0 failures).

**Step 2:** Self-review checklist (no DB calls in this module — only items 5 and 6 apply):
- [ ] Tests pass with count
- [ ] No `try/except` that returns `None`/`[]`/`False` on write operations — only `call_llm` reads, so fail-open is acceptable but `raise` is used on LLM failures (check: FounderPanel raises, keep it)
- [ ] `api_key` param present on all three call surfaces (`call_llm`, `call_llm_with_response`, `stream_llm`)
- [ ] `get_model_for_use_case` is absent
- [ ] Config uses `PLATFORM_OPENAI_KEY` / `PLATFORM_ANTHROPIC_KEY`, not bare `OPENAI_API_KEY`

**Step 3:** Generate commit script to `/private/tmp/claude-501/commit_kin254.sh` (sandbox blocks git index — use script pattern):
```bash
#!/bin/bash
cd /Users/brandonupchuch/son_of_anton
git add projects/kinetic/packages/api/app/__init__.py \
        projects/kinetic/packages/api/app/core/__init__.py \
        projects/kinetic/packages/api/app/core/config.py \
        projects/kinetic/packages/api/app/services/__init__.py \
        projects/kinetic/packages/api/app/services/llm_client.py \
        projects/kinetic/packages/api/tests/test_llm_client.py \
        projects/kinetic/packages/api/tests/conftest.py \
        projects/kinetic/docs/plans/2026-03-22-kin254-llm-client.md
git commit -m "feat: port LiteLLM client abstraction for Kinetic (KIN-254)

Adds LLM client with BYOK api_key routing and platform-key config.
Ports call_llm, call_llm_with_response, stream_llm from FounderPanel.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

**Step 4:** Tell Brandon to run: `bash /private/tmp/claude-501/commit_kin254.sh`

---

## Done-When

- [ ] `packages/api/app/core/config.py` — Kinetic settings, no FounderPanel-specific fields
- [ ] `packages/api/app/services/llm_client.py` — `call_llm`, `call_llm_with_response`, `stream_llm`, `get_provider_model`, `is_reasoning_model` all present; `api_key` param on all call surfaces
- [ ] `packages/api/tests/test_llm_client.py` — ≥15 tests, 0 failures
- [ ] No `get_model_for_use_case` in Kinetic client (Kinetic uses per-query user model selection)
- [ ] Commit script generated for Brandon to run
- [ ] Linear: KIN-254 moved to Code Review; comment: test count + command

---

## Test Strategy

- Mock `litellm.completion` and `litellm.acompletion` with `unittest.mock.patch` — no real API calls in tests.
- Use `AsyncMock` for async streaming; return a mock async iterator.
- Pure-function tests (`get_provider_model`, `is_rate_limit_error`, `is_reasoning_model`) need no mocks.
- Inject required env vars in `conftest.py` at module level (`os.environ.setdefault`) before config import.
- Use `pytest.raises` on failure cases — never assert on a caught exception without re-raising.
