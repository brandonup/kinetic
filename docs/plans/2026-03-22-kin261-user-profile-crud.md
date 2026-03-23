# KIN-261: User Profile CRUD Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement User Profile CRUD — name, bio, API keys (AES-256-GCM encrypted), and default model selector — including backend API, encryption utilities, log scrub middleware, and the profile settings UI.

**Architecture:** Backend adds `app/services/encryption.py` (HKDF+AES-256-GCM per spec), `app/middleware/log_scrub.py` (redact sensitive fields), and `app/api/routes/profile.py` (6 endpoints). Frontend replaces the stub `profile/page.tsx` with a full settings page calling the new API via `apiFetch`. No new DB tables — uses existing `users` and `user_api_keys` per `db-schema-spec.md §1–2`.

**Spec refs:** `docs/api-key-encryption-spec.md` (encryption, masking, logging scrub), `docs/db-schema-spec.md §1–2` (columns/types), `docs/prd.md §2` (UI scope). **Always cross-reference column names against the schema spec.**

**Tech Stack:** Python 3.11+, FastAPI, `cryptography>=42.0.0` (AESGCM + HKDF), Supabase Python client (sync — all calls via `run_in_executor`), Next.js 14 App Router, TypeScript strict, shadcn/ui + Tailwind.

**Tier:** Standard. No Gilfoyle review (ticket: Fast-adjacent). No Jìan scaffolding exists — write tests alongside implementation. Hand off to Jìan (Sprint 3).

---

## Task 1: Encryption Utilities

**Files:**
- Create: `packages/api/app/services/encryption.py`
- Test: `packages/api/tests/test_profile.py` (class `TestEncryptionUtils`)

**Step 1:** Write failing tests for `load_master_key`, `derive_user_key`, `encrypt_api_key`/`decrypt_api_key` round-trip, and `mask_api_key`. Use `TEST_ENCRYPTION_KEY = base64.b64encode(os.urandom(32)).decode()` injected via `os.environ.setdefault` at module top (matches conftest pattern).

**Step 2:** Run `cd packages/api && python -m pytest tests/test_profile.py::TestEncryptionUtils -v` — expect ImportError/NameError.

**Step 3:** Implement `encryption.py` following the exact code in `docs/api-key-encryption-spec.md §1–4`:
- `load_master_key()` — reads `API_KEY_ENCRYPTION_KEY` from env, base64-decodes, asserts 32 bytes
- `derive_user_key(master_key, user_id)` — HKDF-SHA256, `info=user_id.encode()`
- `encrypt_api_key(plaintext, master_key, user_id)` → `(ciphertext: bytes, nonce: bytes)`
- `decrypt_api_key(ciphertext, nonce, master_key, user_id)` → `str`
- `mask_api_key(key)` → `key[:7] + "..." + key[-4:]`, or `"***...***"` if `len < 12`

**Step 4:** Run tests — expect PASS.

**Step 5:** Commit: `feat: add AES-256-GCM encryption utilities for API key storage`

---

## Task 2: Log Scrub Middleware

**Files:**
- Create: `packages/api/app/middleware/__init__.py` (empty)
- Create: `packages/api/app/middleware/log_scrub.py`
- Test: `packages/api/tests/test_profile.py` (class `TestLogScrubMiddleware`)

**Step 1:** Write failing test — call `scrub_dict` with a payload containing `api_key`, `key_ciphertext`, `authorization`, a nested dict, and a safe field. Assert sensitive fields become `"[REDACTED]"`, safe field unchanged.

**Step 2:** Run test — expect NameError.

**Step 3:** Implement `log_scrub.py` following `docs/api-key-encryption-spec.md §5`:
- `SCRUB_PATTERNS` regex (copy from spec verbatim)
- `scrub_dict(d: dict) -> dict` — recursive, replaces matching keys
- `LogScrubMiddleware(BaseHTTPMiddleware)` — calls `scrub_dict` on request body (JSON only) before it hits the logger. Keep it lightweight: log scrubbing only, do not block the request.

