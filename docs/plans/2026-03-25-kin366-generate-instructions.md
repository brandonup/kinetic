# KIN-366: Generate Instructions from KB — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `POST /api/v1/agents/:id/generate-instructions` endpoint and a "Regenerate from corpus" button on the agent Instructions tab for `thought_leader` agents.

**Architecture:** Backend reads KB document chunks for the agent, concatenates text, sends to BYOK LLM with a generation prompt, returns drafted instructions. Frontend adds a conditional button (thought_leader only, owner only) that calls the endpoint and populates the instructions editor for review — no auto-save.

**Tech Stack:** FastAPI (Python), Next.js (TypeScript), Supabase (pgvector), LiteLLM via `call_llm`, shadcn/ui components.

**Spec:** `docs/specs/agents.md` §4, §7, §10 | **DB Schema:** `docs/db-schema-spec.md` §8, §10, §12

---

## Task 1: Add generation prompt to prompt registry

**Files:**
- Modify: `packages/api/app/services/prompts.py`

**Step 1:** Add `"generate-instructions-v1"` prompt to `PROMPTS` dict:

```python
"generate-instructions-v1": {
    "system_prompt_generate": (
        "You are building a system prompt for an AI agent that thinks and reasons "
        "like the person whose writing is provided below. Analyze the corpus for: "
        "(1) thinking style, (2) communication patterns, (3) core principles, "
        "(4) areas of expertise, (5) distinctive perspective. "
        "Generate a system prompt (300-500 tokens) written as instructions to an LLM. "
        "The prompt should begin with 'You are [name]...' and instruct the model to "
        "adopt this person's reasoning style, principles, and communication patterns. "
        "Do not simply summarize the documents. Synthesize across all provided content."
    ),
},
```

Note: This is intentionally similar to the `generate-agent-persona-v1` instructions_extract prompt but adapted for multi-document KB input (synthesize across documents vs. extract from single upload).

**Step 2:** Run: `python -m pytest tests/test_linked_upload.py -v` — verify no regressions. PASS expected.

**Step 3:** Commit: `feat(prompts): add generate-instructions-v1 prompt (KIN-366)`

---

## Task 2: Write failing tests for generate-instructions endpoint

**Files:**
- Create: `packages/api/tests/test_generate_instructions.py`

**Test cases (all mock Supabase + LLM):**

1. `test_owner_can_generate_instructions` — owner calls endpoint, agent has KB with docs, BYOK key exists → 200, returns `{ instructions: "..." }`
2. `test_non_owner_gets_403` — non-owner calls endpoint → 403
3. `test_no_kb_returns_400` — agent has no `knowledge_base_id` → 400
4. `test_no_docs_returns_400` — agent has KB but no documents (empty or all deleted) → 400
5. `test_no_api_key_returns_400` — user has no BYOK key configured → 400
6. `test_llm_failure_returns_500` — LLM call raises → 500 with error message

**Mock strategy:**
- Patch `get_supabase_client` (same pattern as `test_agents.py`)
- Patch `get_llm_client` or `call_llm` for LLM calls
- Use existing `conftest.py` fixtures (`client`, `TEST_USER_ID`)

