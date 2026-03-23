# Auth Service Port (KIN-252) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Port the auth service from FounderPanel into Kinetic — backend JWT verification + FastAPI deps, DB migration for `handle_new_user` trigger, and frontend magic link + Google OAuth login UI.

**Architecture:** Supabase Auth owns `auth.users` (magic link + Google OAuth — no passwords). A DB trigger (`handle_new_user`) creates a row in `public.users` on every `auth.users` INSERT. FastAPI guards every protected route via `get_current_user` (JWT → `sub` → user id); `require_admin` checks `public.users.role`. Frontend uses `@supabase/auth-helpers-nextjs` for session management; the middleware (already wired) redirects unauthenticated users to `/login`.

**Tech Stack:** Python 3.11+, FastAPI, `python-jose`/`PyJWT`, Supabase Python client, pydantic-settings | Next.js 14 App Router, TypeScript strict, `@supabase/supabase-js`, `@supabase/auth-helpers-nextjs`, shadcn/ui, vitest

**Jìan scaffolding:** `packages/api/tests/test_auth.py` — all tests skipped. Job is to build the implementation that makes these tests pass, then activate them by removing `@pytest.mark.skip`.

**Source to port from:** `/Users/brandonupchuch/Projects/founder_panel/backend/app/auth/` (supabase_jwt.py, deps.py) — adapt for Kinetic (no RegistrationRequest, no UserPermission model; role comes from `public.users.role`).

**Schema ref:** `docs/db-schema-spec.md` §1 (`users`), §2 (`user_api_keys`) — canonical source.

---

## Spec-Section Coverage Matrix

| Spec §Section | Task(s) in plan | Status |
|---|---|---|
| §1 `users` table (id, name, role, bio, default_model_id, active_company_id) | Task 1: DB migration | Covered |
| §1 RLS policies (SELECT/UPDATE own row, admin all rows; INSERT via trigger only) | Task 1: DB migration | Covered |
| §2 `user_api_keys` table | Out of scope for this ticket (KIN-252 = auth only) | N/A |
| Enums: `user_role` | Task 1: DB migration | Covered |
| Auth: JWT verification (SupabaseJWTVerifier) | Task 2: Backend auth module | Covered |
| Auth: `get_current_user` dep (header + query param) | Task 2: Backend auth module | Covered |
| Auth: `require_admin` dep | Task 2: Backend auth module | Covered |
| Auth: `require_active_user` dep | Task 2: Backend auth module | Covered |
| Auth: `/api/v1/users/me` endpoint | Task 3: Users router | Covered |
| Frontend: magic link login | Task 4: Login page | Covered |
| Frontend: Google OAuth login | Task 4: Login page | Covered |
| Frontend: auth callback handler | Task 5: Callback route | Covered |
| Backend: FastAPI app wiring (CORS, exception handlers) | Task 6: main.py + config | Covered |
| Test activation (remove skip decorators) | Task 7: Activate tests | Covered |

---

## Task 1: DB Migration — `users` table + `handle_new_user` trigger

**Files:**
- Create: `packages/api/migrations/001_create_users.sql`

**What to write:**

```sql
-- Enum
CREATE TYPE user_role AS ENUM ('admin', 'user');

-- users table (extends auth.users)
CREATE TABLE public.users (
  id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  name text NOT NULL,
  bio text CHECK (char_length(bio) <= 1000),
  role user_role NOT NULL DEFAULT 'user',
  default_model_id uuid REFERENCES public.llm_models(id) ON DELETE SET NULL,
  active_company_id uuid REFERENCES public.companies(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- updated_at trigger
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON public.users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- handle_new_user: fires on auth.users INSERT → creates public.users row
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (id, name, role)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'name', split_part(NEW.email, '@', 1)),
    'user'
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- RLS
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_select_own_or_admin"
  ON public.users FOR SELECT
  USING (auth.uid() = id OR EXISTS (
    SELECT 1 FROM public.users u WHERE u.id = auth.uid() AND u.role = 'admin'
  ));

CREATE POLICY "users_update_own_or_admin"
  ON public.users FOR UPDATE
  USING (auth.uid() = id OR EXISTS (
    SELECT 1 FROM public.users u WHERE u.id = auth.uid() AND u.role = 'admin'
  ));

-- INSERT: trigger only (no direct insert policy for authenticated users)
CREATE POLICY "users_insert_deny"
  ON public.users FOR INSERT
  WITH CHECK (false);

-- DELETE: denied
CREATE POLICY "users_delete_deny"
  ON public.users FOR DELETE
  USING (false);
```

**Verify:** SQL is syntactically valid; every column name/type/constraint matches `docs/db-schema-spec.md §1` exactly. `default_model_id` and `active_company_id` FK targets (`llm_models`, `companies`) are deferred FKs — only add if those tables exist; otherwise drop those two FK constraints for now and note it.

---

## Task 2: Backend — Auth Module