**Step 4:** Run test — expect PASS.

**Step 5:** Commit: `feat: add log scrub middleware to redact sensitive fields`

---

## Task 3: Profile API Routes

**Files:**
- Create: `packages/api/app/api/routes/profile.py`
- Test: `packages/api/tests/test_profile.py` (class `TestProfileEndpoints`, class `TestApiKeyEndpoints`, class `TestDefaultModelEndpoint`)

**Step 1:** Write failing tests (mock Supabase via `unittest.mock.patch` + `MagicMock`). Test cases:

*Profile:*
- `GET /api/v1/profile` returns `{id, name, bio, default_model_id}` — no ciphertext/nonce in response
- `GET /api/v1/profile` with no DB row returns 404
- `PATCH /api/v1/profile` with bio > 1000 chars returns 400
- `PATCH /api/v1/profile` updates name + bio, returns updated profile

*API keys:*
- `GET /api/v1/profile/api-keys` returns list of `{provider, key_hint, validated_at}` — no ciphertext
- `POST /api/v1/profile/api-keys` with valid payload encrypts + stores, returns `{provider, key_hint}`
- `POST /api/v1/profile/api-keys` with invalid provider returns 422
- `DELETE /api/v1/profile/api-keys/anthropic` removes the row, returns 204
- `DELETE /api/v1/profile/api-keys/anthropic` when key doesn't exist returns 404

*Default model:*
- `PATCH /api/v1/profile/default-model` with valid `model_id` (admin-enabled generation model) updates user row
- `PATCH /api/v1/profile/default-model` with unknown model_id returns 404

**Step 2:** Run tests — expect failures.

**Step 3:** Implement `profile.py`. Key rules:
- `router = APIRouter(prefix="/api/v1/profile", tags=["profile"])`
- All Supabase calls wrapped in `run_in_executor` per `conventions.md § Supabase in Async Code`
- `GET /api/v1/profile`: select `id, name, bio, default_model_id` from `users` where `id = user_id`. Raise `NotFoundError` if no row.
- `PATCH /api/v1/profile`: Pydantic model `UpdateProfileRequest(name: str | None, bio: str | None)`. Validate `len(bio) <= 1000`. Update `users` set name/bio + `updated_at = now()`.
- `GET /api/v1/profile/api-keys`: select `provider, key_hint, validated_at` from `user_api_keys` where `user_id = user_id`. **Never select `key_ciphertext` or `key_nonce`.**
- `POST /api/v1/profile/api-keys`: Pydantic model `UpsertApiKeyRequest(provider: str, api_key: str)`. Validate `provider` in `{anthropic, openai, google, groq}`. Call `mask_api_key` → `key_hint`. Call `encrypt_api_key` → `(ciphertext, nonce)`. Upsert `user_api_keys` on `(user_id, provider)` conflict. Return `{provider, key_hint}`. Provider validation call is skipped in MVP (ticket scope).
- `DELETE /api/v1/profile/api-keys/{provider}`: Delete row. If no row deleted, raise `NotFoundError`.
- `PATCH /api/v1/profile/default-model`: Pydantic model `SetDefaultModelRequest(model_id: str)`. Verify `llm_models` row exists and `enabled=True` and `category='generation'`. Update `users.default_model_id`. Raise `NotFoundError` if model not found/disabled.
- **Column names must exactly match `db-schema-spec.md`**: `key_ciphertext`, `key_nonce`, `key_hint`, `validated_at`, `default_model_id`.
- **Write operations**: raise or log-and-raise on errors — never return `None`/`[]`/`False` in `try/except`.

**Step 4:** Run tests — expect PASS.

**Step 5:** Commit: `feat: add profile API routes (profile, api-keys, default-model)`

---

## Task 4: Wire Into App

**Files:**
- Modify: `packages/api/app/main.py`

**Step 1:** No new test needed — existing `test_auth.py` confirms the app boots. After changes, run the full suite.

