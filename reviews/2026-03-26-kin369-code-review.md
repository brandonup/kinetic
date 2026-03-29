# Code Review — KIN-369: Add sign-out button to app shell

**Date:** 2026-03-26
**Reviewer:** Gilfoyle
**Verdict:** APPROVED
**Critical:** 0 | **Important:** 0

---

## Files Reviewed

- `packages/web/components/AppSidebar.tsx` (sign-out section, lines 348–363)
- `packages/web/app/__tests__/components/AppSidebar.test.tsx` (sign-out test, line 208)

---

## Implementation Verified

Sign-out button added to sidebar footer (`KIN-369` comment at line 348):

```tsx
<button
  data-testid="sign-out-button"
  onClick={() => {
    void supabase.auth.signOut().then(() => {
      router.push("/login");
    });
  }}
>
  <LogOut className="h-4 w-4 shrink-0" />
  Sign out
</button>
```

Correct pattern:
- `supabase.auth.signOut()` clears the local session
- `.then(() => router.push("/login"))` redirects only after signOut resolves
- `void` properly discards the Promise without a `.catch()` — acceptable since `signOut` is a best-effort cleanup; the redirect to `/login` happens regardless and the auth middleware will block re-entry
- `data-testid="sign-out-button"` pinned for testing

**Test:** `it("renders sign out button")` at line 208 — verifies the button is present in the rendered sidebar. Minimal but sufficient for a structural assertion.

**Positioning:** Button is in the sidebar footer, below a `<Separator />`, below the conversation scroll area. Visible on all authenticated pages. Correct placement.

**Styling:** Matches the pattern of other nav items (`flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60`). Consistent.

---

## No Findings

LGTM. Minimal, correct implementation. The sign-out flow (client-side session clear → redirect to /login) is the correct pattern for Supabase auth in a Next.js app router application.

— Gilfoyle
