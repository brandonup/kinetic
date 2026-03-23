# Code Review — KIN-267: Sprint 1 Auth Service + Frontend Scaffold

**Reviewer:** Gilfoyle
**Date:** 2026-03-22
**Tickets:** KIN-252 (Auth service), KIN-253 (Frontend scaffold)
**Verdict:** Architecture approved. 0 Critical, 2 Important.

---

## Auth Service (KIN-252)

### Files Reviewed

| File | Verdict |
|---|---|
| `api/app/auth/deps.py` | Pass |
| `api/app/auth/supabase_jwt.py` | Pass |
| `api/app/core/config.py` | Pass |
| `api/app/core/errors.py` | Pass |
| `api/app/main.py` | Pass |
| `api/app/middleware/log_scrub.py` | Important (see #1) |
| `api/app/services/encryption.py` | Pass |

### Findings

**#1 — Important — `log_scrub.py:49–52` — `scrub_dict` crashes on list bodies**

`json.loads()` can return a list for endpoints that accept JSON arrays. `scrub_dict(body_dict)` calls `.items()` on the result, which throws `AttributeError` for lists. The exception is caught by the bare `except: pass`, so requests proceed — but list-shaped request bodies are never scrubbed in logs.

**Fix:** Add a type check before calling `scrub_dict`:

```python
if isinstance(body_dict, dict):
    scrubbed = scrub_dict(body_dict)
elif isinstance(body_dict, list):
    scrubbed = [scrub_dict(item) if isinstance(item, dict) else item for item in body_dict]
```

**Impact:** Low — current Kinetic endpoints use object bodies, not arrays. But the middleware is global, so future endpoints may hit this.

### Architecture Notes (non-blocking)

- **JWT verification:** HS256 primary + JWKS fallback is correct. Audience verification enabled. Production-grade.
- **`LOCAL_DEV_AUTH_BYPASS`:** Properly gated behind settings flag with UUID validation on the debug header. Acceptable pattern — never `True` in production per `config.py`.
- **`get_current_user_from_token`:** SSE query-param auth is necessary (EventSource limitation). Token stripped before backend forwarding in the SSE proxy. Documented and correct.
- **Admin role check:** Queries `public.users.role` via service-role client. `run_in_executor` wraps the sync Supabase call correctly.
- **AES-256-GCM encryption:** HKDF per-user key derivation, 12-byte random nonce, no associated data. Clean implementation. `mask_api_key` returns safe display hints.
- **CORS-aware error handlers:** Error responses include CORS headers. Prevents opaque network errors on the frontend. Well done.
- **Production validation:** `validate_settings` catches localhost in CORS_ORIGINS and ADMIN_PORTAL_URL in production. Good safety net.

---

## Frontend Scaffold (KIN-253)

### Files Reviewed

| File | Verdict |
|---|---|
| `web/middleware.ts` | Pass |
| `web/app/login/page.tsx` | Pass |
| `web/app/auth/callback/route.ts` | Pass |
| `web/app/layout.tsx` | Pass |
| `web/app/(app)/layout.tsx` | Pass |
| `web/app/admin/layout.tsx` | Pass |
| `web/components/AppSidebar.tsx` | Pass |
| `web/tailwind.config.ts` | Pass |
| `web/lib/api.ts` | Important (see #2) |
| `web/lib/supabaseClient.ts` | Pass |
| `web/app/api/stream/route.ts` | Pass |

### Findings

**#2 — Important — `api.ts:113` / `stream/route.ts` — SSE passes message `content` in URL query param**

`createStreamEventSource` puts the user's message in a query parameter (`content`). URLs are capped at ~2000 characters in many browsers and proxies. Long messages will silently fail or truncate. The SSE proxy then forwards all params to the backend.

**Fix (deferred — chat endpoint doesn't exist yet):** When the chat SSE endpoint ships, switch to a two-step pattern: (1) POST message body to `/api/v1/chat/send` → returns a `stream_id`, (2) EventSource subscribes to `/api/stream?stream_id=X`. This separates the payload from the connection.

**Impact:** Medium — this is the scaffold, and no chat endpoint exists yet. Flag for Sprint 3 when Big Head builds the generation engine.

### Architecture Notes (non-blocking)

- **App Router structure:** Correct — route groups `(app)` for authenticated, `admin` for admin, `login` unauthenticated. No Pages Router patterns found.
- **Open redirect prevention (auth callback):** `rawRedirect.startsWith("/") && !rawRedirect.startsWith("//")` correctly rejects absolute and protocol-relative URLs.
- **Admin guard:** Double-layered — middleware checks `app_metadata.role` server-side, admin layout rechecks client-side. Cannot be spoofed (app_metadata is server-set by Supabase).
- **Dark theme:** `<html class="dark">` hardcoded in root layout. `darkMode: ["class"]` in Tailwind config. HSL CSS variables with custom "teak" palette. Correct per spec.
- **Company switcher:** Loads companies from API, persists active selection in local state. Outside-click dismissal. Clean UX.
- **`supabaseClient.ts` fallback:** `supabaseUrl || "http://localhost"` prevents SSR crashes. Client-side `console.error` warns if env vars are missing. Acceptable for MVP.
- **SSE proxy:** Edge runtime, strips `access_token` from backend params, sends immediate ping to keep connection alive. Correct pattern.

---

## Summary

Clean, well-structured Sprint 1 implementation. Auth is production-grade (JWT, AES-256-GCM encryption, CORS-aware errors). Frontend follows App Router conventions, admin guard is double-layered, and the dark/teak theme is properly configured. The two Important findings are both edge cases with low immediate impact — #1 is a trivial fix, #2 is a design note for Sprint 3.
