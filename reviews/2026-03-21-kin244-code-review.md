# Code Review — KIN-244
**Ticket:** [Dinesh] Port frontend scaffold from FounderPanel (Next.js 14 App Router, shadcn/ui, admin shell)
**Reviewer:** Gilfoyle
**Date:** 2026-03-21
**Round:** 1
**Verdict:** Changes Requested — 2 Critical, 3 Important

---

## Summary

The scaffold is structurally sound. Next.js 14 App Router wiring, shadcn/ui component registration, lib/api.ts, and the SSE proxy route are all well-executed ports. The intentional divergences from FounderPanel (always-dark `:root`, `/api/v1/` versioning, named exports) are correct and consistent. Dark theme token coverage is complete. 16 tests pass.

Two critical issues must be fixed before approval: the `cookies()` import in the Edge runtime SSE route will throw at runtime in production (Edge cannot use Next.js server-only APIs), and the admin layout performs a full data fetch (`/api/v1/admin/users`) to determine admin status, which is a performance and correctness anti-pattern — it should call a dedicated `/api/v1/admin/me` or check a token claim, not side-load user data. Three important issues are also flagged.

---

## Findings

### CRITICAL

#### C1 — `cookies()` from `next/headers` used in Edge runtime
**File:** `app/api/stream/route.ts` lines 18–23
**Problem:** `cookies()` from `next/headers` is a Node.js-only API. The route is declared `export const runtime = "edge"`, which runs in the V8 isolate — `next/headers` is explicitly unsupported there. The import is wrapped in a try/catch so it silently falls back, but the correct behavior is to never import it in an Edge route at all. It will throw an unhandled runtime error in production Edge deployments (Vercel Edge, Cloudflare). The fallback chain (`accessToken || cookieTokenFromReq || cookieTokenFromNextHeaders`) will still work in local dev (Node.js), masking the bug until deploy.

Additionally, `(req as any)?.cookies?.get?.(...)` is a type-unsafe reach around the NextRequest API. `NextRequest.cookies` is a `RequestCookies` object with a proper `.get()` method — no `any` cast needed.

**Fix:**
- Remove the `import { cookies } from "next/headers"` and the `cookieTokenFromNextHeaders` path entirely.
- Use `req.cookies.get("sb-access-token")?.value` via the typed `NextRequest` API directly (already available on the request object).
- The fallback chain becomes: `accessToken || req.cookies.get("sb-access-token")?.value`.

---

#### C2 — Admin check uses a data endpoint as an access gate
**File:** `app/admin/layout.tsx` lines 49–66
**Problem:** The admin check calls `GET /api/v1/admin/users` and uses HTTP 200 to mean "is admin" and HTTP 403 to mean "not admin." This is wrong for three reasons:
1. It fetches a potentially large user list just to check a permission. If the user list grows, this is wasteful on every admin page navigation.
2. The endpoint contract is conflated: a data endpoint is doing double duty as an ACL gate. If the endpoint changes response shape, format, or pagination behavior in the future, the auth check silently breaks.
3. Any non-200/non-403 response (500, network timeout, etc.) redirects to `/projects` — legitimate admins get locked out on backend errors.

The correct pattern is a dedicated lightweight endpoint (e.g., `GET /api/v1/admin/me` → `{is_admin: true}`) or, better, a JWT claim check on the client (`session.user.app_metadata.role === "admin"`). This doesn't require a backend round-trip at all if the claim is set at auth time.

**Fix:** Replace the `/api/v1/admin/users` fetch with a call to a dedicated `GET /api/v1/admin/me` endpoint (to be created in the backend scaffold ticket). In the interim, extract the admin flag from `session.user.app_metadata` if Supabase custom claims are being used. Either way, do not use a data endpoint as an auth gate.

Note: this is a blocker because it bakes a bad API contract into the layout before the backend is built. If the backend scaffolds to this pattern, fixing it later requires coordinated frontend+backend change.

---

### IMPORTANT

#### I1 — `tailwind.config.ts` has `darkMode: ["class"]` but `:root` IS the dark theme
**File:** `tailwind.config.ts` line 4
**Problem:** `darkMode: ["class"]` instructs Tailwind to scope dark variants under `.dark` class. The root layout applies `<html className="dark">` (correct), so this technically works. However, the config says dark mode is class-toggled while the intent is always-dark. Any `dark:` utility class in components will only activate when `.dark` is on the `<html>` element — which is always the case, so the behavior is correct, but the setup is misleading and will confuse contributors who try to add light-mode styles via `dark:` utilities.

More importantly: `darkMode: ["class"]` combined with `:root` defining dark values means that if `.dark` is ever removed from `<html>` (e.g., a future light-mode attempt), everything breaks visually. The always-dark intent should be enforced in config.

**Fix:** Change to `darkMode: "media"` and remove the `.dark` class from the root layout — relying on CSS media query `@media (prefers-color-scheme: dark)` — OR keep `darkMode: ["class"]` but add a comment documenting that `.dark` is permanently applied and light mode is not supported in MVP. The latter is lower risk for now. Either way, document the choice.

---