**Step 2:** In `main.py`:
```python
from app.api.routes.profile import router as profile_router
from app.middleware.log_scrub import LogScrubMiddleware

app.add_middleware(LogScrubMiddleware)
app.include_router(profile_router)
```
Add middleware before `CORSMiddleware` (middleware stack is LIFO — log scrub fires last on response, first on request).

**Step 3:** Run `cd packages/api && python -m pytest tests/ -v` — all tests must pass.

**Step 4:** Commit: `feat: register profile router and log scrub middleware`

---

## Task 5: Frontend — Types + Profile Page

**Files:**
- Modify: `packages/web/lib/types/models.ts`
- Modify: `packages/web/app/(app)/profile/page.tsx`

**Step 1:** Add types to `models.ts`:
```ts
export type ApiKeyProvider = "anthropic" | "openai" | "google" | "groq";

export interface UserProfile {
  id: string;
  name: string;
  bio: string | null;
  default_model_id: string | null;
}

export interface ApiKeyEntry {
  provider: ApiKeyProvider;
  key_hint: string;
  validated_at: string | null;
}
```

**Step 2:** Replace `profile/page.tsx` stub with a full `"use client"` page:

*Structure (top to bottom):*
1. `useEffect` → `GET /api/v1/profile` + `GET /api/v1/profile/api-keys` + `GET /api/v1/admin/models` (for model selector) on mount
2. **Name field:** `<Input>` bound to `name`, save on blur via `PATCH /api/v1/profile`
3. **Bio textarea:** `<Textarea>` with char count display `(n / 1000)`. Save on blur. Grey out count when over soft limit (500), red when at hard limit (1000).
4. **API Keys section:** One row per provider (`anthropic`, `openai`, `google`, `groq`). Each row: provider label + masked hint (if set) + inline input (toggled on click of "Update") + "Remove" button (calls `DELETE`). Inline input: on submit calls `POST /api/v1/profile/api-keys`.
5. **Default model selector:** `<select>` of admin-enabled `generation` models. Models without a matching configured API key provider are `disabled` with `title="Add an API key to enable"`. On change calls `PATCH /api/v1/profile/default-model`.
6. **Linked Upload button:** Disabled (`disabled` attr + tooltip "Add an API key to enable auto-fill") when no API keys configured. No backend wiring in Sprint 2 — UI only.

*Rules:*
- No `any` without comment. All API calls via `apiFetch` from `lib/api.ts`. Parse errors via `parseApiError`.
- `snake_case` from API → `camelCase` in local state (manual mapping — no automatic transform).
- Show toast on save errors using shadcn `useToast`.

**Step 3:** Build check: `cd packages/web && ./node_modules/.bin/next build 2>&1 | tail -20` — expect no TypeScript errors.

**Step 4:** Commit: `feat: implement user profile settings page with API keys and model selector`

---

## Done-When

- [ ] `GET/PATCH /api/v1/profile` works; bio capped at 1000 chars
- [ ] API keys add/remove/list: ciphertext never returned; key_hint stored at write time
- [ ] Default model selector validates model exists, is enabled, is category=generation
- [ ] Log scrub middleware redacts `api_key`, `key_ciphertext`, `key_nonce`, `authorization` fields
- [ ] All Python tests pass (`pytest tests/ -v`)
- [ ] Frontend builds without TypeScript errors
- [ ] Profile page renders name, bio, 4 API key rows, model dropdown, Linked Upload button

## Test Strategy

- **Encryption:** round-trip encrypt→decrypt, mask edge cases (short key, exactly 12 chars), wrong master key raises
- **Log scrub:** nested dict redaction, non-JSON body passthrough, safe fields unchanged
- **Profile endpoints:** mock Supabase; test 404 on missing user, 400 on bio overflow, 422 on bad provider
- **API keys:** verify ciphertext never in response; verify upsert path; verify 404 on delete-not-found
- **Default model:** verify non-generation or disabled model returns 404
- All tests use `client` fixture from `conftest.py` (dependency override for auth)