**Files:**
- Create: `packages/api/app/__init__.py`
- Create: `packages/api/app/core/__init__.py`
- Create: `packages/api/app/core/config.py`
- Create: `packages/api/app/core/errors.py`
- Create: `packages/api/app/auth/__init__.py`
- Create: `packages/api/app/auth/supabase_jwt.py`
- Create: `packages/api/app/auth/deps.py`

**2a — `core/config.py`**

Port from FounderPanel's `core/config.py`. Strip all FounderPanel-specific settings. Keep:
- `APP_NAME = "Kinetic"`, `DEBUG`, `ENVIRONMENT`
- `CORS_ORIGINS` with comma-split validator
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`
- `LOCAL_DEV_AUTH_BYPASS: bool = False`
- `model_config` pointing to `backend/.env` relative to the config file

Do not include Qdrant, LLM, RAG, or debate settings — those belong to other tickets.

**2b — `core/errors.py`**

Port verbatim from FounderPanel. All exception classes (`AppException`, `AuthenticationError`, `AuthorizationError`, `NotFoundError`, `ValidationError`), `error_response()`, and `add_exception_handlers()`.

**2c — `auth/supabase_jwt.py`**

Port verbatim from FounderPanel — `SupabaseJWTVerifier`, `get_jwt_verifier()`. No changes needed.

**2d — `auth/deps.py`**

Port from FounderPanel's `deps.py` but adapt:
- Keep `CurrentUser`, `get_current_user`, `get_current_user_from_token`
- Replace `require_active_user` and `require_admin`: instead of hitting a `UserPermission` SQLAlchemy model, hit `public.users` via Supabase client:

```python
async def require_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: supabase_admin_client()
            .table("users")
            .select("role")
            .eq("id", current_user.user_id)
            .single()
            .execute()
    )
    if not result.data or result.data.get("role") != "admin":
        raise AuthorizationError("Admin access required")
    return current_user
```

- Add `supabase_admin_client()` helper at top of file (uses `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`).
- `require_active_user`: Kinetic has no suspension logic in MVP — this is a passthrough to `get_current_user`. Keep the function signature for interface compatibility but just return `current_user`.
- Remove all SQLAlchemy imports (`Session`, `get_db`, models). No SQLAlchemy in this module.
- All Supabase calls inside `async def` use `run_in_executor` per `conventions.md § Supabase in Async Code`.

**Verify before moving on:** No `await` on sync Supabase calls. No SQLAlchemy imports. All column names match `docs/db-schema-spec.md §1`.

---

## Task 3: Backend — Users Router + App Entry Point (stub)

**Files:**
- Create: `packages/api/app/api/__init__.py`
- Create: `packages/api/app/api/routes/__init__.py`
- Create: `packages/api/app/api/routes/users.py`
- Create: `packages/api/app/main.py`

**3a — `routes/users.py`**

Single endpoint to unblock tests:

```python
from fastapi import APIRouter, Depends
from app.auth.deps import get_current_user, CurrentUser

router = APIRouter(prefix="/api/v1/users", tags=["users"])

