# Code Review — KIN-253: Frontend scaffold (Next.js App Router, shadcn, admin shell)

**Reviewer:** Gilfoyle
**Date:** 2026-03-22
**Round:** 1
**Verdict:** CHANGES_REQUESTED — 1 Critical, 2 Important

---

## Summary

Solid scaffold for a first sprint ticket. Architecture is correct: route groups for (app) vs admin, edge middleware for auth, JWT claim for admin ACL, dark-only theme with locked CSS custom properties. Most of the code is clean and idiomatic. Three issues need fixing before approval — one is a security concern.

---

## Findings

### Critical

---

#### C-1 — `middleware.ts`: Deprecated `@supabase/auth-helpers-nextjs` used on edge runtime; session may not refresh

**File:** `middleware.ts`
**Severity:** Critical
**Category:** async-supabase

**Problem:**
`createMiddlewareClient` from `@supabase/auth-helpers-nextjs` is the old SSR helper package that predates Supabase's dedicated SSR package. The package was deprecated in favor of `@supabase/ssr`. More critically, `createMiddlewareClient` does **not** call `supabase.auth.getSession()` in a way that refreshes expired tokens at the edge — it reads from the incoming request cookie but may not write a refreshed cookie back to the response reliably across all Next.js 14 edge runtime versions. This can produce a silent auth failure: user has a stale JWT, middleware reads an apparently valid session from cookie, passes the request through, but the subsequent RSC or API call rejects with 401 because the actual token is expired.

The pattern is also documented as broken in the Supabase Next.js migration guide: `auth-helpers-nextjs` middleware does not guarantee the PKCE code exchange flows correctly through the edge.

**Fix:**
Replace `@supabase/auth-helpers-nextjs` with `@supabase/ssr` across the whole package (middleware, route handler, and any server components added later). Middleware pattern becomes:

```ts
import { createServerClient } from "@supabase/ssr";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export async function middleware(req: NextRequest) {
  let res = NextResponse.next({ request: { headers: req.headers } });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() { return req.cookies.getAll(); },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) => {
            req.cookies.set(name, value);
            res = NextResponse.next({ request: { headers: req.headers } });
            res.cookies.set(name, value, options);
          });
        },
      },
    }
  );

  const { data: { session } } = await supabase.auth.getSession();
  // ... rest of redirect logic unchanged
  return res;
}
```

`app/auth/callback/route.ts` also uses `createRouteHandlerClient` from `auth-helpers-nextjs`. Replace with `createServerClient` from `@supabase/ssr` using `cookies()` from `next/headers`.

Add `@supabase/ssr` to `package.json` dependencies. Remove `@supabase/auth-helpers-nextjs` entirely — it should not remain as a transitive dep.

---

### Important

---

#### I-1 — `app/auth/callback/route.ts`: Missing `redirectTo` preservation; user always lands at `/` regardless of original destination

**File:** `app/auth/callback/route.ts`
**Severity:** Important
**Category:** spec-gap

**Problem:**
`middleware.ts` sets `redirectTo` as a query param on the login URL:
```ts
loginUrl.searchParams.set("redirectTo", req.nextUrl.pathname);
```

But the login page never reads `redirectTo` and never passes it through the magic link flow, and the auth callback always redirects to `requestUrl.origin` (the app root). This means a user who lands on `/projects/abc`, gets bounced to login, authenticates, and then ends up at `/projects` instead of `/projects/abc`. Deep links are broken.

**Fix:**
1. In `app/login/page.tsx`, read `redirectTo` from `useSearchParams()` and thread it into the magic link options:
   ```ts
   options: { emailRedirectTo: `${callbackUrl}?next=${encodeURIComponent(redirectTo)}` }
   ```
2. In `app/auth/callback/route.ts`, read `next` from the search params and redirect there (after validation — only allow same-origin paths):
   ```ts
   const next = requestUrl.searchParams.get("next") ?? "/";
   const safePath = next.startsWith("/") ? next : "/";
   return NextResponse.redirect(new URL(safePath, requestUrl.origin));
   ```

Google OAuth is also affected — `redirectTo` is lost in that flow too. Same fix pattern applies.

---

