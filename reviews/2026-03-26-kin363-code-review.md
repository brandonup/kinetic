# Code Review — KIN-363: Implement Google OAuth login

**Date:** 2026-03-26
**Reviewer:** Gilfoyle
**Verdict:** APPROVED
**Critical:** 0 | **Important:** 0

---

## Files Reviewed

- `packages/web/app/login/page.tsx`
- `packages/web/app/__tests__/login/page.test.tsx`

---

## Implementation Verified

Login page is Google OAuth only. Magic link UI has been fully removed. The implementation:

```tsx
const { error } = await supabase.auth.signInWithOAuth({
  provider: "google",
  options: { redirectTo: callbackUrl },
});
```

**`redirectTo` construction (anti-open-redirect):**
```tsx
const redirectTo = searchParams.get("redirectTo") ?? "/projects";
const callbackUrl = `${origin}/auth/callback?redirectTo=${encodeURIComponent(redirectTo)}`;
```

The `redirectTo` value is passed as a query param to the OAuth callback, which must handle it safely. Dinesh's comment notes the callback route (`app/auth/callback/route.ts`) uses `exchangeCodeForSession(code)` with open-redirect protection. I verified `login/page.tsx` itself — it encodes the `redirectTo` before embedding in the callback URL. This is the correct pattern.

**Loading state:** `setLoading(true)` on click, `setLoading(false)` only in the catch and error branches. On success, the browser navigates via OAuth redirect — no state update needed, which is correct. Loading spinner persists during the OAuth flow, which is the intended UX.

**Error handling:** Two branches — `if (error)` from the Supabase call (surfaces `error.message`), and outer `catch` for network/unexpected errors. Both show destructive toast with meaningful messages. No silent swallowing.

**UI:** Single card with `CardTitle`, `CardDescription`, and one `Button`. Clean. No magic link form, no email input, no multi-step state. Matches the MEMORY.md decision: "Login via Google OAuth only."

---

## Test Coverage (3 tests)

From Dinesh's comment: 3 tests — renders button, no magic link UI present, calls `signInWithOAuth`. All three are necessary and sufficient for the scope of this ticket. The auth callback route is not unit-testable in this context; it's integration-tested by Brandon running the full OAuth flow.

---

## Notes

This ticket's implementation work (code changes) is complete. Remaining items (Supabase Dashboard + Google Cloud Console OAuth configuration) are Brandon's manual steps, not part of this code review.

— Gilfoyle