@router.get("/me")
async def get_me(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    return {"id": current_user.user_id}
```

**3b — `main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.errors import add_exception_handlers
from app.api.routes.users import router as users_router

app = FastAPI(title=settings.APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

add_exception_handlers(app)
app.include_router(users_router)
```

---

## Task 4: Frontend — Login Page (magic link + Google OAuth)

**Files:**
- Modify: `packages/web/app/login/page.tsx`
- Create: `packages/web/app/__tests__/login/page.test.tsx`

**4a — Login page**

Replace the scaffold placeholder with a real login page. Kinetic has no passwords — magic link only, plus Google OAuth. Use shadcn `Card`, `Input`, `Button`, `Label` (already in the web package). Reference the FounderPanel login page structure but replace `signInWithPassword` with:

- Magic link tab: `supabase.auth.signInWithOtp({ email, options: { emailRedirectTo: \`\${origin}/auth/callback\` } })`
- Google OAuth button: `supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: \`\${origin}/auth/callback\` } })`

Show a "check your email" confirmation state after magic link send (don't redirect). Use `useToast` for errors. Dark theme — no gradient backgrounds (Kinetic is dark-only, `bg-background` not `bg-gradient-to-br`).

**4b — Login page test**

Write a vitest test at `app/__tests__/login/page.test.tsx`. Test that:
- The email input renders
- The "Send magic link" button renders
- The "Continue with Google" button renders

Use `@testing-library/react` render + `screen.getBy*`. Mock `@/lib/supabaseClient` to prevent real Supabase calls.

---

## Task 5: Frontend — Auth Callback Route

**Files:**
- Create: `packages/web/app/auth/callback/route.ts`
- Create: `packages/web/app/__tests__/auth/callback.test.ts`

**5a — Callback route**

Next.js Route Handler (not a page). Exchanges the auth `code` for a session using `@supabase/auth-helpers-nextjs`:

```typescript
import { createRouteHandlerClient } from "@supabase/auth-helpers-nextjs";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  const requestUrl = new URL(request.url);
  const code = requestUrl.searchParams.get("code");

  if (code) {
    const supabase = createRouteHandlerClient({ cookies });
    await supabase.auth.exchangeCodeForSession(code);
  }

  return NextResponse.redirect(requestUrl.origin);
}
```

**5b — Callback test**

Test that `GET` returns a redirect when given a `code`. Mock `createRouteHandlerClient` and `cookies`. Assert redirect URL is the request origin.

---

## Task 6: Activate and Fix Jìan Test Scaffolding

**Files:**
- Modify: `packages/api/tests/conftest.py`
- Modify: `packages/api/tests/test_auth.py`

**6a — Activate conftest fixtures**

Uncomment the `db_session` and `client` fixtures. Update imports to match Kinetic's module structure (`app.main`, `app.auth.deps`). The `db_session` fixture should use the Supabase client (not SQLAlchemy) for seeding — or override `get_current_user` directly to avoid DB calls in unit tests.

Preferred approach for unit tests: override `get_current_user` dependency in the test client rather than seeding a real DB. In `conftest.py`:

```python
@pytest.fixture
def client(valid_user_token: str):
    from app.main import app
    from app.auth.deps import get_current_user, CurrentUser
    from fastapi.testclient import TestClient

    async def override_get_current_user():
        return CurrentUser(user_id=TEST_USER_ID)

    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

For role tests (`require_admin`), add a separate fixture that overrides with an admin user.

**6b — Activate test cases**

Remove all `@pytest.mark.skip` decorators from `test_auth.py`. Implement the `raise NotImplementedError` bodies per the docstrings:

- `TestRegistration`: assert `GET /api/v1/users/me` returns 200 with the correct `id` when the user exists in `public.users`.
- `TestMagicLink.test_expired_magic_link_is_rejected`: pass `expired_token` as Bearer, assert 401.
- `TestMagicLink.test_invalid_tampered_magic_link_is_rejected`: pass `tampered_token`, assert 401.
- `TestSession.test_protected_route_rejects_unauthenticated_request`: no Authorization header, assert 401.
- `TestSession.test_protected_route_accepts_valid_jwt`: `valid_user_token` Bearer, assert 200, body has `id == TEST_USER_ID`.
- `TestRoleEnforcement.test_admin_endpoint_rejects_user_role`: regular user hits admin endpoint, assert 403.
- `TestRoleEnforcement.test_admin_endpoint_accepts_admin_role`: admin user, assert 200.
- OAuth callback tests: mock Supabase exchange; assert session returned and no crash.

Run after each test activation: `pytest packages/api/tests/test_auth.py -v`

---

## Task 7: Add `pyproject.toml` / `requirements.txt`

**Files:**
- Create: `packages/api/pyproject.toml`
- Create: `packages/api/requirements.txt`

Minimum deps to run the auth module and tests:

```
fastapi>=0.109
uvicorn[standard]>=0.27
pydantic>=2.5
pydantic-settings>=2.1
PyJWT>=2.8
httpx>=0.26           # for JWKS fetch in supabase_jwt
supabase>=2.3         # for admin client in deps
python-jose[cryptography]>=3.3
pytest>=7.4
pytest-asyncio>=0.23
httpx                 # TestClient transport
```

---

## Done-When Criteria

- `packages/api/app/auth/supabase_jwt.py` exists and exports `SupabaseJWTVerifier`, `get_jwt_verifier`
- `packages/api/app/auth/deps.py` exports `get_current_user`, `get_current_user_from_token`, `require_active_user`, `require_admin`, `CurrentUser`
- `packages/api/app/api/routes/users.py` has `GET /api/v1/users/me`
- `packages/api/app/main.py` creates the FastAPI app with CORS + exception handlers
- `packages/api/migrations/001_create_users.sql` creates `users` table, enums, trigger, RLS matching §1 of schema spec exactly
- All `@pytest.mark.skip` removed from `test_auth.py`; `pytest packages/api/tests/test_auth.py -v` passes ≥80% of cases
- `packages/web/app/login/page.tsx` renders magic link form + Google OAuth button
- `packages/web/app/auth/callback/route.ts` exists and exchanges code for session
- `packages/web` vitest passes: `./node_modules/.bin/vitest run`

---

## Pre-Code-Review Self-Check (Mandatory — `dinesh.md` Hard Gate)

Before moving to Code Review, verify every item:

1. Every table/column name in deps.py matches `docs/db-schema-spec.md §1` exactly (`users`, `role`, not `permissions` or `user_role_column`)
2. All Supabase calls in `async def` use `run_in_executor` — re-check `require_admin` and any future `require_active_user` that hits DB
3. `createServerClient()` / `createRouteHandlerClient()` receives cookies for RLS scoping
4. No snake_case/camelCase mismatches crossing the Python↔TS boundary (N/A for auth, but verify `/api/v1/users/me` response key is `id`)
5. Test count and command: `pytest packages/api/tests/test_auth.py -v` — include pass count in handoff comment
6. No `try/except` that returns `None`/`False` on Supabase write in deps
7. All writes scoped by user id (N/A — auth module is read-only on `public.users`)
8. Re-verify no `await` on sync Supabase calls
9. Migration column names/types/constraints verified against schema spec §1