#### I-2 — `app/admin/layout.tsx`: Client-side admin guard has a render flash window

**File:** `app/admin/layout.tsx`
**Severity:** Important
**Category:** acl-leak

**Problem:**
The admin layout is `"use client"` and defers the admin check to a `useEffect`. Between SSR/initial paint and when the effect fires + Supabase responds, the layout renders the "Checking admin access…" loader — but this also means the `children` prop (the admin page content) is passed to the layout tree and React has already begun reconciliation on it before `isAdmin` is confirmed. In React's concurrent rendering model this is benign from a data-leak perspective (children are not visible), but it means the URL is reachable and React work is done on admin page components before authorization is confirmed.

The deeper concern: this guard runs only in the browser. A non-admin user who disables JavaScript, or a bot that fetches the RSC payload directly, bypasses it entirely. Middleware protects authentication (is the user logged in?) but does not check admin role — so the RSC payload for `/admin/users` is served to any authenticated non-admin user who fetches the URL directly.

**Fix:**
Add admin role enforcement to `middleware.ts`. After the session check, read `session.user.app_metadata?.role` and redirect non-admins hitting `/admin/*` to `/projects`. This makes the check happen at the edge before any RSC rendering, and the client-side layout check becomes a belt-and-suspenders guard rather than the sole gate.

```ts
// In middleware, after session check:
if (req.nextUrl.pathname.startsWith("/admin")) {
  const role = session.user.app_metadata?.role;
  if (role !== "admin") {
    return NextResponse.redirect(new URL("/projects", req.url));
  }
}
```

---

### Minor / Notes (no block)

---

#### N-1 — `lib/supabaseClient.ts`: Fallback to `"http://localhost"` + `"placeholder"` will silently produce a working-but-wrong client

**File:** `lib/supabaseClient.ts`
**Severity:** Minor

The fallback values `"http://localhost"` and `"placeholder"` allow the Supabase client to initialize without throwing, but every call will fail silently or with an opaque network error instead of a clear "missing env var" message. The `console.error` only fires in the browser (`typeof window !== "undefined"`), so server-side initialization has no warning at all.

Not a block for a scaffold ticket but note it: in production, an accidental missing env var will produce confusing auth failures. Consider throwing in server context (SSR/route handlers) rather than silently initializing with a bad URL. Fine to leave for now given this is Sprint 1 scaffold.

---

#### N-2 — `middleware.ts`: The 8-second safety timeout in `app/admin/layout.tsx` is a smell

**File:** `app/admin/layout.tsx`
**Severity:** Minor

An 8-second timeout to catch a hung Supabase call is a workaround for a real problem: the client-side admin check is doing async Supabase work in a layout. This smell goes away when I-2's middleware fix is applied — the layout check becomes a fast synchronous guard on an already-confirmed session.

---

## Test Coverage Assessment

`app/__tests__/middleware.test.ts` tests only the exported `config.matcher` shape — it validates that the string contains `"login"` and `"_next"`. This is better than nothing but covers less than 5% of the middleware's behavior. The actual auth redirect logic (session absent → redirect, session present → pass through) has zero test coverage.

Acceptable for a scaffold ticket. Jìan should add middleware integration tests when the SSR migration is complete (post C-1 fix).

---

## Files Reviewed

| File | Status |
|---|---|
| `app/layout.tsx` | Pass |
| `app/globals.css` | Pass |
| `tailwind.config.ts` | Pass |
| `middleware.ts` | Fail — C-1, contributes to I-2 |
| `app/(app)/layout.tsx` | Pass |
| `components/AppSidebar.tsx` | Pass |
| `app/login/page.tsx` | Fail — I-1 |
| `app/admin/layout.tsx` | Fail — I-2 |
| `app/admin/users/page.tsx` | Pass (placeholder) |
| `app/admin/models/page.tsx` | Pass (placeholder) |
| `app/admin/rag-debug/page.tsx` | Pass (placeholder) |
| `lib/api.ts` | Pass |
| `lib/supabaseClient.ts` | Pass (N-1 noted) |
| `app/auth/callback/route.ts` | Fail — I-1 (related) |
| `app/__tests__/middleware.test.ts` | Pass (scope acknowledged) |