**Step 1:** Write all 6 test functions. Run: `python -m pytest tests/test_generate_instructions.py -v` — all FAIL (endpoint doesn't exist yet).

---

## Task 3: Implement generate-instructions endpoint

**Files:**
- Modify: `packages/api/app/api/routes/agents.py` (add endpoint to existing router)

**Endpoint: `POST /api/v1/agents/{agent_id}/generate-instructions`**

**Logic flow:**
1. Auth: verify `current_user` owns the agent (403 if not)
2. Check agent has `knowledge_base_id` (400 if null)
3. Fetch documents from `knowledge_base_documents` where `knowledge_base_id = agent.knowledge_base_id` AND `deleted_at IS NULL` AND `status = 'completed'` (400 if empty)
4. Fetch document chunks from `document_chunks` for those document IDs, ordered by `chunk_index`
5. Concatenate chunk text, truncate to 12,000 chars (same `_TEXT_LIMIT_AGENT` as linked upload)
6. Get user's first BYOK key (same `_get_first_api_key` pattern from `linked_upload.py`)  — 400 if no key
7. Decrypt key, call `call_llm` with generation prompt + corpus text
8. Return `{ "instructions": generated_text }`

**Key patterns (from existing codebase):**
- All Supabase calls in `async def` use `run_in_executor`
- BYOK key decryption: `decrypt_api_key(bytes.fromhex(...), bytes.fromhex(...), master_key, user_id)`
- LLM call: `call_llm(messages=[...], model="gpt-4o-mini", api_key=api_key, max_tokens=800, timeout=30)`
- Error types: `AuthorizationError`, `NotFoundError`, `ValidationError` (from `app.core.errors`)

**Step 1:** Implement the endpoint. Import `get_prompt` from prompts service.

**Step 2:** Run: `python -m pytest tests/test_generate_instructions.py -v` — all 6 PASS.

**Step 3:** Run: `python -m pytest tests/test_agents.py -v` — no regressions.

**Step 4:** Commit: `feat(api): add generate-instructions endpoint (KIN-366)`

---

## Task 4: Write failing frontend tests

**Files:**
- Modify: `packages/web/app/__tests__/agents/[id]/page.test.tsx` (or create if doesn't exist)

**Test cases:**

1. `test_regenerate_button_visible_for_thought_leader_owner` — agent type=thought_leader, user is owner → button rendered
2. `test_regenerate_button_hidden_for_custom_agent` — agent type=custom → button NOT rendered
3. `test_regenerate_button_hidden_for_non_owner` — agent type=thought_leader, user is NOT owner → button NOT rendered
4. `test_regenerate_button_calls_api_and_populates_editor` — click button → mock API returns instructions → instructions textarea populated (not saved)

**Step 1:** Write tests. Run: `./node_modules/.bin/vitest run app/__tests__/agents/` — FAIL expected.

---

## Task 5: Implement frontend Regenerate button

**Files:**
- Modify: `packages/web/app/(app)/agents/[id]/page.tsx`

**Changes to Instructions tab section (lines 134-151):**

1. Convert Instructions tab to an editable textarea (owner only — read-only `<pre>` for non-owners)
2. Add state: `editedInstructions` (initialized from `agent.instructions`), `generating` (boolean)
3. Add "Regenerate from corpus" button — visible only when `agent.type === "thought_leader" && isOwner`
4. Button onClick: `POST /api/v1/agents/${id}/generate-instructions` via `apiFetch`
5. On success: set `editedInstructions` to returned value — does NOT auto-save
6. Add "Save" button (owner only) — calls `PATCH /api/v1/agents/${id}` with `{ instructions: editedInstructions }`
7. Loading/error states on the Regenerate button

**UI structure:**
```
Instructions tab (owner view):
  [Name: agent.name]
  [Textarea: editedInstructions]
  [Save button] [Regenerate from corpus button (thought_leader only)]

Instructions tab (non-owner view):
  [Name: agent.name]
  [Pre: agent.instructions] (read-only, no buttons)
```

**Step 1:** Implement the changes.

**Step 2:** Run: `./node_modules/.bin/vitest run app/__tests__/agents/` — all PASS.

**Step 3:** Run: `./node_modules/.bin/vitest run` — full suite, no regressions.

**Step 4:** Run: `./node_modules/.bin/tsc --noEmit` — TypeScript clean (ignore pre-existing FrameworkLibraryTab error).

**Step 5:** Commit: `feat(web): add regenerate-from-corpus button to agent instructions tab (KIN-366)`

---

## Task 6: Visual verification

**Step 1:** Start dev server (`preview_start` with `kinetic-web`).

**Step 2:** Navigate to `/agents/{thought_leader_agent_id}` — verify:
- Regenerate button visible on Instructions tab
- Textarea is editable
- Save button present

**Step 3:** Navigate to a `custom` agent — verify Regenerate button is NOT shown.

**Step 4:** Take screenshot for proof.

---

## Done-When Checklist

- [ ] `POST /api/v1/agents/:id/generate-instructions` returns generated instructions from KB
- [ ] Endpoint enforces: owner-only (403), KB required (400), docs required (400), BYOK required (400)
- [ ] "Regenerate from corpus" button visible for `thought_leader` + owner only
- [ ] Generated text populates textarea — does NOT auto-save
- [ ] Save button persists edited instructions via existing PATCH
- [ ] Backend tests: 6 cases passing
- [ ] Frontend tests: 4 cases passing
- [ ] Full suites green (API + web)
- [ ] TypeScript clean
- [ ] Visual verification via preview