#### I2 — `resolveApiBaseUrl()` called twice per request in `apiFetch`
**File:** `lib/api.ts` lines 31 and 64
**Problem:** `API_BASE_URL` is computed once at module init (line 31) and stored as a constant. But `apiFetch` calls `resolveApiBaseUrl()` again on line 64 for every request. This means the function is evaluated twice: once at import time and once per call. In practice this is harmless (the result is deterministic), but it's inconsistent — the constant `API_BASE_URL` is exported but not used internally, which is confusing. `createStreamEventSource` routes through `/api/stream` (the proxy) so it doesn't use either — that's correct.

**Fix:** Replace `resolveApiBaseUrl()` on line 64 with `API_BASE_URL`. The module-level constant is the right single source of truth.

---

#### I3 — `useEffect` dependency array in admin layout includes `loading` — causes double-fire
**File:** `app/admin/layout.tsx` line 84
**Problem:** `useEffect(() => { ... }, [router, loading])` — `loading` is in the dependency array. The effect sets `loading` to `false` in its `finally` block, which triggers a re-render, which re-runs the effect (because `loading` changed), which fires `checkAdminAccess()` a second time. The `mounted` flag prevents the second call from actually doing anything harmful, but the effect fires twice on every mount and the `setTimeout` safety timeout is created and cancelled twice. This is a React effect dependency bug.

**Fix:** Remove `loading` from the dependency array. The effect should depend only on `[router]`. The `loading` state is internal to the effect's lifecycle, not a trigger for re-running it.

---

### NOTES (non-blocking)

**N1 — supabaseClient graceful fallback is correct but the placeholder URL is fragile**
`lib/supabaseClient.ts` falls back to `"http://localhost"` and `"placeholder"` as URL/key. This prevents build-time throws, which is the right behavior. Worth noting that `createClient("http://localhost", "placeholder")` will still succeed and return a client — any actual auth call will fail silently. If a future SSR path calls `supabase.auth.getSession()` server-side without env vars, it will return `null` session (acceptable) rather than throwing. The behavior is correct; document it.

**N2 — Middleware does not protect `/admin/*`**
The middleware matcher `/((?!login|api|_next/static|_next/image|favicon.ico).*)` will match `/admin/...` routes and enforce session presence — correct. The admin-specific role check happens in the layout client component. This two-layer approach (middleware = authenticated, layout = admin role) is acceptable for MVP, but note that a user who is authenticated but not admin will briefly see the "Checking admin access…" spinner before being redirected. This is a UX note, not a defect for this ticket.

**N3 — `@testing-library/react` v16 + `vitest` v4 — check compatibility**
`package.json` has `@testing-library/react: ^16.3.1` and `vitest: ^4.0.16`. These are recent major versions. Tests pass at 16/16, so this is not a blocker, but pin these to exact versions in `pnpm-lock.yaml` to avoid future CI drift. The lockfile is present, so this is already handled — just noting it.

**N4 — SSE proxy does not validate that `conversation_id` and `content` are present**
`app/api/stream/route.ts` forwards all query params to the backend without validating required params. If a caller omits `conversation_id`, the backend will receive a malformed request and return a 4xx. The proxy currently returns whatever the backend returns with its original status code — that behavior is acceptable for a scaffold, but will need input validation before the chat feature is wired.

---

## Test Quality Assessment

The 16 tests are structurally appropriate for a scaffold. They cover:
- Middleware matcher shape (structural, not behavioral — acceptable given Edge runtime constraints)
- SSE route exports (structural — acceptable)
- `apiFetch` auth throw on missing session (behavioral — good)
- `parseApiError` FastAPI error shape extraction (behavioral — good)
- `AdminLayout` NAV_ITEMS shape (structural — acceptable but the test is testing a local constant, not the actual component)
- `AppSidebar` renders and active-state highlighting (behavioral — good)

**Gap:** There are no tests for `resolveApiBaseUrl` with a mocked `NEXT_PUBLIC_API_BASE_URL` env variable. The current test only covers the default case. This is Important-level for the next round.

---

## Action Items for Dinesh

**Must fix before re-review:**

1. **[C1]** `app/api/stream/route.ts` — Remove `import { cookies } from "next/headers"` and `cookieTokenFromNextHeaders`. Replace `(req as any)?.cookies?.get?.(...)` with `req.cookies.get("sb-access-token")?.value`. Remove the `any` cast.

2. **[C2]** `app/admin/layout.tsx` — Replace the `/api/v1/admin/users` admin gate with either: (a) `session.user.app_metadata.role === "admin"` claim check (no round-trip), or (b) a call to `GET /api/v1/admin/me` when that endpoint is built. Do not use a data endpoint as an auth gate. Flag if the Supabase custom claims path isn't confirmed for this project.

**Should fix in same PR:**

3. **[I1]** `tailwind.config.ts` — Add a comment documenting that `darkMode: ["class"]` is intentional, `.dark` is permanently applied on `<html>`, and light mode is not supported in MVP.

4. **[I2]** `lib/api.ts` line 64 — Replace `resolveApiBaseUrl()` call with `API_BASE_URL` constant.

5. **[I3]** `app/admin/layout.tsx` line 84 — Remove `loading` from the `useEffect` dependency array.
