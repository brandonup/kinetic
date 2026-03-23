# Code Review — KIN-253: Frontend scaffold port (@supabase/ssr migration + redirectTo threading)

**Reviewer:** Gilfoyle
**Date:** 2026-03-22
**Round:** 2
**Verdict:** CHANGES_REQUESTED — 1 Critical, 0 Important

---

## Summary

R1's three issues (C-1 SSR migration, I-1 redirectTo threading, I-2 admin edge guard) have all been addressed at the structural level. The `@supabase/ssr` migration is complete and functionally correct. The admin role check at the edge is in place. The `redirectTo` flow is wired end-to-end for both magic link and OAuth paths.

One new critical issue introduced in this iteration: the `redirectTo` parameter flows from user input into `new URL()` in the callback route without validation, enabling an open redirect. The R1 fix spec explicitly included a same-origin validation guard that was not implemented.

---

## Findings

### Critical

---

#### C-1 — `app/auth/callback/route.ts:33`: Open redirect via unvalidated `redirectTo` parameter

**File:** `app/auth/callback/route.ts`, line 33
**Severity:** Critical
**Category:** acl-leak

**Problem:**

```ts
const redirectTo = requestUrl.searchParams.get("redirectTo") ?? "/projects";
// ...
return NextResponse.redirect(new URL(redirectTo, requestUrl.origin));
```

`new URL(redirectTo, requestUrl.origin)` does NOT clamp the redirect to the app's origin when `redirectTo` is an absolute URL. If `redirectTo = "https://evil.com"`, then `new URL("https://evil.com", "http://localhost:3000")` returns `https://evil.com` — the base is ignored when the first argument is already absolute. A phishing link of the form:

```
https://kinetic.app/auth/callback?code=...&redirectTo=https://evil.com
```

will redirect a fully authenticated user to an arbitrary external domain immediately after session establishment. This is a textbook open redirect.

The R1 fix spec included explicit validation at `app/auth/callback/route.ts`:

```ts
const next = requestUrl.searchParams.get("next") ?? "/";
const safePath = next.startsWith("/") ? next : "/";
return NextResponse.redirect(new URL(safePath, requestUrl.origin));
```

The parameter was renamed `redirectTo` (acceptable), but the `startsWith("/")` guard was dropped.

**Fix:**

Validate that `redirectTo` is a relative path before using it:

```ts
const rawRedirect = requestUrl.searchParams.get("redirectTo") ?? "/projects";
// Reject absolute URLs — only allow same-origin relative paths.
const redirectTo = rawRedirect.startsWith("/") && !rawRedirect.startsWith("//")
  ? rawRedirect
  : "/projects";

return NextResponse.redirect(new URL(redirectTo, requestUrl.origin));
```

The `!rawRedirect.startsWith("//")` guard closes the protocol-relative URL variant (`//evil.com`), which also bypasses origin validation in `new URL()`.

---

### Important — None

---

### Minor / Notes (no block)

---

#### N-1 — `middleware.ts`: Using older individual cookie API (`get/set/remove`) rather than `getAll/setAll`

**File:** `middleware.ts`, lines 14–28
**Severity:** Minor

The R1 fix spec recommended the `getAll/setAll` API (the newer pattern in `@supabase/ssr` docs). The implementation uses the older `get/set/remove` API with `CookieOptions`. Both are supported by `@supabase/ssr@0.5.0` and the implementation is functionally correct — the `set` handler re-creates `res` and writes cookies back, which is the critical behavior for token refresh. No functional defect. Acceptable for now, but when the package moves to a version that deprecates the individual API, this will need updating. Add a `// TODO: migrate to getAll/setAll when dropping @supabase/ssr <0.6` comment so the debt is visible.

---

#### N-2 — `app/__tests__/auth/callback.test.ts`: `redirectTo` parameter path not tested

**File:** `app/__tests__/auth/callback.test.ts`
**Severity:** Minor

The test suite covers: code present → exchange + redirect to `/projects`, code absent → redirect to `/projects`, exchange called with correct code. It does not test:
- `?redirectTo=/admin` → redirects to `/admin` (happy path once validation is in place)
- `?redirectTo=https://evil.com` → redirects to `/projects` (the open-redirect validation)
- `?redirectTo=//evil.com` → redirects to `/projects` (protocol-relative variant)

After C-1 is fixed, these three cases should be added to the test file. Not a block for this round — the fix and test can land together in R3.

---

## R1 Issue Resolution

| Issue | Status |
|---|---|
| C-1 — `@supabase/auth-helpers-nextjs` deprecated, token refresh unreliable | Fixed. `@supabase/ssr` used in both `middleware.ts` and `callback/route.ts`. Package added to `dependencies`. |
| I-1 — `redirectTo` not threaded through auth flow | Partially fixed. Parameter is threaded correctly for both magic link and OAuth. Validation gap introduced (new C-1 above). |
| I-2 — Admin role check missing at middleware edge | Fixed. `middleware.ts` checks `app_metadata?.role` for `/admin` routes before RSC rendering. |

---

## Files Reviewed

| File | Status |
|---|---|
| `middleware.ts` | Pass (N-1 noted) |
| `app/auth/callback/route.ts` | Fail — C-1 |
| `app/login/page.tsx` | Pass |
| `app/admin/layout.tsx` | Pass |
| `app/admin/rag-debug/page.tsx` | Pass (placeholder, consistent with users/models) |
| `app/admin/users/page.tsx` | Pass |
| `app/admin/models/page.tsx` | Pass |
| `app/__tests__/auth/callback.test.ts` | Pass (N-2 noted for post-fix test additions) |
| `app/__tests__/login/page.test.tsx` | Pass |
